"""
Morpheus — Mappa web dei lead locali.

Avvio:
    .venv/bin/python3 app.py
    # oppure: bash scripts/run_map.sh

La prima volta popola il database con:
    .venv/bin/python3 scripts/importa_db.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from threading import Lock, Thread
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).parent / "src"))

from flask import Flask, Response, jsonify, request, send_from_directory

from morpheus.db import (
    count_leads,
    create_dataset_from_reference,
    create_manual_lead,
    delete_dataset,
    export_leads_csv,
    get_active_dataset,
    get_job,
    import_from_csv,
    init_db,
    list_comuni,
    list_datasets,
    mark_stale_jobs,
    query_leads,
    save_job,
    update_lead_fields,
    update_leads_bulk,
)
from morpheus.facebook_enrichment import enrich_leads_facebook
from morpheus.site_checker import check_sites_batch
from morpheus.url_parser import geocode_address, parse_lead_url
from morpheus.paths import DB_PATH, DEFAULT_HOTLIST, DEFAULT_OSM_OUTPUT
from morpheus.osm_finder import DEFAULT_PROVINCE_QUERY

app = Flask(__name__)
BASE_DIR = Path(__file__).parent
FRONTEND_DIST_DIR = BASE_DIR / "frontend" / "dist"
FRONTEND_INDEX = FRONTEND_DIST_DIR / "index.html"
# Lock leggero usato solo per serializzare le lettura-scrittura in-process
_JOB_LOCK = Lock()


def _list_arg(name: str) -> list[str]:
    values = [value.strip() for value in request.args.getlist(name) if value.strip()]
    if len(values) == 1 and "," in values[0]:
        values = [value.strip() for value in values[0].split(",") if value.strip()]
    return values


def _bool_arg(name: str) -> bool:
    return request.args.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _int_arg(name: str) -> int | None:
    raw = request.args.get(name, "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if value > 0 else None


def _save_job(job_id: str, payload: dict, job_type: str = "populate") -> None:
    with _JOB_LOCK:
        save_job(job_id, payload, job_type=job_type, db_path=DB_PATH)


def _get_job(job_id: str) -> dict | None:
    row = get_job(job_id, db_path=DB_PATH)
    if row is None:
        return None
    result = {
        "job_id": row["job_id"],
        "job_type": row.get("job_type", "populate"),
        "status": row["status"],
        "progress": row.get("progress", 0),
        "stage": row.get("stage", ""),
        "message": row.get("message", ""),
        "error": row.get("error", ""),
        "dataset_id": row.get("dataset_id", ""),
    }
    extra = row.get("_result") or {}
    if extra:
        job_type = row.get("job_type", "populate")
        if job_type == "populate":
            result["dataset"] = extra
        else:
            result["result"] = extra
    return result


def _population_worker(
    job_id: str,
    *,
    reference_query: str,
    province_query: str,
    dataset_id: str | None,
    append_to_existing: bool,
    limit: int,
) -> None:
    def on_progress(event: dict) -> None:
        _save_job(
            job_id,
            {
                "status": "running",
                "progress": event.get("progress", 0),
                "stage": event.get("stage", ""),
                "message": event.get("message", "Popolamento in corso."),
                "dataset_id": dataset_id or "",
            },
        )

    try:
        dataset = create_dataset_from_reference(
            reference_query,
            dataset_id=dataset_id,
            province_query=province_query,
            limit=limit,
            db_path=DB_PATH,
            replace_dataset=not append_to_existing,
            progress_callback=on_progress,
        )
    except Exception as exc:
        _save_job(
            job_id,
            {
                "status": "error",
                "progress": 100,
                "stage": "error",
                "message": str(exc),
                "error": str(exc),
                "dataset_id": dataset_id or "",
            },
        )
        return

    _save_job(
        job_id,
        {
            "status": "completed",
            "progress": 100,
            "stage": "done",
            "message": f"Dataset pronto: {dataset['label']}",
            "dataset_id": dataset.get("dataset_id", ""),
            "result_json": dataset,
        },
    )


def _facebook_enrichment_worker(
    job_id: str,
    *,
    dataset_id: str,
) -> None:
    def on_progress(event: dict) -> None:
        _save_job(
            job_id,
            {
                "status": "running",
                "progress": event.get("progress", 0),
                "stage": event.get("stage", ""),
                "message": event.get("message", "Ricerca Facebook in corso..."),
                "dataset_id": dataset_id,
            },
            job_type="facebook_enrichment",
        )

    try:
        result = enrich_leads_facebook(
            dataset_id=dataset_id,
            db_path=DB_PATH,
            progress_callback=on_progress,
        )
    except Exception as exc:
        _save_job(
            job_id,
            {
                "status": "error",
                "progress": 100,
                "stage": "error",
                "message": str(exc),
                "error": str(exc),
                "dataset_id": dataset_id,
            },
            job_type="facebook_enrichment",
        )
        return

    _save_job(
        job_id,
        {
            "status": "completed",
            "progress": 100,
            "stage": "done",
            "message": (
                f"Facebook completato: {result['enriched']} profili trovati "
                f"su {result['total']} lead."
            ),
            "dataset_id": dataset_id,
            "result_json": result,
        },
        job_type="facebook_enrichment",
    )


HTML_PAGE = """<!DOCTYPE html>
<html lang="it">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Morpheus — Mappa Lead</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap">
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { display: flex; height: 100vh; font-family: 'Inter', system-ui, -apple-system, sans-serif; font-size: 13px; color: #1e293b; }

    :root {
      --brand:        #264653;
      --brand-dark:   #1a3340;
      --brand-light:  #e8f0f3;
      --accent:       #2a9d8f;
      --accent-light: #e6f4f2;
      --danger:       #e63946;
      --warn:         #f4a261;
      --gold:         #d4a017;
      --bg:           #f1f5f9;
      --surface:      #ffffff;
      --surface-2:    #f8fafc;
      --border:       #e2e8f0;
      --border-strong:#cbd5e1;
      --text:         #0f172a;
      --text-2:       #475569;
      --text-3:       #94a3b8;
      --radius-sm:    6px;
      --radius-md:    10px;
      --shadow-sm:    0 1px 3px rgba(0,0,0,.06), 0 1px 2px rgba(0,0,0,.04);
      --shadow-md:    0 4px 12px rgba(0,0,0,.08);
    }

    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { display: flex; height: 100vh; font-family: 'Inter', system-ui, -apple-system, sans-serif; font-size: 13px; color: var(--text); background: var(--bg); }

    /* ── Sidebar ── */
    #sidebar {
      width: 272px; min-width: 272px;
      background: var(--surface);
      padding: 16px 14px;
      overflow-y: auto;
      border-right: 1px solid var(--border);
      display: flex; flex-direction: column; gap: 0;
      box-shadow: var(--shadow-sm);
      z-index: 10;
    }

    #map { flex: 1; min-width: 0; }

    /* ── Lead list panel ── */
    #lead-list-panel {
      width: 348px; min-width: 348px;
      background: var(--surface);
      border-left: 1px solid var(--border);
      display: flex; flex-direction: column;
      box-shadow: var(--shadow-sm);
      z-index: 10;
    }

    #lead-list-header {
      padding: 14px 14px 10px;
      border-bottom: 1px solid var(--border);
      background: var(--surface-2);
    }

    #lead-list-title { font-size: 12px; font-weight: 700; letter-spacing: .3px; text-transform: uppercase; color: var(--text-2); margin-bottom: 2px; }
    #lead-list-counter { font-size: 12px; color: var(--text-2); font-weight: 500; }

    #lead-list {
      flex: 1;
      overflow-y: auto;
      padding: 10px;
      display: flex;
      flex-direction: column;
      gap: 6px;
    }

    #lead-list-empty {
      display: none;
      padding: 24px 14px;
      color: var(--text-3);
      font-size: 12px;
      line-height: 1.6;
      text-align: center;
    }

    /* ── Lead cards ── */
    .lead-item {
      width: 100%;
      border: 1px solid var(--border);
      background: var(--surface);
      border-radius: var(--radius-md);
      padding: 10px 11px;
      text-align: left;
      cursor: pointer;
      transition: border-color 0.18s ease, box-shadow 0.18s ease, background 0.18s ease;
    }

    .lead-item:hover {
      border-color: var(--border-strong);
      box-shadow: var(--shadow-md);
    }

    .lead-item.active {
      border-color: var(--brand);
      background: var(--brand-light);
      box-shadow: 0 0 0 2px rgba(38, 70, 83, 0.1);
    }

    .lead-item-head {
      display: flex;
      align-items: flex-start;
      gap: 9px;
      margin-bottom: 7px;
    }

    .lead-item-index {
      width: 22px; height: 22px;
      border-radius: 50%;
      background: var(--brand);
      color: #fff;
      font-size: 10px;
      font-weight: 700;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      flex-shrink: 0;
      margin-top: 2px;
      letter-spacing: -.3px;
    }

    .lead-item-main { min-width: 0; flex: 1; }
    .lead-item-name {
      font-size: 13px;
      font-weight: 600;
      color: var(--text);
      line-height: 1.3;
      margin-bottom: 2px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .lead-item-sub {
      font-size: 11px;
      color: var(--text-2);
      line-height: 1.4;
      margin-bottom: 6px;
      display: flex;
      align-items: center;
      gap: 4px;
      flex-wrap: wrap;
    }

    .lead-item-footer {
      display: flex;
      align-items: center;
      gap: 6px;
      flex-wrap: wrap;
    }

    .badge-priority {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      font-size: 10px;
      font-weight: 600;
      padding: 2px 7px;
      border-radius: 999px;
      letter-spacing: .2px;
    }

    .lead-detail-row {
      display: flex;
      align-items: center;
      gap: 5px;
      font-size: 11px;
      color: var(--text-2);
      margin-top: 4px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .lead-detail-row svg { flex-shrink: 0; color: var(--text-3); }

    .tag-nosito {
      font-size: 10px;
      font-weight: 600;
      color: var(--accent);
      background: var(--accent-light);
      padding: 2px 6px;
      border-radius: 999px;
    }

    .tag-hotlist {
      font-size: 10px;
      font-weight: 600;
      color: var(--gold);
      background: #fef9ec;
      padding: 2px 6px;
      border-radius: 999px;
    }

    /* ── Sidebar header ── */
    #sidebar-header { margin-bottom: 14px; }
    h1 { font-size: 15px; font-weight: 700; color: var(--text); letter-spacing: -.2px; margin-bottom: 1px; }
    h1 span { color: var(--brand); }
    #counter { font-size: 11px; color: var(--text-2); font-weight: 500; margin-bottom: 1px; }
    #hotlist-counter { font-size: 11px; color: var(--gold); font-weight: 600; }

    /* ── Section titles ── */
    .section-title {
      font-weight: 600; font-size: 10px; text-transform: uppercase;
      letter-spacing: .8px; color: var(--text-3);
      margin: 14px 0 6px;
      padding-top: 14px;
      border-top: 1px solid var(--border);
    }

    .section-title:first-of-type { border-top: none; padding-top: 0; margin-top: 2px; }

    /* ── Form elements ── */
    label { display: flex; align-items: center; gap: 7px; margin-bottom: 4px; cursor: pointer; user-select: none; font-size: 12px; color: var(--text-2); }
    label:hover { color: var(--text); }
    input[type=checkbox] { cursor: pointer; accent-color: var(--brand); width: 13px; height: 13px; }
    select, input[type=text] { cursor: pointer; font-family: inherit; }

    .dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
    .star-badge { color: var(--gold); font-size: 12px; line-height: 1; }

    .field, .field-static {
      width: 100%;
      padding: 7px 9px;
      border: 1px solid var(--border-strong);
      border-radius: var(--radius-sm);
      background: var(--surface);
      color: var(--text);
      font-size: 12px;
      font-family: inherit;
      margin-bottom: 7px;
      transition: border-color .15s, box-shadow .15s;
      outline: none;
    }

    .field:focus {
      border-color: var(--brand);
      box-shadow: 0 0 0 3px rgba(38, 70, 83, 0.12);
    }

    .field-static {
      background: var(--surface-2);
      line-height: 1.5;
      color: var(--text-2);
      cursor: default;
      font-size: 11px;
    }

    .hint {
      font-size: 11px;
      color: var(--text-3);
      line-height: 1.5;
      margin-bottom: 8px;
    }

    .btn-primary, #btn-reset {
      margin-top: 6px;
      padding: 8px 10px;
      font-size: 12px;
      font-weight: 600;
      font-family: inherit;
      background: var(--brand);
      border: 1px solid var(--brand);
      border-radius: var(--radius-sm);
      cursor: pointer;
      color: #fff;
      width: 100%;
      letter-spacing: .1px;
      transition: background .15s, box-shadow .15s;
    }

    .btn-primary:hover { background: var(--brand-dark); box-shadow: var(--shadow-sm); }
    .btn-primary:disabled { opacity: 0.5; cursor: wait; }

    #btn-reset {
      background: var(--surface);
      color: var(--text-2);
      border-color: var(--border-strong);
    }

    #btn-reset:hover { background: var(--surface-2); }

    /* ── Progress ── */
    #populate-progress {
      display: none;
      width: 100%;
      height: 4px;
      background: var(--border);
      border-radius: 999px;
      overflow: hidden;
      margin-top: 8px;
    }
    #populate-progress-bar {
      height: 100%;
      width: 0%;
      background: var(--brand);
      transition: width 0.5s ease;
      border-radius: 999px;
    }
    #populate-status {
      margin-top: 6px;
      font-size: 11px;
      color: var(--text-3);
      line-height: 1.5;
      min-height: 16px;
      word-break: break-word;
    }
    #populate-status.error { color: var(--danger); }

    /* ── No data ── */
    #no-data {
      display: none; padding: 20px; text-align: center;
      color: var(--text-3); font-size: 12px; line-height: 1.6;
    }

    #no-data code { background: var(--surface-2); padding: 2px 6px; border-radius: 4px; font-size: 11px; border: 1px solid var(--border); }

    /* ── Responsive ── */
    @media (max-width: 1180px) {
      body { flex-direction: column; height: auto; min-height: 100vh; }
      #sidebar, #lead-list-panel {
        width: 100%;
        min-width: 0;
        border-right: none;
        border-left: none;
        box-shadow: none;
      }
      #sidebar { border-bottom: 1px solid var(--border); }
      #lead-list-panel { border-top: 1px solid var(--border); min-height: 36vh; }
      #map { min-height: 46vh; }
    }
  </style>
</head>
<body>
  <div id="sidebar">
    <div id="sidebar-header">
      <h1>Morpheus</h1>
      <div id="counter">Caricamento...</div>
      <div id="hotlist-counter"></div>
    </div>

    <div class="section-title">Dataset attivo</div>
    <select id="dataset-select" class="field"></select>
    <div id="dataset-meta" class="field-static">Caricamento dataset...</div>

    <div class="section-title">Nuovo popolamento</div>
    <input id="reference-input" class="field" type="text" placeholder="Centro, es. Busto Arsizio, Varese, Lombardia, Italia">
    <input id="province-input" class="field" type="text" value="Provincia di Varese, Lombardia, Italia">
    <div class="hint">Crea un nuovo dataset da un punto di partenza diverso o aggiorna quello corrente.</div>
    <button id="btn-populate" class="btn-primary" type="button">Avvia popolamento</button>
    <div id="populate-progress"><div id="populate-progress-bar"></div></div>
    <div id="populate-status"></div>

    <div class="section-title">Priorità</div>
    <div id="priority-filters"></div>

    <div class="section-title">Categoria</div>
    <div id="category-filters"></div>

    <div class="section-title">Filtri rapidi</div>
    <label><input type="checkbox" id="toggle-senza-sito"> Solo senza sito web</label>
    <label><input type="checkbox" id="toggle-hotlist">
      <span class="star-badge">★</span> Solo hotlist arricchita
    </label>

    <button id="btn-reset" type="button" style="margin-top:10px;">Azzera filtri</button>

    <div id="no-data">
      Nessun dato nel database.<br><br>
      Esegui:<br>
      <code>.venv/bin/python3 scripts/importa_db.py</code>
    </div>
  </div>

  <div id="map"></div>

  <div id="lead-list-panel">
    <div id="lead-list-header">
      <div id="lead-list-title">Elenco lead</div>
      <div id="lead-list-counter">Caricamento...</div>
    </div>
    <div id="lead-list"></div>
    <div id="lead-list-empty">
      <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" style="margin:0 auto 8px;display:block;opacity:.35"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
      Nessun lead con i filtri correnti.
    </div>
  </div>

  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script>
    const PRIORITY_COLORS = {
      "ALTISSIMA": "#e63946",
      "ALTA": "#f4a261",
      "MEDIA": "#2a9d8f",
      "BASSA": "#adb5bd",
      "MOLTO BASSA": "#dee2e6"
    };
    const PRIORITY_ORDER = ["ALTISSIMA", "ALTA", "MEDIA", "BASSA", "MOLTO BASSA"];

    const SVG = {
      phone: '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 16.92v3a2 2 0 01-2.18 2 19.79 19.79 0 01-8.63-3.07A19.5 19.5 0 013.07 9.8a19.79 19.79 0 01-3.07-8.63A2 2 0 012 0h3a2 2 0 012 1.72 12.84 12.84 0 00.7 2.81 2 2 0 01-.45 2.11L6.09 7.91a16 16 0 006 6l1.27-1.27a2 2 0 012.11-.45 12.84 12.84 0 002.81.7A2 2 0 0122 14z"/></svg>',
      globe: '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 014 10 15.3 15.3 0 01-4 10 15.3 15.3 0 01-4-10 15.3 15.3 0 014-10z"/></svg>',
      pin:   '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0118 0z"/><circle cx="12" cy="10" r="3"/></svg>',
      mail:  '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg>',
      star:  '<svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" stroke="none"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>',
      target:'<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/></svg>',
    };

    const PRIORITY_BG = {
      "ALTISSIMA":  "rgba(230,57,70,.12)",
      "ALTA":       "rgba(244,162,97,.15)",
      "MEDIA":      "rgba(42,157,143,.12)",
      "BASSA":      "rgba(148,163,184,.15)",
      "MOLTO BASSA":"rgba(226,232,240,.4)",
    };

    const map = L.map("map").setView([45.7755, 8.8872], 12);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "© <a href='https://www.openstreetmap.org/copyright'>OpenStreetMap</a>"
    }).addTo(map);

    const referenceMarker = L.circleMarker([45.7755, 8.8872], {
      radius: 8,
      color: "#264653",
      fillColor: "#264653",
      fillOpacity: 1,
      weight: 2.5
    }).addTo(map).bindPopup("<b style='font-family:Inter,sans-serif'>Vedano Olona</b><br><span style='font-size:11px;color:#64748b;font-family:Inter,sans-serif'>Punto di riferimento</span>");

    let allLeads = [];
    let markers = [];
    let markerById = new Map();
    let datasets = [];
    let activeDatasetId = null;
    let selectedLeadId = null;
    let focusRing = null;
    let focusRingTimeout = null;

    function makePopup(lead) {
      const row = (icon, val) =>
        "<div style='display:flex;align-items:center;gap:5px;margin-top:3px;color:#475569;font-size:11px'>" +
        "<span style='color:#94a3b8;flex-shrink:0'>" + icon + "</span>" + val + "</div>";

      let html = "<div style='font-family:Inter,system-ui,sans-serif;font-size:12px;min-width:180px'>";
      html += "<b style='font-size:13px;color:#0f172a'>" + lead.nome + "</b>";
      html += "<div style='font-size:11px;color:#64748b;margin-top:1px'>" + lead.categoria;
      if (lead.comune && lead.comune !== "N/D") html += " &middot; " + lead.comune;
      html += "</div>";

      if (lead.telefono && lead.telefono !== "N/D") html += row(SVG.phone, lead.telefono);
      if (lead.sito && lead.sito !== "N/D") {
        const sito = lead.sito.replace(/^https?:\\/\\//, "").replace(/\\/$/, "");
        html += row(SVG.globe, "<a href='" + lead.sito + "' target='_blank' rel='noopener' style='color:#264653'>" + sito + "</a>");
      }
      html += row(SVG.pin, lead.distanza_km + " km &middot; <b style='color:#0f172a'>" + lead.priorita + "</b>");

      if (lead.rilevanza_score !== null && lead.rilevanza_score > 0) {
        html += row(SVG.target, "Rilevanza: <b style='color:#0f172a'>" + lead.rilevanza_score + "/10</b>");
      }
      if (lead.in_hotlist) {
        html += "<hr style='margin:7px 0;border:none;border-top:1px solid #e2e8f0'>";
        if (lead.stato) html += row(SVG.star, lead.stato);
        if (lead.proposta) html += "<div style='font-size:11px;color:#475569;margin-top:3px'><b>Proposta:</b> " + lead.proposta + "</div>";
        if (lead.rating) html += "<div style='font-size:11px;color:#d4a017;margin-top:3px;font-weight:600'>" + lead.rating + "</div>";
        if (lead.email && lead.email !== "N/D") html += row(SVG.mail, lead.email);
      }
      html += "</div>";
      return html;
    }

    function setSelectedLead(leadId, scrollIntoView) {
      selectedLeadId = leadId;
      document.querySelectorAll(".lead-item").forEach(el => {
        el.classList.toggle("active", el.dataset.leadId === leadId);
      });
      if (scrollIntoView) {
        const active = document.querySelector(".lead-item.active");
        if (active) active.scrollIntoView({ block: "nearest", behavior: "smooth" });
      }
    }

    function flashLeadLocation(lat, lon) {
      if (focusRing) map.removeLayer(focusRing);
      if (focusRingTimeout) clearTimeout(focusRingTimeout);
      focusRing = L.circleMarker([lat, lon], {
        radius: 12,
        color: "#264653",
        weight: 2,
        fillOpacity: 0
      }).addTo(map);
      focusRingTimeout = setTimeout(() => {
        if (focusRing) map.removeLayer(focusRing);
        focusRing = null;
      }, 1600);
    }

    function focusLead(leadId) {
      const marker = markerById.get(leadId);
      if (!marker) return;
      const lead = marker._lead;
      setSelectedLead(leadId, true);
      map.setView([lead.lat, lead.lon], Math.max(map.getZoom(), 15), { animate: true });
      marker.openPopup();
      if (marker.bringToFront) marker.bringToFront();
      flashLeadLocation(lead.lat, lead.lon);
    }

    function createMarker(lead) {
      let marker;
      if (lead.in_hotlist) {
        const icon = L.divIcon({
          html: "<div style='font-size:18px;line-height:1;color:#FFD700;text-shadow:0 0 2px rgba(0,0,0,0.6);'>&#9733;</div>",
          className: "",
          iconSize: [20, 20],
          iconAnchor: [10, 10]
        });
        marker = L.marker([lead.lat, lead.lon], { icon });
      } else {
        const color = PRIORITY_COLORS[lead.priorita] || "#adb5bd";
        marker = L.circleMarker([lead.lat, lead.lon], {
          radius: 5,
          color: color,
          fillColor: color,
          fillOpacity: 0.8,
          weight: 1
        });
      }
      marker.bindPopup(makePopup(lead), { maxWidth: 280 });
      marker._lead = lead;
      marker.on("click", () => setSelectedLead(lead._id, true));
      return marker;
    }

    function renderLeadList(leads) {
      const list = document.getElementById("lead-list");
      const empty = document.getElementById("lead-list-empty");
      const counter = document.getElementById("lead-list-counter");
      counter.textContent = leads.length + " lead";

      if (!leads.some(lead => lead._id === selectedLeadId)) {
        selectedLeadId = null;
      }

      list.innerHTML = "";
      if (!leads.length) {
        empty.style.display = "block";
        return;
      }

      empty.style.display = "none";
      const fragment = document.createDocumentFragment();
      leads.forEach((lead, index) => {
        const item = document.createElement("button");
        item.type = "button";
        item.className = "lead-item" + (lead._id === selectedLeadId ? " active" : "");
        item.dataset.leadId = lead._id;

        const priorityColor = PRIORITY_COLORS[lead.priorita] || "#94a3b8";
        const priorityBg    = PRIORITY_BG[lead.priorita]    || "rgba(148,163,184,.15)";
        const comune  = lead.comune  && lead.comune  !== "N/D" ? lead.comune  : "";
        const telefono = lead.telefono && lead.telefono !== "N/D" ? lead.telefono : "";
        const sito    = lead.sito    && lead.sito    !== "N/D"
          ? lead.sito.replace(/^https?:\\/\\//, "").replace(/\\/$/, "") : "";

        const hotlistBadge = lead.in_hotlist
          ? "<span class='tag-hotlist' style='display:inline-flex;align-items:center;gap:3px'>" +
            "<span style='color:#d4a017'>" + SVG.star + "</span>Hotlist</span>"
          : "";
        const nositoBadge = lead.ha_sito === "NO"
          ? "<span class='tag-nosito'>Senza sito</span>"
          : "";

        const sub = [lead.categoria, comune].filter(Boolean).join(" · ");
        const telRow = telefono
          ? "<div class='lead-detail-row'>" + SVG.phone + telefono + "</div>"
          : "";
        const sitoRow = sito
          ? "<div class='lead-detail-row'>" + SVG.globe + "<span style='overflow:hidden;text-overflow:ellipsis'>" + sito + "</span></div>"
          : "";

        item.innerHTML =
          "<div class='lead-item-head'>" +
            "<span class='lead-item-index'>" + (index + 1) + "</span>" +
            "<div class='lead-item-main'>" +
              "<div class='lead-item-name'>" + lead.nome + "</div>" +
              "<div class='lead-item-sub'>" + sub + "</div>" +
            "</div>" +
          "</div>" +
          "<div class='lead-item-footer' style='margin-bottom:7px'>" +
            "<span class='badge-priority' style='color:" + priorityColor + ";background:" + priorityBg + "'>" +
              "<span class='dot' style='background:" + priorityColor + "'></span>" + lead.priorita +
            "</span>" +
            "<span style='font-size:10px;color:#94a3b8'>" + SVG.pin + " " + lead.distanza_km + " km</span>" +
            hotlistBadge + nositoBadge +
          "</div>" +
          telRow + sitoRow;

        item.addEventListener("click", () => focusLead(lead._id));
        fragment.appendChild(item);
      });
      list.appendChild(fragment);
    }

    function buildFilterUI(leads) {
      const priorities = PRIORITY_ORDER.filter(priority => leads.some(lead => lead.priorita === priority));
      const categories = [...new Set(leads.map(lead => lead.categoria))].sort();

      const priorityBox = document.getElementById("priority-filters");
      const categoryBox = document.getElementById("category-filters");
      priorityBox.innerHTML = "";
      categoryBox.innerHTML = "";

      priorities.forEach(priority => {
        const color = PRIORITY_COLORS[priority] || "#adb5bd";
        const label = document.createElement("label");
        label.innerHTML =
          "<input type='checkbox' class='f-priority' value='" + priority + "' checked>" +
          "<span class='dot' style='background:" + color + "'></span>" + priority;
        priorityBox.appendChild(label);
      });

      categories.forEach(category => {
        const label = document.createElement("label");
        label.innerHTML = "<input type='checkbox' class='f-category' value='" + category + "' checked>" + category;
        categoryBox.appendChild(label);
      });

      document.querySelectorAll(".f-priority, .f-category, #toggle-senza-sito, #toggle-hotlist")
        .forEach(el => el.addEventListener("change", applyFilters));
    }

    function applyFilters() {
      const activePriority = new Set(
        [...document.querySelectorAll(".f-priority:checked")].map(el => el.value)
      );
      const activeCategory = new Set(
        [...document.querySelectorAll(".f-category:checked")].map(el => el.value)
      );
      const soloSenzaSito = document.getElementById("toggle-senza-sito").checked;
      const soloHotlist = document.getElementById("toggle-hotlist").checked;

      let visible = 0;
      let hotlistVisible = 0;
      const visibleLeads = [];

      markers.forEach(marker => {
        const lead = marker._lead;
        const show =
          activePriority.has(lead.priorita) &&
          activeCategory.has(lead.categoria) &&
          (!soloSenzaSito || lead.ha_sito === "NO") &&
          (!soloHotlist || lead.in_hotlist);

        if (show) {
          marker.addTo(map);
          visible++;
          visibleLeads.push(lead);
          if (lead.in_hotlist) hotlistVisible++;
        } else {
          map.removeLayer(marker);
        }
      });

      document.getElementById("counter").textContent = visible + " lead visibili";
      document.getElementById("hotlist-counter").textContent =
        hotlistVisible > 0 ? "★ " + hotlistVisible + " in hotlist" : "";
      renderLeadList(visibleLeads);
    }

    function resetMapMarkers() {
      markers.forEach(marker => map.removeLayer(marker));
      markers = [];
      markerById = new Map();
      selectedLeadId = null;
      if (focusRing) {
        map.removeLayer(focusRing);
        focusRing = null;
      }
      if (focusRingTimeout) {
        clearTimeout(focusRingTimeout);
        focusRingTimeout = null;
      }
    }

    function updateDatasetMeta(dataset) {
      const meta = document.getElementById("dataset-meta");
      if (!dataset) {
        meta.innerHTML = "<span style='color:#94a3b8'>Nessun dataset disponibile</span>";
        return;
      }
      meta.innerHTML =
        "<b style='color:#0f172a'>" + dataset.label + "</b><br>" +
        "<span style='color:#64748b'>" + dataset.reference_query + "</span><br>" +
        "<span style='color:#475569'>" + dataset.lead_count + " lead</span>" +
        (dataset.hotlist_count > 0
          ? " &nbsp;<span style='color:#d4a017;font-weight:600'>★ " + dataset.hotlist_count + " hotlist</span>"
          : "") +
        (dataset.without_site_count > 0
          ? " &nbsp;<span style='color:#2a9d8f;font-size:10px'>· " + dataset.without_site_count + " senza sito</span>"
          : "");
    }

    function updateReferenceMarker(dataset) {
      if (!dataset || dataset.reference_lat === null || dataset.reference_lon === null) return;
      referenceMarker.setLatLng([dataset.reference_lat, dataset.reference_lon]);
      referenceMarker.bindPopup("<b>" + dataset.reference_name + "</b><br>Punto di riferimento");
      map.setView([dataset.reference_lat, dataset.reference_lon], 12);
    }

    async function loadDatasets(preferredDatasetId) {
      const response = await fetch("/api/datasets");
      const data = await response.json();
      datasets = Array.isArray(data) ? data : [];

      const select = document.getElementById("dataset-select");
      select.innerHTML = "";

      datasets.forEach(dataset => {
        const option = document.createElement("option");
        option.value = dataset.dataset_id;
        option.textContent = dataset.label + " (" + dataset.lead_count + ")";
        select.appendChild(option);
      });

      if (!datasets.length) {
        activeDatasetId = null;
        updateDatasetMeta(null);
        return null;
      }

      const nextDataset =
        datasets.find(dataset => dataset.dataset_id === preferredDatasetId) ||
        datasets.find(dataset => dataset.is_active) ||
        datasets[0];

      activeDatasetId = nextDataset.dataset_id;
      select.value = activeDatasetId;
      updateDatasetMeta(nextDataset);
      updateReferenceMarker(nextDataset);
      document.getElementById("reference-input").value = nextDataset.reference_query || "";
      document.getElementById("province-input").value = nextDataset.province_query || "Provincia di Varese, Lombardia, Italia";
      return activeDatasetId;
    }

    async function loadLeads(datasetId) {
      if (!datasetId) return;
      resetMapMarkers();
      const response = await fetch("/api/leads?dataset_id=" + encodeURIComponent(datasetId));
      const data = await response.json();
      allLeads = data.map((lead, index) => ({ ...lead, _id: String(index + 1) }));

      if (!allLeads.length) {
        document.getElementById("counter").textContent = "Nessun dato";
        document.getElementById("lead-list-counter").textContent = "Nessun lead";
        document.getElementById("lead-list-empty").style.display = "block";
        return;
      }

      buildFilterUI(allLeads);
      markers = allLeads.map(createMarker);
      markerById = new Map(markers.map(marker => [marker._lead._id, marker]));
      document.getElementById("toggle-senza-sito").checked = false;
      document.getElementById("toggle-hotlist").checked = false;
      applyFilters();
    }

    function setPopulateStatus(msg, isError) {
      const status = document.getElementById("populate-status");
      status.textContent = msg;
      status.className = isError ? "error" : "";
    }

    function setPopulateProgress(pct, visible) {
      const wrap = document.getElementById("populate-progress");
      const bar = document.getElementById("populate-progress-bar");
      wrap.style.display = visible ? "block" : "none";
      bar.style.width = Math.max(0, Math.min(100, pct)) + "%";
    }

    async function pollJob(jobId, button) {
      try {
        const res = await fetch("/api/jobs/" + jobId);
        if (!res.ok) throw new Error("Job non trovato (HTTP " + res.status + ")");
        const job = await res.json();

        setPopulateProgress(job.progress || 0, true);
        setPopulateStatus(job.message || "In corso...", false);

        if (job.status === "completed") {
          setPopulateProgress(100, false);
          setPopulateStatus("Dataset pronto: " + (job.dataset && job.dataset.label || ""), false);
          button.disabled = false;
          const datasetId = await loadDatasets(job.dataset && job.dataset.dataset_id);
          await loadLeads(datasetId);
          return;
        }

        if (job.status === "error") {
          setPopulateProgress(0, false);
          setPopulateStatus("Errore: " + (job.error || job.message || "Errore sconosciuto"), true);
          button.disabled = false;
          return;
        }

        setTimeout(() => pollJob(jobId, button), 2000);
      } catch (err) {
        setPopulateProgress(0, false);
        setPopulateStatus("Errore nel monitoraggio: " + err.message, true);
        button.disabled = false;
      }
    }

    async function createDataset() {
      const button = document.getElementById("btn-populate");
      const referenceQuery = document.getElementById("reference-input").value.trim();
      const provinceQuery = document.getElementById("province-input").value.trim() || "Provincia di Varese, Lombardia, Italia";

      if (!referenceQuery) {
        setPopulateStatus("Inserisci un punto di partenza prima di avviare il popolamento.", true);
        return;
      }

      button.disabled = true;
      setPopulateStatus("Avvio popolamento...", false);
      setPopulateProgress(1, true);

      try {
        const response = await fetch("/api/datasets", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            reference_query: referenceQuery,
            province_query: provinceQuery,
            background: true
          })
        });
        const payload = await response.json();
        if (!response.ok) {
          throw new Error(payload.error || "Errore durante il popolamento");
        }
        setPopulateStatus("Geocodifica e query OSM in corso...", false);
        setTimeout(() => pollJob(payload.job_id, button), 1500);
      } catch (error) {
        setPopulateProgress(0, false);
        setPopulateStatus("Errore: " + (error.message || "Errore durante il popolamento"), true);
        button.disabled = false;
      }
    }

    document.getElementById("dataset-select").addEventListener("change", async event => {
      activeDatasetId = event.target.value;
      const dataset = datasets.find(item => item.dataset_id === activeDatasetId);
      updateDatasetMeta(dataset || null);
      updateReferenceMarker(dataset || null);
      await loadLeads(activeDatasetId);
    });

    document.getElementById("btn-populate").addEventListener("click", createDataset);

    document.getElementById("btn-reset").addEventListener("click", () => {
      document.querySelectorAll(".f-priority, .f-category").forEach(el => { el.checked = true; });
      document.getElementById("toggle-senza-sito").checked = false;
      document.getElementById("toggle-hotlist").checked = false;
      applyFilters();
    });

    loadDatasets()
      .then(datasetId => {
        if (!datasetId) {
          document.getElementById("counter").textContent = "Nessun dato";
          document.getElementById("lead-list-counter").textContent = "Nessun lead";
          document.getElementById("lead-list-empty").style.display = "block";
          document.getElementById("no-data").style.display = "block";
          return;
        }
        return loadLeads(datasetId);
      })
      .catch(error => {
        document.getElementById("counter").textContent = "Errore caricamento";
        document.getElementById("populate-status").textContent = error.message || "Errore caricamento dati";
        console.error(error);
      });
  </script>
</body>
</html>
"""


@app.route("/")
def index():
    if FRONTEND_INDEX.exists():
        return send_from_directory(FRONTEND_DIST_DIR, "index.html")
    return HTML_PAGE


@app.route("/<path:path>")
def frontend_assets(path: str):
    if path.startswith("api/") or not FRONTEND_INDEX.exists():
        return ("Not found", 404)

    asset_path = FRONTEND_DIST_DIR / path
    if asset_path.exists() and asset_path.is_file():
        return send_from_directory(FRONTEND_DIST_DIR, path)
    return send_from_directory(FRONTEND_DIST_DIR, "index.html")


@app.route("/api/datasets", methods=["GET", "POST"])
def api_datasets():
    if request.method == "GET":
        return jsonify(list_datasets(DB_PATH))

    payload = request.get_json(silent=True) or {}
    reference_query = (payload.get("reference_query") or "").strip()
    if not reference_query:
        return jsonify({"error": "reference_query è obbligatorio"}), 400

    province_query = (payload.get("province_query") or "").strip() or DEFAULT_PROVINCE_QUERY
    dataset_id = (payload.get("dataset_id") or "").strip() or None
    append_to_existing = bool(payload.get("append_to_existing"))
    background = bool(payload.get("background"))
    limit = payload.get("limit")
    try:
        limit_value = int(limit) if limit else 0
    except (TypeError, ValueError):
        limit_value = 0

    if append_to_existing and not dataset_id:
        return jsonify({"error": "dataset_id è obbligatorio quando append_to_existing è attivo"}), 400

    if background:
        job_id = uuid4().hex
        _save_job(
            job_id,
            {
                "job_id": job_id,
                "status": "queued",
                "progress": 1,
                "stage": "queued",
                "message": "Richiesta ricevuta. Preparo il popolamento.",
                "reference_query": reference_query,
                "province_query": province_query,
                "dataset_id": dataset_id,
                "append_to_existing": append_to_existing,
            },
        )
        Thread(
            target=_population_worker,
            kwargs={
                "job_id": job_id,
                "reference_query": reference_query,
                "province_query": province_query,
                "dataset_id": dataset_id,
                "append_to_existing": append_to_existing,
                "limit": limit_value,
            },
            daemon=True,
        ).start()
        return (
            jsonify(
                {
                    "job_id": job_id,
                    "status": "queued",
                    "progress": 1,
                    "message": "Popolamento avviato.",
                }
            ),
            202,
        )

    try:
        dataset = create_dataset_from_reference(
            reference_query,
            dataset_id=dataset_id,
            province_query=province_query,
            limit=limit_value,
            db_path=DB_PATH,
            replace_dataset=not append_to_existing,
        )
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

    return jsonify(dataset), 201


@app.route("/api/jobs/<job_id>")
def api_job_status(job_id: str):
    payload = _get_job(job_id)
    if payload is None:
        return jsonify({"error": "job non trovato"}), 404
    return jsonify(payload)


@app.route("/api/leads")
def api_leads():
    dataset_id = (request.args.get("dataset_id") or "").strip() or None
    page_size = min(_int_arg("page_size") or 50000, 100000)
    page = max((_int_arg("page") or 1), 1)
    offset = (page - 1) * page_size

    leads = query_leads(
        priorita=_list_arg("priorita") or None,
        categoria=_list_arg("categoria") or None,
        solo_senza_sito=_bool_arg("solo_senza_sito"),
        solo_hotlist=_bool_arg("solo_hotlist") or _bool_arg("in_hotlist"),
        comune=(request.args.get("comune") or "").strip() or None,
        limit=page_size,
        offset=offset,
        dataset_id=dataset_id,
        db_path=DB_PATH,
    )
    result = [
        {
            "id": row.get("osm_url") or "",
            "dataset_id": row.get("dataset_id") or "",
            "lat": row["lat"],
            "lon": row["lon"],
            "nome": row["nome"] or "",
            "priorita": row["priorita"] or "",
            "categoria": row["categoria"] or "",
            "comune": row["comune"] or "",
            "telefono": row["telefono"] or "",
            "sito": row["sito"] or "",
            "ha_sito": row["ha_sito"] or "",
            "distanza_km": round(row["distanza_km"] or 0, 2),
            "in_hotlist": bool(row["in_hotlist"]),
            "stato": row["stato"] or "",
            "proposta": row["proposta"] or "",
            "criticita": row["criticita"] or "",
            "rating": row["rating"] or "",
            "email": row["email"] or "",
            "rilevanza_score": row.get("rilevanza_score"),
            "facebook_url": row.get("facebook_url") or "",
            "indirizzo": row.get("indirizzo") or "",
        }
        for row in leads
    ]
    # total = numero di lead con coordinate (quelli che compaiono sulla mappa)
    total_with_coords = count_leads(DB_PATH, dataset_id)
    return jsonify({
        "leads": result,
        "total": total_with_coords,
        "page": page,
        "page_size": page_size,
        "has_more": len(result) == page_size,
    })


@app.route("/api/datasets/<dataset_id>/enrich/facebook", methods=["POST"])
def api_enrich_facebook(dataset_id: str):
    job_id = str(uuid4())
    _save_job(
        job_id,
        {
            "status": "queued",
            "progress": 1,
            "stage": "queued",
            "message": "Avvio ricerca Facebook...",
            "dataset_id": dataset_id,
        },
        job_type="facebook_enrichment",
    )
    Thread(
        target=_facebook_enrichment_worker,
        kwargs={"job_id": job_id, "dataset_id": dataset_id},
        daemon=True,
    ).start()
    return jsonify({"job_id": job_id, "status": "queued", "progress": 1,
                    "message": "Ricerca Facebook avviata."}), 202


@app.route("/api/stats")
def api_stats():
    dataset_id = (request.args.get("dataset_id") or "").strip() or None
    dataset = get_active_dataset(DB_PATH, dataset_id)
    leads = query_leads(dataset_id=dataset_id, db_path=DB_PATH)
    total = len(leads)
    with_coords = sum(1 for row in leads if row["lat"] is not None and row["lon"] is not None)
    in_hotlist = sum(1 for row in leads if row["in_hotlist"])
    senza_sito = sum(1 for row in leads if row["ha_sito"] == "NO")
    by_priority: dict[str, int] = {}
    for row in leads:
      priority = row["priorita"] or "N/D"
      by_priority[priority] = by_priority.get(priority, 0) + 1
    return jsonify(
        {
            "dataset": dataset,
            "total": total,
            "with_coords": with_coords,
            "in_hotlist": in_hotlist,
            "senza_sito": senza_sito,
            "by_priority": by_priority,
        }
    )


@app.route("/api/geocode")
def api_geocode():
    """Geocode a free-text address via Nominatim."""
    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify({"error": "q è obbligatorio"}), 400
    result = geocode_address(q)
    if result is None:
        return jsonify({"error": "Indirizzo non trovato"}), 404
    return jsonify(result)


@app.route("/api/leads/parse-url", methods=["POST"])
def api_parse_lead_url():
    """Parse a Facebook or Google Maps URL and return pre-filled lead fields."""
    payload = request.get_json(silent=True) or {}
    url = (payload.get("url") or "").strip()
    if not url:
        return jsonify({"error": "url è obbligatorio"}), 400
    try:
        data = parse_lead_url(url)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 422
    except Exception as exc:
        return jsonify({"error": f"Parsing fallito: {exc}"}), 422
    return jsonify(data)


@app.route("/api/leads", methods=["POST"])
def api_create_lead():
    """Create a manually-entered lead in the active dataset."""
    payload = request.get_json(silent=True) or {}
    dataset_id = (payload.get("dataset_id") or "").strip() or None
    if not dataset_id:
        return jsonify({"error": "dataset_id è obbligatorio"}), 400

    lead = create_manual_lead(dataset_id, payload, db_path=DB_PATH)
    if lead is None:
        return jsonify({"error": "nome obbligatorio o dataset non trovato"}), 400

    return jsonify({
        "id": lead.get("osm_url", ""),
        "dataset_id": lead.get("dataset_id", ""),
        "nome": lead.get("nome", ""),
        "lat": lead.get("lat"),
        "lon": lead.get("lon"),
        "priorita": lead.get("priorita", ""),
        "categoria": lead.get("categoria", ""),
        "comune": lead.get("comune", ""),
        "telefono": lead.get("telefono", ""),
        "sito": lead.get("sito", ""),
        "ha_sito": lead.get("ha_sito", ""),
        "distanza_km": round(lead.get("distanza_km") or 0, 2),
        "in_hotlist": bool(lead.get("in_hotlist")),
        "stato": lead.get("stato", ""),
        "proposta": lead.get("proposta", ""),
        "criticita": lead.get("criticita", ""),
        "rating": lead.get("rating", ""),
        "email": lead.get("email", ""),
        "rilevanza_score": lead.get("rilevanza_score"),
        "facebook_url": lead.get("facebook_url", ""),
        "indirizzo": lead.get("indirizzo", ""),
    }), 201


@app.route("/api/leads/export")
def api_export_leads():
    """Stream filtered leads as a downloadable CSV file."""
    dataset_id = (request.args.get("dataset_id") or "").strip() or None
    csv_gen = export_leads_csv(
        dataset_id=dataset_id,
        priorita=_list_arg("priorita") or None,
        categoria=_list_arg("categoria") or None,
        solo_senza_sito=_bool_arg("solo_senza_sito"),
        solo_hotlist=_bool_arg("solo_hotlist") or _bool_arg("in_hotlist"),
        comune=(request.args.get("comune") or "").strip() or None,
        db_path=DB_PATH,
    )
    filename = f"morpheus_leads_{dataset_id or 'all'}.csv"
    return Response(
        csv_gen,
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.route("/api/leads", methods=["PATCH"])
def api_update_leads_bulk():
    """Bulk partial update: {'ids': [...], 'updates': {...}}"""
    payload = request.get_json(silent=True) or {}
    ids = payload.get("ids") or []
    updates = payload.get("updates") or {}
    if not ids or not updates:
        return jsonify({"error": "ids e updates sono obbligatori"}), 400
    count = update_leads_bulk(ids, updates, db_path=DB_PATH)
    return jsonify({"updated": count})


@app.route("/api/leads/<path:lead_id>", methods=["PATCH"])
def api_update_lead(lead_id: str):
    """Partial update of editable fields on a single lead."""
    payload = request.get_json(silent=True) or {}
    updated = update_lead_fields(lead_id, payload, db_path=DB_PATH)
    if updated is None:
        return jsonify({"error": "Lead non trovato"}), 404
    return jsonify({
        "id": updated.get("osm_url", ""),
        "dataset_id": updated.get("dataset_id", ""),
        "nome": updated.get("nome", ""),
        "stato": updated.get("stato", ""),
        "proposta": updated.get("proposta", ""),
        "rating": updated.get("rating", ""),
        "criticita": updated.get("criticita", ""),
        "in_hotlist": bool(updated.get("in_hotlist")),
        "telefono": updated.get("telefono", ""),
        "email": updated.get("email", ""),
        "sito": updated.get("sito", ""),
        "ha_sito": updated.get("ha_sito", ""),
    })


def _site_check_worker(job_id: str, *, dataset_id: str) -> None:
    def on_progress(event: dict) -> None:
        _save_job(
            job_id,
            {
                "status": "running",
                "progress": event.get("progress", 0),
                "stage": event.get("stage", ""),
                "message": event.get("message", "Verifica siti in corso..."),
                "dataset_id": dataset_id,
            },
            job_type="site_check",
        )

    try:
        result = check_sites_batch(dataset_id=dataset_id, db_path=DB_PATH, progress_callback=on_progress)
    except Exception as exc:
        _save_job(
            job_id,
            {"status": "error", "progress": 100, "stage": "error",
             "message": str(exc), "error": str(exc), "dataset_id": dataset_id},
            job_type="site_check",
        )
        return

    _save_job(
        job_id,
        {
            "status": "completed",
            "progress": 100,
            "stage": "done",
            "message": (
                f"Verifica completata: {result['dead']} siti non raggiungibili "
                f"su {result['checked']} controllati."
            ),
            "dataset_id": dataset_id,
            "result_json": result,
        },
        job_type="site_check",
    )


@app.route("/api/datasets/<dataset_id>/check-sites", methods=["POST"])
def api_check_sites(dataset_id: str):
    job_id = str(uuid4())
    _save_job(
        job_id,
        {"status": "queued", "progress": 1, "stage": "queued",
         "message": "Avvio verifica siti...", "dataset_id": dataset_id},
        job_type="site_check",
    )
    Thread(
        target=_site_check_worker,
        kwargs={"job_id": job_id, "dataset_id": dataset_id},
        daemon=True,
    ).start()
    return jsonify({"job_id": job_id, "status": "queued", "progress": 1,
                    "message": "Verifica siti avviata."}), 202


@app.route("/api/datasets/<dataset_id>", methods=["DELETE"])
def api_delete_dataset(dataset_id: str):
    """Delete a dataset and all its leads."""
    result = delete_dataset(dataset_id, db_path=DB_PATH)
    if result["deleted_leads"] == 0:
        existing = get_active_dataset(DB_PATH, dataset_id)
        if existing is None:
            return jsonify({"error": "Dataset non trovato"}), 404
    return jsonify(result)


@app.route("/api/comuni")
def api_comuni():
    """Return distinct comune values for autocomplete."""
    dataset_id = (request.args.get("dataset_id") or "").strip() or None
    return jsonify(list_comuni(dataset_id, DB_PATH))


if __name__ == "__main__":
    init_db(DB_PATH)
    mark_stale_jobs(DB_PATH)
    if count_leads(DB_PATH) == 0 and DEFAULT_OSM_OUTPUT.exists():
        print("Database vuoto — importo il dataset di default dal CSV...")
        import_from_csv(DEFAULT_OSM_OUTPUT, DEFAULT_HOTLIST, DB_PATH)

    dataset = get_active_dataset(DB_PATH)
    if dataset:
        print(f"✓  dataset attivo: {dataset['label']} ({dataset['lead_count']} attività)")
    else:
        print("⚠  Nessun dataset disponibile. Esegui prima: .venv/bin/python3 scripts/importa_db.py")
    print("→  Apri http://localhost:5000\n")
    app.run(debug=False, port=5000)
