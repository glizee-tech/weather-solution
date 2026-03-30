let map;
let marker = null;
let currentPlan = null;
const selectedSlots = new Set();

/** Coordonnées connues comme correspondant au champ adresse (géocodage ou clic carte). */
let locationCoords = null;
let _settingAddressProgrammatically = false;

function byId(id) {
  return document.getElementById(id);
}

function setStatus(msg, isError = false) {
  const el = byId("status");
  el.textContent = msg;
  el.style.color = isError ? "#b91c1c" : "#0f766e";
}

function setAddressField(value, coords) {
  _settingAddressProgrammatically = true;
  byId("address").value = value;
  locationCoords = coords;
  _settingAddressProgrammatically = false;
}

function initMap() {
  map = L.map("map").setView([46.7, 2.4], 6);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap contributors",
  }).addTo(map);

  map.on("click", async (e) => {
    const lat = e.latlng.lat;
    const lng = e.latlng.lng;
    setStatus("Adresse au point cliqué…");
    try {
      const data = await callApi("/api/reverse", { latitude: lat, longitude: lng });
      const loc = data.location;
      setAddressField(loc.label, { lat: loc.latitude, lon: loc.longitude });
      updateMarker(loc.latitude, loc.longitude, loc.label);
      setStatus("Adresse mise à jour (carte).");
    } catch (err) {
      setStatus(`Géocodage inverse : ${err.message}`, true);
    }
  });
}

function updateMarker(lat, lon, label) {
  if (marker) map.removeLayer(marker);
  marker = L.marker([lat, lon]).addTo(map);
  marker.bindPopup(label).openPopup();
  map.setView([lat, lon], 12);
  byId("location-label").textContent = `${label} (${lat.toFixed(4)}, ${lon.toFixed(4)})`;
}

async function callApi(path, payload) {
  const resp = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await resp.json();
  if (!resp.ok) {
    const detail = data && data.detail ? data.detail : "Erreur API";
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return data;
}

function scoreColor(score) {
  if (score === null || score === undefined) return "#cbd5e1";
  const s = Math.max(0, Math.min(1, score));
  const r = Math.round(255 * (1 - s));
  const g = Math.round(255 * s);
  return `rgb(${r},${g},0)`;
}

function slotId(date, hourLabel) {
  return `${date} ${hourLabel}`;
}

/** ISO date YYYY-MM-DD -> « lundi 3 mars 2026 » */
function formatDayLabel(isoDate) {
  const p = isoDate.split("-").map(Number);
  if (p.length !== 3 || p.some(Number.isNaN)) return isoDate;
  const dt = new Date(p[0], p[1] - 1, p[2]);
  return new Intl.DateTimeFormat("fr-FR", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  }).format(dt);
}

function windArrowSvg(degFrom) {
  if (degFrom == null || Number.isNaN(Number(degFrom))) return "";
  const d = Number(degFrom);
  // Direction météo : vent venant de d° (horaire depuis le nord). La flèche pointe vers l’origine du vent.
  return `<span class="wind-arrow" title="Vent de ${d.toFixed(0)}° (${compass16(d)})"><svg width="22" height="22" viewBox="-11 -11 22 22" aria-hidden="true"><g transform="rotate(${d})"><polygon points="0,-9 -3.5,5 0,2 3.5,5" fill="currentColor"/></g></svg></span>`;
}

function compass16(deg) {
  const names = [
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
  ];
  const i = Math.round(deg / 22.5) % 16;
  return names[i];
}

function renderHeatmap(plan) {
  const container = byId("heatmap");
  container.innerHTML = "";

  const table = document.createElement("table");
  table.className = "heatmap-table";

  const thead = document.createElement("thead");
  const hr = document.createElement("tr");
  const blank = document.createElement("th");
  blank.className = "day-col";
  blank.textContent = "Jour";
  hr.appendChild(blank);
  for (let h = 0; h < 24; h++) {
    const th = document.createElement("th");
    th.textContent = `${String(h).padStart(2, "0")}`;
    hr.appendChild(th);
  }
  thead.appendChild(hr);
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  for (const day of plan.days) {
    const tr = document.createElement("tr");
    const tdDay = document.createElement("th");
    tdDay.className = "day-col";
    tdDay.textContent = formatDayLabel(day.date);
    tr.appendChild(tdDay);

    const byHour = {};
    for (const h of day.hours) byHour[h.hour_int] = h;

    for (let hh = 0; hh < 24; hh++) {
      const td = document.createElement("td");
      td.className = "heat-cell";
      const h = byHour[hh];
      if (!h) {
        td.textContent = "?";
        td.style.backgroundColor = "#e2e8f0";
      } else {
        const id = slotId(day.date, h.hour_label);
        td.dataset.slotId = id;
        td.style.backgroundColor = scoreColor(h.score);
        td.title = `${id}\npluie=${h.precipitation_mm ?? "N/A"} mm/h\nvent=${h.effective_wind_kmh ?? "N/A"} km/h\ndir=${h.wind_direction_compass ?? "N/A"} (${h.wind_direction_deg ?? "N/A"}°)`;
        td.textContent = h.score == null ? "?" : Math.round(h.score * 9);
        if (h.available) td.classList.add("privileged");
        else td.classList.add("unavailable");
        if (selectedSlots.has(id)) td.classList.add("selected");
        td.addEventListener("click", () => {
          if (selectedSlots.has(id)) selectedSlots.delete(id);
          else selectedSlots.add(id);
          renderSelected(plan);
          renderHeatmap(plan);
        });
      }
      tr.appendChild(td);
    }
    tbody.appendChild(tr);
  }
  table.appendChild(tbody);
  container.appendChild(table);
}

function renderSelected(plan) {
  const ul = byId("selected-list");
  ul.innerHTML = "";

  const hourIndex = {};
  for (const d of plan.days) {
    for (const h of d.hours) hourIndex[slotId(d.date, h.hour_label)] = h;
  }

  const ids = Array.from(selectedSlots).sort();
  if (ids.length === 0) {
    const li = document.createElement("li");
    li.textContent = "Aucun créneau sélectionné.";
    ul.appendChild(li);
    return;
  }

  for (const id of ids) {
    const h = hourIndex[id];
    const li = document.createElement("li");
    if (!h) {
      li.textContent = `${id} (indisponible)`;
    } else {
      li.className = "selected-slot-row";
      const arrow = windArrowSvg(h.wind_direction_deg);
      li.innerHTML = `${arrow}<span class="selected-slot-text">${id} | pluie ${h.precipitation_mm ?? "N/A"} mm/h | vent ${h.effective_wind_kmh ?? "N/A"} km/h | ${h.wind_direction_compass ?? "N/A"}</span>`;
    }
    ul.appendChild(li);
  }
}

function renderRecommendations(plan) {
  const ul = byId("recommended-list");
  ul.innerHTML = "";
  for (const r of plan.recommendations || []) {
    const li = document.createElement("li");
    li.textContent = `${formatDayLabel(r.date)} ${r.start_hour_label} | pluie moy ${r.avg_precipitation_mm.toFixed(1)} mm/h | vent max ${r.max_wind_kmh.toFixed(0)} km/h | ${r.strict_ok ? "STRICT_OK" : "BEST_EFFORT"}`;
    ul.appendChild(li);
  }
}

async function handleGeocode() {
  const address = byId("address").value.trim();
  if (!address) return;
  setStatus("Géocodage en cours...");
  try {
    const data = await callApi("/api/geocode", { address });
    const loc = data.location;
    locationCoords = { lat: loc.latitude, lon: loc.longitude };
    updateMarker(loc.latitude, loc.longitude, loc.label);
    setStatus("Adresse localisée.");
  } catch (e) {
    setStatus(`Erreur géocodage: ${e.message}`, true);
  }
}

async function handlePlanSubmit(ev) {
  ev.preventDefault();
  const address = byId("address").value.trim();
  if (address.length < 2 && !locationCoords) {
    setStatus("Indiquez une adresse ou cliquez sur la carte pour choisir un lieu.", true);
    return;
  }

  const payload = {
    address,
    rain_threshold_mm_per_h: Number(byId("rain").value),
    wind_threshold_kmh: Number(byId("wind").value),
    run_duration_hours: Number(byId("duration").value),
    recommended_per_week: Number(byId("recommended").value),
    weekday_start_h: Number(byId("weekday-start").value),
    weekday_end_h: Number(byId("weekday-end").value),
    weekend_start_h: Number(byId("weekend-start").value),
    weekend_end_h: Number(byId("weekend-end").value),
  };
  if (locationCoords) {
    payload.latitude = locationCoords.lat;
    payload.longitude = locationCoords.lon;
  }

  setStatus("Calcul du plan en cours...");
  try {
    const data = await callApi("/api/plan", payload);
    currentPlan = data.plan;
    selectedSlots.clear();
    const loc = currentPlan.location;
    locationCoords = { lat: loc.latitude, lon: loc.longitude };
    updateMarker(loc.latitude, loc.longitude, loc.label);
    renderHeatmap(currentPlan);
    renderRecommendations(currentPlan);
    renderSelected(currentPlan);
    setStatus("Plan calculé.");
  } catch (e) {
    setStatus(`Erreur plan: ${e.message}`, true);
  }
}

window.addEventListener("DOMContentLoaded", () => {
  initMap();
  byId("address").addEventListener("input", () => {
    if (_settingAddressProgrammatically) return;
    locationCoords = null;
  });
  byId("btn-geocode").addEventListener("click", handleGeocode);
  byId("plan-form").addEventListener("submit", handlePlanSubmit);
});
