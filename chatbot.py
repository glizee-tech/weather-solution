"""
Chatbot CLI:
- Entrée: une adresse (texte libre)
- Sortie: météo sur 7 jours (BAN -> Open-Meteo)
Commandes : quit, exit, q pour quitter.
"""

from __future__ import annotations

import sys

from weather_client import (
    GeocodingError,
    WeatherAPIError,
    format_weekly_running_plan_message,
    format_selected_slots,
    get_weekly_running_plan,
    render_week_timeline,
)


def _prompt_int(prompt: str, *, min_value: int, max_value: int, default: int) -> int:
    while True:
        raw = input(f"{prompt} [{default}] > ").strip()
        if not raw:
            return default
        try:
            v = int(raw)
        except ValueError:
            print("Entier invalide, recommence.")
            continue
        if v < min_value or v > max_value:
            print(f"Valeur hors bornes ({min_value}-{max_value}).")
            continue
        return v


def _prompt_choice(prompt: str, options: list[tuple[str, str]]) -> str:
    print(prompt)
    for key, label in options:
        print(f"  {key}) {label}")
    while True:
        choice = input("> ").strip()
        for key, _ in options:
            if choice == key:
                return choice
        print("Choix invalide, recommence.")


def _choose_filters() -> tuple[float, float, float]:
    print("Parametres de filtrage (ordre de grandeur).")
    print("- Pluie (mm/h) : 0 = sec, 0.1-0.5 = bruine/faible, 0.5-2 = pluie, >2 = pluie moderee+.")
    print("- Vent (km/h) : <15 calme, 15-25 brise, 25-35 vent, >40 fort.")
    print()

    rain = _prompt_choice(
        "Pluie moyenne max sur un creneau :",
        [
            ("1", "0.1 mm/h (quasi sec)"),
            ("2", "0.5 mm/h (faible pluie OK)"),
            ("3", "1.0 mm/h (leger acceptable)"),
        ],
    )
    rain_threshold = {"1": 0.1, "2": 0.5, "3": 1.0}[rain]

    wind = _prompt_choice(
        "Vent maximum max sur un creneau (vent ou rafales) :",
        [
            ("1", "20 km/h (plutot protege)"),
            ("2", "30 km/h (brise/vent modere)"),
            ("3", "40 km/h (vent soutenu)"),
        ],
    )
    wind_threshold = {"1": 20.0, "2": 30.0, "3": 40.0}[wind]

    dur = _prompt_choice(
        "Duree de course pour evaluer un creneau :",
        [
            ("1", "30 minutes (fenetre 1h)"),
            ("2", "1 heure (fenetre 1h)"),
            ("3", "2 heures (fenetre 2h)"),
        ],
    )
    run_duration = {"1": 0.5, "2": 1.0, "3": 2.0}[dur]

    print()
    return rain_threshold, wind_threshold, run_duration


def _choose_main_settings() -> tuple[int, int, int, int]:
    print("Reglages principaux (ne changent pas a chaque recherche).")
    print("Ex: semaine 17h-20h, week-end 9h-20h.")
    print()

    weekday_start_h = _prompt_int("Heure debut semaine (0-23)", min_value=0, max_value=23, default=17)
    weekday_end_h = _prompt_int("Heure fin semaine (1-24)", min_value=1, max_value=24, default=20)
    weekend_start_h = _prompt_int("Heure debut week-end (0-23)", min_value=0, max_value=23, default=9)
    weekend_end_h = _prompt_int("Heure fin week-end (1-24)", min_value=1, max_value=24, default=20)

    # petites validations
    if weekday_end_h <= weekday_start_h:
        print("Attention: fin semaine <= debut semaine. Je remets 17-20.")
        weekday_start_h, weekday_end_h = 17, 20
    if weekend_end_h <= weekend_start_h:
        print("Attention: fin week-end <= debut week-end. Je remets 09-20.")
        weekend_start_h, weekend_end_h = 9, 20

    print()
    return weekday_start_h, weekday_end_h, weekend_start_h, weekend_end_h


def _choose_outputs_per_week() -> int:
    print("Combien de sorties (creneaux) veux-tu proposer sur la semaine ?")
    print("Ordre de grandeur: 5 = 1 par jour en semaine, 7 = 1 par jour, 10-14 = plusieurs options.")
    v = _prompt_int("Nombre de creneaux / semaine", min_value=1, max_value=50, default=10)
    print()
    return v


def run() -> None:
    print("Plan de course sur 7 jours - tapez une adresse (ex. \"73 Avenue de Paris Saint-Mandé\").")
    print("Commandes : quit | exit | q\n")

    # Adresse d'abord (comme demande)
    try:
        first_address = input("Adresse > ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nAu revoir.")
        sys.exit(0)

    if not first_address:
        print("Adresse vide.")
        return
    if first_address.lower() in ("quit", "exit", "q", "bye"):
        print("Au revoir.")
        return

    weekday_start_h, weekday_end_h, weekend_start_h, weekend_end_h = _choose_main_settings()
    recommended_per_week = _choose_outputs_per_week()
    rain_threshold_mm_per_h, wind_threshold_kmh, run_duration_hours = _choose_filters()

    while True:
        user = first_address
        first_address = ""

        if not user:
            continue

        lower = user.lower()
        if lower in ("quit", "exit", "q", "bye"):
            print("Au revoir.")
            break

        try:
            label, per_day = get_weekly_running_plan(
                user,
                rain_threshold_mm_per_h=rain_threshold_mm_per_h,
                wind_threshold_kmh=wind_threshold_kmh,
                run_duration_hours=run_duration_hours,
            )
            timeline, slot_map = render_week_timeline(
                per_day,
                rain_threshold_mm_per_h=rain_threshold_mm_per_h,
                wind_threshold_kmh=wind_threshold_kmh,
                weekday_start_h=weekday_start_h,
                weekday_end_h=weekday_end_h,
                weekend_start_h=weekend_start_h,
                weekend_end_h=weekend_end_h,
                use_color=True,
            )
            print(timeline)

            # Selection interactive
            selected: set[str] = set()
            print()
            print("Selection des creneaux (tape: add 2026-04-01 18 | add 2026-04-01 17-20 | del ... | list | done)")
            while True:
                cmd = input("Selection > ").strip()
                if not cmd:
                    continue
                lc = cmd.lower()
                if lc in ("done", "ok", "finish"):
                    break
                if lc in ("list", "ls"):
                    print(format_selected_slots(sorted(selected), slot_map))
                    continue
                if lc in ("help", "?"):
                    print("Commandes: add YYYY-MM-DD HH | add YYYY-MM-DD HH-HH | del ... | list | done")
                    continue

                parts = cmd.split()
                if len(parts) < 3:
                    print("Format attendu: add/del YYYY-MM-DD HH ou add/del YYYY-MM-DD HH-HH")
                    continue
                action = parts[0].lower()
                d = parts[1]
                hh = parts[2]

                if action not in ("add", "del", "remove"):
                    print("Action inconnue. Utilise add/del/list/done.")
                    continue

                to_modify: list[str] = []
                if "-" in hh:
                    try:
                        start_s, end_s = hh.split("-", 1)
                        start_h = int(start_s)
                        end_h = int(end_s)
                    except Exception:
                        print("Plage invalide. Ex: 17-20")
                        continue
                    for h in range(start_h, end_h):
                        to_modify.append(f"{d} {h:02d}:00")
                else:
                    try:
                        h = int(hh)
                    except Exception:
                        print("Heure invalide. Ex: 18")
                        continue
                    to_modify.append(f"{d} {h:02d}:00")

                missing = [s for s in to_modify if s not in slot_map]
                if missing:
                    print("Ces creneaux ne sont pas disponibles (hors plage ou donnees manquantes):")
                    for m in missing[:10]:
                        print(f"- {m}")
                    continue

                if action == "add":
                    for s in to_modify:
                        selected.add(s)
                    print(f"Ajoute: {len(to_modify)} creneau(x). Total: {len(selected)}")
                else:
                    for s in to_modify:
                        selected.discard(s)
                    print(f"Supprime: {len(to_modify)} creneau(x). Total: {len(selected)}")

            print()
            print(format_selected_slots(sorted(selected), slot_map))
            print()

            print(
                format_weekly_running_plan_message(
                    label,
                    per_day,
                    rain_threshold_mm_per_h=rain_threshold_mm_per_h,
                    wind_threshold_kmh=wind_threshold_kmh,
                    run_duration_hours=run_duration_hours,
                    weekday_start_h=weekday_start_h,
                    weekday_end_h=weekday_end_h,
                    weekend_start_h=weekend_start_h,
                    weekend_end_h=weekend_end_h,
                    recommended_per_week=recommended_per_week,
                )
            )
        except GeocodingError as e:
            print(f"Adresse introuvable / erreur BAN : {e}")
        except WeatherAPIError as e:
            print(f"Erreur météo : {e}")

        print()

        # Prochaine recherche: nouvelle adresse uniquement
        try:
            nxt = input("Nouvelle adresse (ou q pour quitter) > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nAu revoir.")
            return
        if not nxt:
            continue
        if nxt.lower() in ("quit", "exit", "q", "bye"):
            print("Au revoir.")
            return
        first_address = nxt


if __name__ == "__main__":
    run()
