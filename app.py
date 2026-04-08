"""
DataBase B2B — Mappa web dei lead locali.

Avvio:
    source .venv/bin/activate
    python app.py
    # oppure: bash scripts/run_map.sh

La prima volta popola il database con:
    python scripts/importa_db.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from flask import Flask, jsonify

from finder_clienti_varesotto.db import count_leads, init_db, query_leads
from finder_clienti_varesotto.paths import DB_PATH

app = Flask(__name__)

HTML_PAGE = """<!DOCTYPE html>
<html lang="it">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>DataBase B2B — Mappa Lead</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { display: flex; height: 100vh; font-family: system-ui, -apple-system, sans-serif; font-size: 13px; color: #212529; }

    #sidebar {
      width: 230px; min-width: 230px;
      background: #f8f9fa;
      padding: 14px 12px;
      overflow-y: auto;
      border-right: 1px solid #dee2e6;
      display: flex; flex-direction: column; gap: 0;
    }

    #map { flex: 1; }

    h1 { font-size: 15px; font-weight: 700; margin-bottom: 2px; }
    #counter { font-size: 12px; color: #6c757d; margin-bottom: 2px; }
    #hotlist-counter { font-size: 11px; color: #f4a261; font-weight: 600; margin-bottom: 12px; }

    .section-title {
      font-weight: 600; font-size: 10px; text-transform: uppercase;
      letter-spacing: 0.6px; color: #868e96;
      margin: 10px 0 5px;
      padding-top: 10px;
      border-top: 1px solid #e9ecef;
    }
    .section-title:first-of-type { border-top: none; padding-top: 0; margin-top: 6px; }

    label { display: flex; align-items: center; gap: 7px; margin-bottom: 3px; cursor: pointer; user-select: none; }
    label:hover { color: #495057; }
    input[type=checkbox] { cursor: pointer; accent-color: #495057; }

    .dot { width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0; }
    .star-badge { color: #FFD700; font-size: 12px; line-height: 1; text-shadow: 0 0 1px #888; }

    .divider { border: none; border-top: 1px solid #e9ecef; margin: 8px 0; }

    #btn-reset {
      margin-top: 12px; padding: 5px 10px; font-size: 12px;
      background: #fff; border: 1px solid #ced4da; border-radius: 4px;
      cursor: pointer; color: #495057; width: 100%;
    }
    #btn-reset:hover { background: #e9ecef; }

    #no-data {
      display: none; padding: 20px; text-align: center;
      color: #6c757d; font-size: 12px; line-height: 1.6;
    }
    #no-data code { background: #e9ecef; padding: 2px 5px; border-radius: 3px; font-size: 11px; }
  </style>
</head>
<body>
  <div id="sidebar">
    <h1>DataBase B2B</h1>
    <div id="counter">Caricamento...</div>
    <div id="hotlist-counter"></div>

    <div class="section-title">Priorità</div>
    <div id="priority-filters"></div>

    <div class="section-title">Categoria</div>
    <div id="category-filters"></div>

    <div class="section-title">Filtri rapidi</div>
    <label><input type="checkbox" id="toggle-senza-sito"> Solo senza sito web</label>
    <label><input type="checkbox" id="toggle-hotlist">
      <span class="star-badge">★</span> Solo hotlist arricchita
    </label>

    <button id="btn-reset">Azzera filtri</button>

    <div id="no-data">
      Nessun dato nel database.<br><br>
      Esegui:<br>
      <code>python scripts/importa_db.py</code>
    </div>
  </div>

  <div id="map"></div>

  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script>
    const PRIORITY_COLORS = {
      "ALTISSIMA":   "#e63946",
      "ALTA":        "#f4a261",
      "MEDIA":       "#2a9d8f",
      "BASSA":       "#adb5bd",
      "MOLTO BASSA": "#dee2e6"
    };
    const PRIORITY_ORDER = ["ALTISSIMA", "ALTA", "MEDIA", "BASSA", "MOLTO BASSA"];

    // Mappa
    const map = L.map("map").setView([45.7755, 8.8872], 12);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "© <a href='https://www.openstreetmap.org/copyright'>OpenStreetMap</a>"
    }).addTo(map);

    // Punto di riferimento
    L.circleMarker([45.7755, 8.8872], {
      radius: 7, color: "#343a40", fillColor: "#343a40", fillOpacity: 1, weight: 2
    }).addTo(map).bindPopup("<b>Vedano Olona</b><br>Punto di riferimento");

    let allLeads = [];
    let markers = [];

    function makePopup(l) {
      let h = "<b>" + l.nome + "</b><br>";
      h += l.categoria;
      if (l.comune && l.comune !== "N/D") h += " &middot; " + l.comune;
      h += "<br>";
      if (l.telefono && l.telefono !== "N/D") h += "&#128222; " + l.telefono + "<br>";
      if (l.sito && l.sito !== "N/D")
        h += "&#127760; <a href='" + l.sito + "' target='_blank' rel='noopener'>" + l.sito + "</a><br>";
      h += "&#128205; " + l.distanza_km + " km &nbsp;&middot;&nbsp; <b>" + l.priorita + "</b>";
      if (l.in_hotlist) {
        h += "<hr style='margin:6px 0; border-color:#dee2e6'>";
        if (l.stato) h += "<b>Stato:</b> " + l.stato + "<br>";
        if (l.proposta) h += "<b>Proposta:</b> " + l.proposta + "<br>";
        if (l.rating) h += "&#11088; " + l.rating + "<br>";
        if (l.email && l.email !== "N/D") h += "&#128231; " + l.email;
      }
      return h;
    }

    function createMarker(l) {
      let marker;
      if (l.in_hotlist) {
        const icon = L.divIcon({
          html: "<div style='font-size:18px;line-height:1;color:#FFD700;text-shadow:0 0 2px rgba(0,0,0,0.6);'>&#9733;</div>",
          className: "",
          iconSize: [20, 20],
          iconAnchor: [10, 10]
        });
        marker = L.marker([l.lat, l.lon], { icon });
      } else {
        const color = PRIORITY_COLORS[l.priorita] || "#adb5bd";
        marker = L.circleMarker([l.lat, l.lon], {
          radius: 5, color: color, fillColor: color, fillOpacity: 0.8, weight: 1
        });
      }
      marker.bindPopup(makePopup(l), { maxWidth: 280 });
      marker._lead = l;
      return marker;
    }

    function buildFilterUI(leads) {
      const priorities = PRIORITY_ORDER.filter(p => leads.some(l => l.priorita === p));
      const categories = [...new Set(leads.map(l => l.categoria))].sort();

      const pDiv = document.getElementById("priority-filters");
      priorities.forEach(p => {
        const color = PRIORITY_COLORS[p] || "#adb5bd";
        const lbl = document.createElement("label");
        lbl.innerHTML =
          "<input type='checkbox' class='f-priority' value='" + p + "' checked>" +
          "<span class='dot' style='background:" + color + "'></span>" + p;
        pDiv.appendChild(lbl);
      });

      const cDiv = document.getElementById("category-filters");
      categories.forEach(c => {
        const lbl = document.createElement("label");
        lbl.innerHTML = "<input type='checkbox' class='f-category' value='" + c + "' checked>" + c;
        cDiv.appendChild(lbl);
      });

      document.querySelectorAll(".f-priority, .f-category, #toggle-senza-sito, #toggle-hotlist")
        .forEach(el => el.addEventListener("change", applyFilters));

      document.getElementById("btn-reset").addEventListener("click", () => {
        document.querySelectorAll(".f-priority, .f-category").forEach(el => el.checked = true);
        document.getElementById("toggle-senza-sito").checked = false;
        document.getElementById("toggle-hotlist").checked = false;
        applyFilters();
      });
    }

    function applyFilters() {
      const activePriority = new Set(
        [...document.querySelectorAll(".f-priority:checked")].map(e => e.value)
      );
      const activeCategory = new Set(
        [...document.querySelectorAll(".f-category:checked")].map(e => e.value)
      );
      const soloSenzaSito = document.getElementById("toggle-senza-sito").checked;
      const soloHotlist   = document.getElementById("toggle-hotlist").checked;

      let visible = 0, hotlistVisible = 0;
      markers.forEach(m => {
        const l = m._lead;
        const show =
          activePriority.has(l.priorita) &&
          activeCategory.has(l.categoria) &&
          (!soloSenzaSito || l.ha_sito === "NO") &&
          (!soloHotlist   || l.in_hotlist);
        if (show) { m.addTo(map); visible++; if (l.in_hotlist) hotlistVisible++; }
        else { map.removeLayer(m); }
      });

      document.getElementById("counter").textContent = visible + " lead visibili";
      const hl = document.getElementById("hotlist-counter");
      hl.textContent = hotlistVisible > 0 ? "★ " + hotlistVisible + " in hotlist" : "";
    }

    // Caricamento dati
    fetch("/api/leads")
      .then(r => r.json())
      .then(data => {
        if (!data.length) {
          document.getElementById("counter").textContent = "Nessun dato";
          document.getElementById("no-data").style.display = "block";
          return;
        }
        allLeads = data;
        buildFilterUI(data);
        markers = data.map(createMarker);
        markers.forEach(m => m.addTo(map));
        const hotlistCount = data.filter(l => l.in_hotlist).length;
        document.getElementById("counter").textContent = data.length + " lead visibili";
        if (hotlistCount)
          document.getElementById("hotlist-counter").textContent = "★ " + hotlistCount + " in hotlist";
      })
      .catch(err => {
        document.getElementById("counter").textContent = "Errore caricamento";
        console.error(err);
      });
  </script>
</body>
</html>
"""


@app.route("/")
def index():
    return HTML_PAGE


@app.route("/api/leads")
def api_leads():
    leads = query_leads(db_path=DB_PATH)
    result = [
        {
            "lat": r["lat"],
            "lon": r["lon"],
            "nome": r["nome"] or "",
            "priorita": r["priorita"] or "",
            "categoria": r["categoria"] or "",
            "comune": r["comune"] or "",
            "telefono": r["telefono"] or "",
            "sito": r["sito"] or "",
            "ha_sito": r["ha_sito"] or "",
            "distanza_km": round(r["distanza_km"] or 0, 2),
            "in_hotlist": bool(r["in_hotlist"]),
            "stato": r["stato"] or "",
            "proposta": r["proposta"] or "",
            "criticita": r["criticita"] or "",
            "rating": r["rating"] or "",
            "email": r["email"] or "",
        }
        for r in leads
        if r["lat"] is not None and r["lon"] is not None
    ]
    return jsonify(result)


@app.route("/api/stats")
def api_stats():
    leads = query_leads(db_path=DB_PATH)
    total = len(leads)
    with_coords = sum(1 for r in leads if r["lat"] and r["lon"])
    in_hotlist = sum(1 for r in leads if r["in_hotlist"])
    senza_sito = sum(1 for r in leads if r["ha_sito"] == "NO")
    by_priority = {}
    for r in leads:
        p = r["priorita"] or "N/D"
        by_priority[p] = by_priority.get(p, 0) + 1
    return jsonify({
        "total": total,
        "with_coords": with_coords,
        "in_hotlist": in_hotlist,
        "senza_sito": senza_sito,
        "by_priority": by_priority,
    })


if __name__ == "__main__":
    init_db(DB_PATH)
    n = count_leads(DB_PATH)
    if n == 0:
        print("⚠  Database vuoto. Esegui prima: python scripts/importa_db.py")
    else:
        print(f"✓  {n} attività nel database")
    print("→  Apri http://localhost:5000\n")
    app.run(debug=False, port=5000)
