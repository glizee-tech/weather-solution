"""
Géocodage d'une adresse (BAN/Géoplateforme) + prévisions météo Open‑Meteo
pour une sortie chatbot CLI sur 7 jours.

Flux:
- Adresse -> lat/lon via `https://data.geopf.fr/geocodage/search`
- Jours 1-4 via `https://api.open-meteo.com/v1/meteofrance` (AROME/ARPEGE)
- Jours 5-7 via `https://api.open-meteo.com/v1/forecast` (complément)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as _date
import math
from typing import Any, Callable

import requests

BAN_SEARCH_URL = "https://data.geopf.fr/geocodage/search"
OPENMETEO_METEOFRENCE_URL = "https://api.open-meteo.com/v1/meteofrance"
OPENMETEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


class WeatherAPIError(Exception):
    """Erreur liée au service météo (réseau, paramètre, réponse inattendue)."""


class GeocodingError(Exception):
    """Erreur liée au géocodage (adresse introuvable, réponse inattendue)."""


@dataclass(frozen=True)
class DayForecast:
    date: str  # YYYY-MM-DD (local)
    temperature_2m_max: float | None
    temperature_2m_min: float | None
    precipitation_sum: float | None
    wind_speed_10m_max: float | None
    weather_code: int | None


def _http_get_json(url: str, params: dict[str, Any], *, timeout_s: int = 20) -> dict[str, Any]:
    try:
        r = requests.get(url, params=params, timeout=timeout_s)
    except requests.RequestException as e:
        raise WeatherAPIError(f"Erreur réseau: {e}") from e

    try:
        data = r.json()
    except ValueError:
        data = {"_raw": r.text}

    if r.status_code != 200:
        msg = data.get("reason") or data.get("message") or r.text
        raise WeatherAPIError(f"HTTP {r.status_code} sur {url}: {msg}")

    return data


def _feature_score(feature: dict[str, Any]) -> float:
    # Le spec montre des scores internes (`_score`) mais selon les cas la réponse peut varier.
    if isinstance(feature.get("_score"), (int, float)):
        return float(feature["_score"])
    props = feature.get("properties") or {}
    if isinstance(props.get("_score"), (int, float)):
        return float(props["_score"])
    if isinstance(props.get("score"), (int, float)):
        return float(props["score"])
    return 0.0


def _extract_lat_lon_from_ban_feature(feature: dict[str, Any]) -> tuple[float, float]:
    # Le schéma BAN expose des champs `properties.x/y` mais ils ne sont pas forcément en WGS84.
    # Pour Open‑Meteo, on utilise les coordonnées GeoJSON WGS84 attendues dans `geometry.coordinates`.
    geometry = feature.get("geometry") or {}
    coords = geometry.get("coordinates")
    if isinstance(coords, list) and len(coords) >= 2:
        # GeoJSON: [lon, lat]
        lon = float(coords[0])
        lat = float(coords[1])
        # Validation simple (sinon on se retrouve avec un système projeté en mètres).
        if not (-90.0 <= lat <= 90.0):
            raise GeocodingError(f"Latitude BAN invalide: {lat}")
        if not (-180.0 <= lon <= 180.0):
            raise GeocodingError(f"Longitude BAN invalide: {lon}")
        return lat, lon

    raise GeocodingError("Réponse BAN inattendue: `geometry.coordinates` introuvables.")


def ban_geocode_address(address: str) -> tuple[float, float, str]:
    """
    Convertit une adresse en (latitude, longitude, libellé).
    Retourne le meilleur résultat via `_score` quand disponible.
    """
    q = address.strip()
    if not q:
        raise GeocodingError("Adresse vide.")

    # index=address: recherche sur adresses.
    params = {"q": q, "index": "address", "limit": 10}
    data = _http_get_json(BAN_SEARCH_URL, params=params)

    features = data.get("features") or []
    if not features:
        raise GeocodingError(f"Aucune adresse trouvée pour: {q}")

    best = max(features, key=_feature_score)
    lat, lon = _extract_lat_lon_from_ban_feature(best)

    props = best.get("properties") or {}
    label = (
        props.get("label")
        or props.get("name")
        or props.get("street")
        or address
    )
    return lat, lon, str(label)


def _get_daily_array(daily: dict[str, Any], key: str) -> list[Any]:
    arr = daily.get(key)
    return arr if isinstance(arr, list) else []


def _parse_day_forecast(
    *,
    time: list[Any],
    daily: dict[str, Any],
    get_var: Callable[[dict[str, Any], str], list[Any]],
    var_temp_max: str,
    var_temp_min: str,
    var_precip: str,
    var_wind: str,
    var_code: str,
) -> list[DayForecast]:
    times = [str(t) for t in time]
    tmax = get_var(daily, var_temp_max)
    tmin = get_var(daily, var_temp_min)
    precip = get_var(daily, var_precip)
    wind = get_var(daily, var_wind)
    codes = get_var(daily, var_code)

    days: list[DayForecast] = []
    for i, t in enumerate(times):
        # t est généralement "YYYY-MM-DD" ou ISO timestamp; on garde la date.
        date = t[:10]

        def at(arr: list[Any]) -> float | None:
            if i >= len(arr):
                return None
            v = arr[i]
            return float(v) if isinstance(v, (int, float)) else None

        def at_int(arr: list[Any]) -> int | None:
            if i >= len(arr):
                return None
            v = arr[i]
            return int(v) if isinstance(v, (int, float)) else None

        days.append(
            DayForecast(
                date=date,
                temperature_2m_max=at(tmax),
                temperature_2m_min=at(tmin),
                precipitation_sum=at(precip),
                wind_speed_10m_max=at(wind),
                weather_code=at_int(codes),
            )
        )

    return days


def openmeteo_fetch_meteofrance_daily(lat: float, lon: float) -> list[DayForecast]:
    """
    Jours 1-4 via /v1/meteofrance (combinaison AROME/ARPEGE).
    La doc Open-Meteo indique une portée max de 4 jours.
    """
    params: dict[str, Any] = {
        "latitude": lat,
        "longitude": lon,
        "daily": ",".join(
            [
                "temperature_2m_max",
                "temperature_2m_min",
                "precipitation_sum",
                "wind_speed_10m_max",
                "weather_code",
            ]
        ),
        "timezone": "auto",
        "forecast_days": 4,
    }
    data = _http_get_json(OPENMETEO_METEOFRENCE_URL, params=params)
    daily = data.get("daily") or {}
    time = daily.get("time") or []
    return _parse_day_forecast(
        time=time,
        daily=daily,
        get_var=_get_daily_array,
        var_temp_max="temperature_2m_max",
        var_temp_min="temperature_2m_min",
        var_precip="precipitation_sum",
        var_wind="wind_speed_10m_max",
        var_code="weather_code",
    )


def openmeteo_fetch_forecast_daily(lat: float, lon: float, *, forecast_days: int = 7) -> list[DayForecast]:
    """
    Complément via /v1/forecast pour atteindre 7 jours.
    Par défaut, on demande 7 jours et on tronque/fusionne ensuite côté application.
    """
    params: dict[str, Any] = {
        "latitude": lat,
        "longitude": lon,
        "daily": ",".join(
            [
                "temperature_2m_max",
                "temperature_2m_min",
                "precipitation_sum",
                "wind_speed_10m_max",
                "weather_code",
            ]
        ),
        "timezone": "auto",
        "forecast_days": forecast_days,
    }
    data = _http_get_json(OPENMETEO_FORECAST_URL, params=params)
    daily = data.get("daily") or {}
    time = daily.get("time") or []
    return _parse_day_forecast(
        time=time,
        daily=daily,
        get_var=_get_daily_array,
        var_temp_max="temperature_2m_max",
        var_temp_min="temperature_2m_min",
        var_precip="precipitation_sum",
        var_wind="wind_speed_10m_max",
        var_code="weather_code",
    )


def get_weekly_weather_for_address(address: str) -> tuple[str, list[DayForecast]]:
    """
    Retourne:
    - un label (adresse/libellé)
    - une liste de 7 DayForecast (date croissante, local-time)
    """
    lat, lon, label = ban_geocode_address(address)

    meteofrance_days: list[DayForecast] = []
    try:
        meteofrance_days = openmeteo_fetch_meteofrance_daily(lat, lon)
    except WeatherAPIError:
        # Fallback: si /v1/meteofrance est indisponible (réseau/SSL/etc),
        # on continue quand même avec /v1/forecast pour fournir une réponse utile.
        meteofrance_days = []
    forecast_days = openmeteo_fetch_forecast_daily(lat, lon, forecast_days=7)

    merged_by_date: dict[str, DayForecast] = {d.date: d for d in meteofrance_days}

    # Compléter avec les jours manquants.
    for d in forecast_days:
        if len(merged_by_date) >= 7:
            break
        if d.date not in merged_by_date:
            merged_by_date[d.date] = d

    ordered = [merged_by_date[k] for k in sorted(merged_by_date.keys())]

    # Sécurité: s'assurer qu'on a bien 7 jours (ou le max dispo).
    return label, ordered[:7]


def format_weekly_weather_message(address_label: str, days: list[DayForecast]) -> str:
    lines = [f"Meteo sur 7 jours - {address_label}"]
    lines.append("Source: Open-Meteo (BAN -> coordonnees).")

    for d in days:
        tmin = f"{d.temperature_2m_min:.0f}°C" if d.temperature_2m_min is not None else "N/A"
        tmax = f"{d.temperature_2m_max:.0f}°C" if d.temperature_2m_max is not None else "N/A"
        precip = f"{d.precipitation_sum:.1f} mm" if d.precipitation_sum is not None else "N/A"
        wind = f"{d.wind_speed_10m_max:.0f} km/h" if d.wind_speed_10m_max is not None else "N/A"
        code = str(d.weather_code) if d.weather_code is not None else "N/A"

        lines.append(f"{d.date} : {tmin} - {tmax}, pluie {precip}, vent max {wind}, code {code}")

    return "\n".join(lines)


@dataclass(frozen=True)
class HourlyForecast:
    # ISO local time string (ex: "2026-03-30T14:00")
    time: str
    date: str  # YYYY-MM-DD
    hour: str  # HH:MM
    precipitation_mm: float | None  # pluie (mm/h)
    wind_speed_kmh: float | None  # vent (km/h)
    wind_gust_kmh: float | None  # rafales (km/h)
    wind_direction_deg: float | None  # degrees 0..360
    weather_code: int | None


def _deg_to_compass_16(deg: float) -> str:
    # 16 directions: N, NNE, NE, ...
    dirs = [
        "N",
        "NNE",
        "NE",
        "ENE",
        "E",
        "ESE",
        "SE",
        "SSE",
        "S",
        "SSW",
        "SW",
        "WSW",
        "W",
        "WNW",
        "NW",
        "NNW",
    ]
    # round to nearest 22.5 degrees
    idx = int((deg + 11.25) // 22.5) % 16
    return dirs[idx]


def _is_weekend(iso_date: str) -> bool:
    # ISO date: YYYY-MM-DD
    d = _date.fromisoformat(iso_date)
    # 0=Mon ... 5=Sat 6=Sun
    return d.weekday() >= 5


def _hour_in_range(hour_hhmm: str, start_h: int, end_h: int) -> bool:
    # end_h is exclusive. Example: start=17 end=20 => 17:00,18:00,19:00
    try:
        hh = int(hour_hhmm[:2])
    except Exception:
        return False
    return start_h <= hh < end_h


def _parse_hourly_response(data: dict[str, Any]) -> list[HourlyForecast]:
    hourly = data.get("hourly") or {}
    times = hourly.get("time") or []

    precip = hourly.get("precipitation")
    wind_speed = hourly.get("wind_speed_10m")
    gust = hourly.get("wind_gusts_10m")
    wind_dir = hourly.get("wind_direction_10m")
    weather_code = hourly.get("weather_code")

    def arr(key_arr: Any, i: int) -> float | int | None:
        if not isinstance(key_arr, list):
            return None
        if i >= len(key_arr):
            return None
        v = key_arr[i]
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return v
        try:
            return float(v)  # type: ignore[arg-type]
        except Exception:
            return None

    res: list[HourlyForecast] = []
    for i, t in enumerate(times):
        t_str = str(t)
        date = t_str[:10]
        hour = t_str[11:16] if len(t_str) >= 16 else t_str

        res.append(
            HourlyForecast(
                time=t_str,
                date=date,
                hour=hour,
                precipitation_mm=float(arr(precip, i)) if isinstance(arr(precip, i), (int, float)) else None,
                wind_speed_kmh=float(arr(wind_speed, i)) if isinstance(arr(wind_speed, i), (int, float)) else None,
                wind_gust_kmh=float(arr(gust, i)) if isinstance(arr(gust, i), (int, float)) else None,
                wind_direction_deg=float(arr(wind_dir, i)) if isinstance(arr(wind_dir, i), (int, float)) else None,
                weather_code=int(arr(weather_code, i)) if isinstance(arr(weather_code, i), (int, float)) else None,
            )
        )

    return res


def openmeteo_fetch_forecast_hourly(lat: float, lon: float, *, forecast_days: int = 7) -> list[HourlyForecast]:
    params: dict[str, Any] = {
        "latitude": lat,
        "longitude": lon,
        "hourly": ",".join(
            [
                "precipitation",
                "wind_speed_10m",
                "wind_gusts_10m",
                "wind_direction_10m",
                "weather_code",
            ]
        ),
        "timezone": "auto",
        "forecast_days": forecast_days,
        "wind_speed_unit": "kmh",
        "precipitation_unit": "mm",
    }
    data = _http_get_json(OPENMETEO_FORECAST_URL, params=params)
    return _parse_hourly_response(data)


def openmeteo_fetch_meteofrance_hourly(lat: float, lon: float) -> list[HourlyForecast]:
    # Portee AROME/ARPEGE max: 4 jours
    params: dict[str, Any] = {
        "latitude": lat,
        "longitude": lon,
        "hourly": ",".join(
            [
                "precipitation",
                "wind_speed_10m",
                "wind_gusts_10m",
                "wind_direction_10m",
                "weather_code",
            ]
        ),
        "timezone": "auto",
        "forecast_days": 4,
        "wind_speed_unit": "kmh",
        "precipitation_unit": "mm",
    }
    data = _http_get_json(OPENMETEO_METEOFRENCE_URL, params=params)
    return _parse_hourly_response(data)


def get_weekly_running_plan(
    address: str,
    *,
    rain_threshold_mm_per_h: float = 0.5,
    wind_threshold_kmh: float = 20.0,
    run_duration_hours: float = 0.5,
    recommended_per_day: int = 3,
) -> tuple[str, list[tuple[str, list[HourlyForecast]]]]:
    """
    Retourne:
    - label adresse
    - liste de (date, liste 24h) sous forme de HourlyForecast
    """
    lat, lon, label = ban_geocode_address(address)

    # Base: /forecast pour couvrir toute la semaine.
    forecast_hours = openmeteo_fetch_forecast_hourly(lat, lon, forecast_days=7)
    hours_by_time: dict[str, HourlyForecast] = {h.time: h for h in forecast_hours}

    # Optionnel: /meteofrance pour remplacer les 4 premiers jours.
    try:
        meteofrance_hours = openmeteo_fetch_meteofrance_hourly(lat, lon)
        for h in meteofrance_hours:
            hours_by_time[h.time] = h
    except WeatherAPIError:
        pass

    # On reconstitue la liste dans l'ordre du /forecast (times).
    ordered = [hours_by_time[h.time] for h in forecast_hours if h.time in hours_by_time]

    # Grouper par jour et ne garder que 7 jours
    unique_dates: list[str] = []
    grouped: dict[str, list[HourlyForecast]] = {}
    for h in ordered:
        if h.date not in grouped:
            grouped[h.date] = []
        grouped[h.date].append(h)
        if h.date not in unique_dates:
            unique_dates.append(h.date)
        if len(unique_dates) >= 7:
            # on continue de remplir jusqu'a la fin de la 7e journee
            pass

    selected_dates = unique_dates[:7]
    per_day = [(d, grouped.get(d, [])) for d in selected_dates]
    # Assurer tri par heure
    per_day = [(d, sorted(day_hours, key=lambda x: x.time)) for (d, day_hours) in per_day]

    # "score" uniquement pour recommandation (affichage géré ailleurs).
    # On renvoie aussi les heures pour pouvoir faire un affichage horaire detaille.
    _ = recommended_per_day

    return label, per_day


def _hour_ok(h: HourlyForecast, *, rain_threshold_mm_per_h: float, wind_threshold_kmh: float) -> bool:
    if h.precipitation_mm is None or h.wind_speed_kmh is None:
        return False
    eff_wind = h.wind_speed_kmh
    if h.wind_gust_kmh is not None:
        eff_wind = max(eff_wind, h.wind_gust_kmh)
    return h.precipitation_mm <= rain_threshold_mm_per_h and eff_wind <= wind_threshold_kmh


def _hour_effective_wind_kmh(h: HourlyForecast) -> float | None:
    if h.wind_speed_kmh is None:
        return None
    eff = float(h.wind_speed_kmh)
    if h.wind_gust_kmh is not None:
        eff = max(eff, float(h.wind_gust_kmh))
    return eff


def score_hour(
    h: HourlyForecast,
    *,
    rain_threshold_mm_per_h: float,
    wind_threshold_kmh: float,
) -> float | None:
    """
    Score horaire normalisé (0..1):
    - 1.0 = excellent (sec + peu de vent)
    - 0.0 = très mauvais

    On pénalise:
    - la pluie au-dessus du seuil (poids fort)
    - le vent max (rafales incluses) au-dessus du seuil
    """
    if h.precipitation_mm is None:
        return None
    eff_w = _hour_effective_wind_kmh(h)
    if eff_w is None:
        return None

    rain_excess = max(0.0, float(h.precipitation_mm) - rain_threshold_mm_per_h)
    wind_excess = max(0.0, float(eff_w) - wind_threshold_kmh)

    # On transforme en une "pénalité" bornée (plus robuste qu'un seuil dur)
    #  - pluie: chaque +1.0 mm/h au-dessus -> grosse pénalité
    #  - vent: chaque +10 km/h au-dessus -> pénalité modérée
    penalty = (rain_excess * 1.5) + (wind_excess / 10.0)

    # Convertir pénalité -> score 0..1 (décroissance exponentielle douce)
    score = math.exp(-penalty)
    if score < 0.0:
        return 0.0
    if score > 1.0:
        return 1.0
    return float(score)


def _ansi_bg_rgb(r: int, g: int, b: int) -> str:
    return f"\x1b[48;2;{r};{g};{b}m"


def _ansi_fg_rgb(r: int, g: int, b: int) -> str:
    return f"\x1b[38;2;{r};{g};{b}m"


ANSI_RESET = "\x1b[0m"


def _color_from_score(score: float) -> tuple[int, int, int]:
    # 0 -> rouge, 1 -> vert (gradient simple)
    score = min(1.0, max(0.0, score))
    r = int(round(255 * (1.0 - score)))
    g = int(round(255 * score))
    b = 0
    return r, g, b


def render_week_timeline(
    per_day: list[tuple[str, list[HourlyForecast]]],
    *,
    rain_threshold_mm_per_h: float,
    wind_threshold_kmh: float,
    weekday_start_h: int,
    weekday_end_h: int,
    weekend_start_h: int,
    weekend_end_h: int,
    use_color: bool = True,
) -> tuple[str, dict[str, HourlyForecast]]:
    """
    Rend une frise type "heatmap" heure-par-heure.
    Retourne:
    - texte à afficher
    - mapping slot_id -> HourlyForecast, où slot_id = YYYY-MM-DD HH:00
    """
    # La heatmap montre toute la journee (00h-23h), sans filtrer par disponibilites.
    slot_map: dict[str, HourlyForecast] = {}
    lines: list[str] = []

    lines.append("Frise semaine (vert=meilleur, rouge=a eviter). 1 case = 1 heure.")
    lines.append(f"Seuils: pluie moy {rain_threshold_mm_per_h:.1f} mm/h, vent max {wind_threshold_kmh:.0f} km/h.")
    lines.append("")

    # Header heures: 00..23 mais on n'affichera que la plage
    lines.append("      " + " ".join([f"{h:02d}" for h in range(0, 24)]))

    for iso_date, hours in per_day:
        if not hours:
            continue
        row_cells: list[str] = []
        by_hh: dict[int, HourlyForecast] = {}
        for h in hours:
            try:
                hh = int(h.hour[:2])
            except Exception:
                continue
            by_hh[hh] = h

        for hh in range(0, 24):
            hf = by_hh.get(hh)
            if hf is None:
                row_cells.append("??")
                continue
            s = score_hour(hf, rain_threshold_mm_per_h=rain_threshold_mm_per_h, wind_threshold_kmh=wind_threshold_kmh)
            if s is None:
                row_cells.append("..")
                continue

            slot_id = f"{iso_date} {hh:02d}:00"
            slot_map[slot_id] = hf

            # Choix du caractère affiché
            cell_char = "  "
            if use_color:
                r, g, b = _color_from_score(s)
                # Couleur de fond + petit point blanc/noir selon luminosité
                lum = (0.2126 * r + 0.7152 * g + 0.0722 * b)
                fg = (0, 0, 0) if lum > 140 else (255, 255, 255)
                dot = "•" if s >= 0.5 else "·"
                cell_char = _ansi_bg_rgb(r, g, b) + _ansi_fg_rgb(*fg) + dot + " " + ANSI_RESET
            else:
                # Sans couleur: 0..1 -> 0..9
                lvl = int(round(s * 9))
                cell_char = f"{lvl:02d}"

            row_cells.append(cell_char)

        # Label jour
        day_label = iso_date
        lines.append(f"{day_label} " + " ".join(row_cells))

    lines.append("")
    lines.append("Lecture: ??=donnees manquantes.")
    lines.append("Tu peux selectionner des creneaux avec: YYYY-MM-DD HH (ex: 2026-04-01 18) ou une plage: YYYY-MM-DD 17-20")

    return "\n".join(lines), slot_map


def format_selected_slots(
    selected: list[str],
    slot_map: dict[str, HourlyForecast],
) -> str:
    lines = ["Creneaux choisis:"]
    for slot_id in sorted(selected):
        h = slot_map.get(slot_id)
        if h is None:
            lines.append(f"- {slot_id} (inconnu)")
            continue
        eff_w = _hour_effective_wind_kmh(h)
        dir_txt = "N/A"
        if h.wind_direction_deg is not None:
            dir_txt = f"{_deg_to_compass_16(h.wind_direction_deg)}({h.wind_direction_deg:.0f}deg)"
        lines.append(
            f"- {slot_id} | pluie {h.precipitation_mm:.1f} mm/h | vent {eff_w:.0f} km/h | dir {dir_txt}"
        )
    return "\n".join(lines)

def format_weekly_running_plan_message(
    address_label: str,
    per_day: list[tuple[str, list[HourlyForecast]]],
    *,
    rain_threshold_mm_per_h: float,
    wind_threshold_kmh: float,
    run_duration_hours: float,
    recommended_per_day: int = 3,
    # Disponibilites (heures locales)
    weekday_start_h: int = 17,
    weekday_end_h: int = 20,
    weekend_start_h: int = 9,
    weekend_end_h: int = 20,
    recommended_per_week: int = 10,
) -> str:
    window_hours = max(1, int(math.ceil(run_duration_hours)))

    lines: list[str] = [
        f"Plan de course 7 jours - {address_label}",
        f"Criteres creneaux: pluie MOYENNE <= {rain_threshold_mm_per_h:.1f} mm/h, vent MAX <= {wind_threshold_kmh:.0f} km/h, duree ~{run_duration_hours:g}h (fenetre {window_hours}h).",
        f"Disponibilites: semaine {weekday_start_h:02d}h-{weekday_end_h:02d}h, week-end {weekend_start_h:02d}h-{weekend_end_h:02d}h.",
        "Vent: direction donnee en degres et boussole (d'ou le vent vient).",
    ]

    # Collect candidates over the entire week, within availability windows.
    global_candidates: list[tuple[bool, float, str, int]] = []

    for date, hours in per_day:
        if not hours:
            continue
        lines.append(f"\nJour {date}")

        is_we = _is_weekend(date)
        start_h = weekend_start_h if is_we else weekday_start_h
        end_h = weekend_end_h if is_we else weekday_end_h

        # Horaire detaille: 24h (ou moins si API limite)
        lines.append("Heure | Pluie(mm/h) | Vent(km/h) | Rafales(km/h) | VentDir(deg) | OK?")
        for h in hours:
            # Affichage: ne montrer que les heures "disponibles"
            if not _hour_in_range(h.hour, start_h, end_h):
                continue

            dir_txt = "N/A"
            if h.wind_direction_deg is not None:
                dir_txt = f"{_deg_to_compass_16(h.wind_direction_deg)}({h.wind_direction_deg:.0f}deg)"

            eff_wind = h.wind_speed_kmh if h.wind_speed_kmh is not None else None
            gust_txt = "N/A"
            if h.wind_gust_kmh is not None:
                gust_txt = f"{h.wind_gust_kmh:.0f}"
                if eff_wind is not None:
                    eff_wind = max(eff_wind, h.wind_gust_kmh)

            ok = _hour_ok(h, rain_threshold_mm_per_h=rain_threshold_mm_per_h, wind_threshold_kmh=wind_threshold_kmh)

            lines.append(
                f"{h.hour} | {h.precipitation_mm:.1f} | {h.wind_speed_kmh:.0f} | {gust_txt} | {dir_txt} | {'OK' if ok else 'EVITE'}"
            )

        # Candidats de creneaux (duree fenetre), dans les heures disponibles
        n = len(hours)
        for i in range(0, max(0, n - window_hours + 1)):
            window = hours[i : i + window_hours]
            if not window:
                continue

            # Fenetre doit etre entierement dans les heures disponibles
            if not all(_hour_in_range(x.hour, start_h, end_h) for x in window):
                continue

            # On a besoin de valeurs au moins pour pluie + vent
            if not all((x.precipitation_mm is not None and x.wind_speed_kmh is not None) for x in window):
                continue

            avg_precip = sum(float(x.precipitation_mm) for x in window) / float(window_hours)
            max_wind = 0.0
            for x in window:
                eff = float(x.wind_speed_kmh)
                if x.wind_gust_kmh is not None:
                    eff = max(eff, float(x.wind_gust_kmh))
                max_wind = max(max_wind, eff)

            strict_ok = avg_precip <= rain_threshold_mm_per_h and max_wind <= wind_threshold_kmh

            # score simple: minimiser pluie et vent au-dessus des seuils
            total_penalty = 0.0
            total_penalty += max(0.0, avg_precip - rain_threshold_mm_per_h) * 100.0
            total_penalty += max(0.0, max_wind - wind_threshold_kmh)

            global_candidates.append((strict_ok, total_penalty, date, i))

    # Global recommendation list (over the whole week)
    lines.append("\nMeilleurs creneaux de la semaine (toutes dates confondues):")
    if not global_candidates:
        lines.append("Aucun creneau disponible dans tes plages horaires (ou donnees manquantes).")
        return "\n".join(lines)

    global_candidates.sort(key=lambda x: (0 if x[0] else 1, x[1], x[2], x[3]))
    chosen: list[tuple[str, int]] = []
    for _, __, d, idx in global_candidates:
        # eviter de proposer 2 creneaux identiques
        if (d, idx) in chosen:
            continue
        chosen.append((d, idx))
        if len(chosen) >= recommended_per_week:
            break

    for d, idx in chosen:
        hours = next((hs for (dd, hs) in per_day if dd == d), [])
        if not hours:
            continue
        is_we = _is_weekend(d)
        start_h = weekend_start_h if is_we else weekday_start_h
        end_h = weekend_end_h if is_we else weekday_end_h
        window = hours[idx : idx + window_hours]
        if not window:
            continue
        if not all(_hour_in_range(x.hour, start_h, end_h) for x in window):
            continue
        avg_precip = sum(float(x.precipitation_mm) for x in window) / float(window_hours)
        max_wind = 0.0
        for x in window:
            eff = float(x.wind_speed_kmh) if x.wind_speed_kmh is not None else 0.0
            if x.wind_gust_kmh is not None:
                eff = max(eff, float(x.wind_gust_kmh))
            max_wind = max(max_wind, eff)
        start = window[0]
        dir_txt = "N/A"
        if start.wind_direction_deg is not None:
            dir_txt = f"{_deg_to_compass_16(start.wind_direction_deg)}({start.wind_direction_deg:.0f}deg)"
        strict_tag = "STRICT_OK" if (avg_precip <= rain_threshold_mm_per_h and max_wind <= wind_threshold_kmh) else "BEST_EFFORT"
        lines.append(
            f"- {d} {start.hour} | pluie moy {avg_precip:.1f} mm/h | vent max {max_wind:.0f} km/h | dir {dir_txt} | {strict_tag}"
        )

    return "\n".join(lines)
