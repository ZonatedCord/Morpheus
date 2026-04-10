import { startTransition, useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

const PRIORITY_COLORS = {
  ALTISSIMA: "#e03131",
  ALTA: "#f08c00",
  MEDIA: "#099268",
  BASSA: "#6c757d",
  "MOLTO BASSA": "#adb5bd"
};

const PRIORITY_OPTIONS = ["ALTISSIMA", "ALTA", "MEDIA", "BASSA", "MOLTO BASSA"];
const DEFAULT_PROVINCE = "Provincia di Varese, Lombardia, Italia";
const ACTIVE_DATASET_STORAGE_KEY = "lead-atlas.activeDataset";
const POPULATION_JOB_STORAGE_KEY = "lead-atlas.activePopulationJob";

function normalizeDatasets(payload) {
  if (!Array.isArray(payload)) return [];
  return payload.map((dataset, index) => ({
    datasetId: String(dataset.dataset_id ?? dataset.id ?? index),
    label: dataset.label ?? dataset.name ?? `Dataset ${index + 1}`,
    referenceQuery: dataset.reference_query ?? "",
    referenceName: dataset.reference_name ?? dataset.label ?? dataset.name ?? `Dataset ${index + 1}`,
    referenceLat: Number(dataset.reference_lat ?? 45.7755),
    referenceLon: Number(dataset.reference_lon ?? 8.8872),
    provinceQuery: dataset.province_query ?? DEFAULT_PROVINCE,
    leadCount: Number(dataset.lead_count ?? 0),
    hotlistCount: Number(dataset.hotlist_count ?? 0),
    withoutSiteCount: Number(dataset.without_site_count ?? 0),
    isActive: Boolean(dataset.is_active)
  }));
}

function normalizeLeads(payload) {
  if (!Array.isArray(payload)) return [];
  return payload.map((lead, index) => ({
    ...lead,
    id: String(lead.id ?? `${lead.dataset_id ?? "dataset"}-${index}`),
    lat: Number(lead.lat),
    lon: Number(lead.lon),
    distanza_km: Number(lead.distanza_km ?? 0),
    priorita: lead.priorita ?? "",
    categoria: lead.categoria ?? "",
    comune: lead.comune ?? "",
    telefono: lead.telefono ?? "",
    sito: lead.sito ?? "",
    ha_sito: lead.ha_sito ?? "",
    in_hotlist: Boolean(lead.in_hotlist)
  }));
}

function makeStarIcon(active) {
  const size = active ? 22 : 18;
  const shadow = active
    ? "0 0 0 4px rgba(255, 215, 0, 0.18), 0 0 3px rgba(0,0,0,0.7)"
    : "0 0 2px rgba(0,0,0,0.55)";
  return L.divIcon({
    html: `<div style="font-size:${size}px;line-height:1;color:#FFD700;text-shadow:${shadow};">★</div>`,
    className: "",
    iconSize: [24, 24],
    iconAnchor: [12, 12]
  });
}

function applyMarkerSelection(marker, lead, active) {
  if (!marker) return;
  if (lead.in_hotlist) {
    marker.setIcon(makeStarIcon(active));
    marker.setZIndexOffset(active ? 1000 : 0);
    return;
  }

  const color = PRIORITY_COLORS[lead.priorita] || "#adb5bd";
  marker.setStyle({
    radius: active ? 8 : 5,
    color,
    fillColor: color,
    fillOpacity: active ? 1 : 0.8,
    weight: active ? 2 : 1
  });
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function buildPopupHtml(lead) {
  let html = `<b>${escapeHtml(lead.nome)}</b><br>`;
  html += escapeHtml(lead.categoria || "Categoria N/D");
  if (lead.comune && lead.comune !== "N/D") html += ` &middot; ${escapeHtml(lead.comune)}`;
  html += "<br>";
  if (lead.telefono && lead.telefono !== "N/D") html += `&#128222; ${escapeHtml(lead.telefono)}<br>`;
  if (lead.sito && lead.sito !== "N/D") {
    const href = escapeHtml(lead.sito);
    html += `&#127760; <a href="${href}" target="_blank" rel="noopener">${href}</a><br>`;
  }
  html += `&#128205; ${lead.distanza_km.toFixed(2)} km &nbsp;&middot;&nbsp; <b>${escapeHtml(lead.priorita)}</b>`;
  if (lead.in_hotlist) {
    html += "<hr style='margin:6px 0; border-color:#dee2e6'>";
    if (lead.stato) html += `<b>Stato:</b> ${escapeHtml(lead.stato)}<br>`;
    if (lead.proposta) html += `<b>Proposta:</b> ${escapeHtml(lead.proposta)}<br>`;
    if (lead.rating) html += `&#11088; ${escapeHtml(lead.rating)}<br>`;
    if (lead.email && lead.email !== "N/D") html += `&#128231; ${escapeHtml(lead.email)}`;
  }
  return html;
}

function DatasetPill({ dataset, active, onClick }) {
  return (
    <button type="button" className={`dataset-pill ${active ? "active" : ""}`} onClick={onClick}>
      <span className="dataset-pill-title">{dataset.label}</span>
      <span className="dataset-pill-sub">{dataset.referenceQuery || dataset.referenceName}</span>
    </button>
  );
}

function LeadCard({ lead, active, index, onClick }) {
  const priorityColor = PRIORITY_COLORS[lead.priorita] || "#adb5bd";
  const siteLabel = lead.ha_sito === "NO" ? "Senza sito" : "Con sito";

  return (
    <button type="button" className={`lead-card ${active ? "active" : ""}`} onClick={onClick}>
      <div className="lead-card-index">{index + 1}</div>
      <div className="lead-card-body">
        <div className="lead-card-head">
          <div className="lead-card-name">{lead.nome}</div>
          {lead.in_hotlist ? <span className="lead-card-hotlist">★</span> : null}
        </div>
        <div className="lead-card-meta">
          <span>{lead.categoria || "Categoria N/D"}</span>
          <span>{lead.comune || "Comune N/D"}</span>
        </div>
        <div className="lead-card-line">
          <span className="lead-card-priority">
            <span className="dot" style={{ background: priorityColor }} />
            {lead.priorita || "N/D"}
          </span>
          <span>{lead.distanza_km.toFixed(2)} km</span>
        </div>
        <div className="lead-card-muted">
          <span>{siteLabel}</span>
          <span>{lead.telefono || "Telefono N/D"}</span>
        </div>
      </div>
    </button>
  );
}

export default function App() {
  const mapContainerRef = useRef(null);
  const mapRef = useRef(null);
  const tileLayerRef = useRef(null);
  const referenceMarkerRef = useRef(null);
  const markersLayerRef = useRef(null);
  const markerRefs = useRef(new Map());

  const [datasets, setDatasets] = useState([]);
  const [activeDatasetId, setActiveDatasetId] = useState("");
  const [datasetsLoading, setDatasetsLoading] = useState(true);
  const [datasetsError, setDatasetsError] = useState("");

  const [leads, setLeads] = useState([]);
  const [leadsLoading, setLeadsLoading] = useState(true);
  const [leadsError, setLeadsError] = useState("");
  const [selectedLeadId, setSelectedLeadId] = useState(null);

  const [referenceInput, setReferenceInput] = useState("");
  const [provinceInput, setProvinceInput] = useState(DEFAULT_PROVINCE);
  const [populateStatus, setPopulateStatus] = useState("");
  const [populateLoading, setPopulateLoading] = useState(false);
  const [populateProgress, setPopulateProgress] = useState(0);
  const [populateStage, setPopulateStage] = useState("");
  const [populateJobId, setPopulateJobId] = useState("");
  const [appendToExisting, setAppendToExisting] = useState(false);

  const [search, setSearch] = useState("");
  const deferredSearch = useDeferredValue(search);
  const [onlyHotlist, setOnlyHotlist] = useState(false);
  const [onlyWithoutSite, setOnlyWithoutSite] = useState(false);
  const [selectedPriorities, setSelectedPriorities] = useState(() => new Set(PRIORITY_OPTIONS));
  const [selectedCategory, setSelectedCategory] = useState("");
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [isListCollapsed, setIsListCollapsed] = useState(false);

  const activeDataset = useMemo(
    () => datasets.find((dataset) => dataset.datasetId === activeDatasetId) || datasets[0] || null,
    [datasets, activeDatasetId]
  );

  const categories = useMemo(
    () => [...new Set(leads.map((lead) => lead.categoria).filter(Boolean))].sort((a, b) => a.localeCompare(b)),
    [leads]
  );

  const filteredLeads = useMemo(() => {
    const query = deferredSearch.trim().toLowerCase();
    return leads.filter((lead) => {
      const matchesSearch =
        !query ||
        [lead.nome, lead.categoria, lead.comune, lead.telefono, lead.sito]
          .filter(Boolean)
          .some((value) => String(value).toLowerCase().includes(query));
      const matchesPriority = selectedPriorities.has(lead.priorita);
      const matchesHotlist = !onlyHotlist || lead.in_hotlist;
      const matchesSite = !onlyWithoutSite || lead.ha_sito === "NO";
      const matchesCategory = !selectedCategory || lead.categoria === selectedCategory;
      return matchesSearch && matchesPriority && matchesHotlist && matchesSite && matchesCategory;
    });
  }, [deferredSearch, leads, onlyHotlist, onlyWithoutSite, selectedCategory, selectedPriorities]);

  const selectedLead =
    filteredLeads.find((lead) => lead.id === selectedLeadId) || filteredLeads[0] || null;

  useEffect(() => {
    if (selectedLead && selectedLead.id !== selectedLeadId) {
      setSelectedLeadId(selectedLead.id);
    }
    if (!selectedLead) {
      setSelectedLeadId(null);
    }
  }, [selectedLead, selectedLeadId]);

  useEffect(() => {
    if (mapRef.current || !mapContainerRef.current) return;

    const map = L.map(mapContainerRef.current, { zoomControl: true }).setView([45.7755, 8.8872], 12);
    mapRef.current = map;
    tileLayerRef.current = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "© OpenStreetMap"
    }).addTo(map);
    referenceMarkerRef.current = L.circleMarker([45.7755, 8.8872], {
      radius: 7,
      color: "#111827",
      fillColor: "#111827",
      fillOpacity: 1,
      weight: 2
    })
      .addTo(map)
      .bindPopup("<b>Vedano Olona</b><br>Punto di riferimento");
    markersLayerRef.current = L.layerGroup().addTo(map);
    window.requestAnimationFrame(() => map.invalidateSize());

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!activeDataset || !mapRef.current || !referenceMarkerRef.current) return;
    referenceMarkerRef.current.setLatLng([activeDataset.referenceLat, activeDataset.referenceLon]);
    referenceMarkerRef.current.bindPopup(`<b>${escapeHtml(activeDataset.referenceName)}</b><br>Punto di riferimento`);
    mapRef.current.setView([activeDataset.referenceLat, activeDataset.referenceLon], 12, { animate: false });
    window.requestAnimationFrame(() => mapRef.current?.invalidateSize());
    setReferenceInput(activeDataset.referenceQuery || "");
    setProvinceInput(activeDataset.provinceQuery || DEFAULT_PROVINCE);
  }, [activeDataset]);

  useEffect(() => {
    window.requestAnimationFrame(() => mapRef.current?.invalidateSize());
  }, [isSidebarCollapsed, isListCollapsed]);

  useEffect(() => {
    const savedJobId = window.localStorage.getItem(POPULATION_JOB_STORAGE_KEY);
    if (!savedJobId) return;
    setPopulateJobId(savedJobId);
    setPopulateLoading(true);
    setPopulateProgress(5);
    setPopulateStatus("Sto riprendendo il monitoraggio del popolamento...");
  }, []);

  useEffect(() => {
    if (!populateJobId) return undefined;

    let cancelled = false;

    const pollJob = async () => {
      try {
        const response = await fetch(`/api/jobs/${populateJobId}`);
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
        if (cancelled) return;

        setPopulateLoading(payload.status === "queued" || payload.status === "running");
        setPopulateProgress(Number(payload.progress ?? 0));
        setPopulateStage(String(payload.stage ?? "").replaceAll("_", " "));
        setPopulateStatus(payload.message || "Popolamento in esecuzione...");

        if (payload.status === "completed") {
          window.localStorage.removeItem(POPULATION_JOB_STORAGE_KEY);
          setPopulateJobId("");
          setPopulateLoading(false);
          const nextId = await loadDatasets(payload.dataset?.dataset_id || activeDatasetId);
          await loadLeads(nextId);
        } else if (payload.status === "error") {
          window.localStorage.removeItem(POPULATION_JOB_STORAGE_KEY);
          setPopulateJobId("");
          setPopulateLoading(false);
        }
      } catch (error) {
        if (!cancelled) {
          setPopulateStatus(error.message || "Impossibile leggere lo stato del popolamento.");
        }
      }
    };

    pollJob();
    const intervalId = window.setInterval(pollJob, 1500);
    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [populateJobId]);

  useEffect(() => {
    if (!populateLoading) return undefined;

    const handleBeforeUnload = (event) => {
      event.preventDefault();
      event.returnValue = "";
    };

    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, [populateLoading]);

  async function loadDatasets(preferredDatasetId = "") {
    setDatasetsLoading(true);
    setDatasetsError("");
    try {
      const response = await fetch("/api/datasets");
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = await response.json();
      const nextDatasets = normalizeDatasets(payload);
      startTransition(() => {
        setDatasets(nextDatasets);
      });
      const nextActive =
        nextDatasets.find((dataset) => dataset.datasetId === preferredDatasetId)?.datasetId ||
        nextDatasets.find((dataset) => dataset.isActive)?.datasetId ||
        nextDatasets[0]?.datasetId ||
        "";
      setActiveDatasetId(nextActive);
      return nextActive;
    } catch (error) {
      setDatasets([]);
      setActiveDatasetId("");
      setDatasetsError("Endpoint /api/datasets non disponibile.");
      return "";
    } finally {
      setDatasetsLoading(false);
    }
  }

  async function loadLeads(datasetId) {
    if (!datasetId) {
      setLeads([]);
      setSelectedLeadId(null);
      return;
    }
    setLeadsLoading(true);
    setLeadsError("");
    try {
      const params = new URLSearchParams({ dataset_id: datasetId });
      const response = await fetch(`/api/leads?${params.toString()}`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = await response.json();
      const nextLeads = normalizeLeads(payload);
      startTransition(() => {
        setLeads(nextLeads);
      });
      setSelectedLeadId(nextLeads[0]?.id ?? null);
    } catch (error) {
      setLeads([]);
      setSelectedLeadId(null);
      setLeadsError("Endpoint /api/leads non disponibile o vuoto.");
    } finally {
      setLeadsLoading(false);
    }
  }

  useEffect(() => {
    const savedDatasetId = window.localStorage.getItem(ACTIVE_DATASET_STORAGE_KEY) || "";
    loadDatasets(savedDatasetId);
  }, []);

  useEffect(() => {
    loadLeads(activeDatasetId);
  }, [activeDatasetId]);

  useEffect(() => {
    if (!activeDatasetId) return;
    window.localStorage.setItem(ACTIVE_DATASET_STORAGE_KEY, activeDatasetId);
  }, [activeDatasetId]);

  function focusLead(leadId, pan = true) {
    const marker = markerRefs.current.get(leadId);
    const lead = filteredLeads.find((item) => item.id === leadId) || leads.find((item) => item.id === leadId);
    if (!lead) return;
    setSelectedLeadId(leadId);
    if (!marker || !mapRef.current) return;
    if (pan) {
      mapRef.current.flyTo([lead.lat, lead.lon], Math.max(mapRef.current.getZoom(), 15), {
        duration: 0.45
      });
    }
    marker.openPopup();
  }

  useEffect(() => {
    if (!markersLayerRef.current) return;
    markersLayerRef.current.clearLayers();
    markerRefs.current = new Map();

    filteredLeads.forEach((lead) => {
      let marker;
      if (lead.in_hotlist) {
        marker = L.marker([lead.lat, lead.lon], {
          icon: makeStarIcon(false),
          zIndexOffset: 0
        });
      } else {
        const color = PRIORITY_COLORS[lead.priorita] || "#adb5bd";
        marker = L.circleMarker([lead.lat, lead.lon], {
          radius: 5,
          color,
          fillColor: color,
          fillOpacity: 0.8,
          weight: 1
        });
      }

      marker.bindPopup(buildPopupHtml(lead), { maxWidth: 280 });
      marker.on("click", () => setSelectedLeadId(lead.id));
      marker.addTo(markersLayerRef.current);
      markerRefs.current.set(lead.id, marker);
      applyMarkerSelection(marker, lead, lead.id === selectedLeadId);
    });
  }, [filteredLeads]);

  useEffect(() => {
    filteredLeads.forEach((lead) => {
      const marker = markerRefs.current.get(lead.id);
      applyMarkerSelection(marker, lead, lead.id === selectedLeadId);
    });
  }, [filteredLeads, selectedLeadId]);

  function togglePriority(priority) {
    setSelectedPriorities((current) => {
      const next = new Set(current);
      if (next.has(priority)) next.delete(priority);
      else next.add(priority);
      return next;
    });
  }

  function resetFilters() {
    setSearch("");
    setOnlyHotlist(false);
    setOnlyWithoutSite(false);
    setSelectedCategory("");
    setSelectedPriorities(new Set(PRIORITY_OPTIONS));
  }

  async function handleCreateDataset() {
    const referenceQuery =
      appendToExisting && activeDataset
        ? activeDataset.referenceQuery || activeDataset.referenceName
        : referenceInput.trim();

    if (!referenceQuery) {
      setPopulateStatus("Inserisci il centro da cui vuoi misurare la distanza.");
      return;
    }
    if (appendToExisting && !activeDatasetId) {
      setPopulateStatus("Per unire i risultati devi prima selezionare un dataset attivo.");
      return;
    }
    setPopulateLoading(true);
    setPopulateProgress(3);
    setPopulateStage("queued");
    setPopulateStatus("Avvio scansione della nuova area. Non chiudere la pagina.");
    try {
      const response = await fetch("/api/datasets", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          reference_query: referenceQuery,
          province_query: provinceInput.trim() || DEFAULT_PROVINCE,
          background: true,
          append_to_existing: appendToExisting,
          dataset_id: appendToExisting ? activeDatasetId : ""
        })
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "Errore durante il popolamento");
      if (!payload.job_id) throw new Error("Job di popolamento non ricevuto.");
      setPopulateJobId(payload.job_id);
      window.localStorage.setItem(POPULATION_JOB_STORAGE_KEY, payload.job_id);
      setPopulateProgress(Number(payload.progress ?? 3));
      setPopulateStatus(payload.message || "Scansione avviata.");
    } catch (error) {
      window.localStorage.removeItem(POPULATION_JOB_STORAGE_KEY);
      setPopulateJobId("");
      setPopulateStage("error");
      setPopulateStatus(error.message || "Errore durante il popolamento");
      setPopulateProgress(0);
      setPopulateLoading(false);
    }
  }

  return (
    <div className={`app-shell${isSidebarCollapsed ? " sidebar-collapsed" : ""}`}>
      <aside className={`sidebar${isSidebarCollapsed ? " collapsed" : ""}`}>
        <div className="panel-rail">
          <span className="panel-rail-title">{isSidebarCollapsed ? "Filtri" : "DataBase B2B"}</span>
          <button
            type="button"
            className="panel-toggle"
            onClick={() => setIsSidebarCollapsed((current) => !current)}
            aria-label={isSidebarCollapsed ? "Apri pannello filtri" : "Chiudi pannello filtri"}
            title={isSidebarCollapsed ? "Apri filtri" : "Chiudi filtri"}
          >
            {isSidebarCollapsed ? "›" : "‹"}
          </button>
        </div>

        {!isSidebarCollapsed ? (
          <div className="sidebar-scroll">
            <div className="brand-block">
              <div className="eyebrow">Lead Atlas</div>
              <h1>Atlante dei clienti locali</h1>
              <p>Scansiona nuove aree, unisci dataset e apri i lead direttamente sulla mappa senza perdere il contesto.</p>
            </div>

            <section className="panel">
              <div className="panel-head">
                <h2>Archivi salvati</h2>
                <span>{datasetsLoading ? "Caricamento..." : `${datasets.length} disponibili`}</span>
              </div>
              {datasetsError ? <div className="notice">{datasetsError}</div> : null}
              <div className="dataset-list">
                {datasets.map((dataset) => (
                  <DatasetPill
                    key={dataset.datasetId}
                    dataset={dataset}
                    active={dataset.datasetId === activeDatasetId}
                    onClick={() => setActiveDatasetId(dataset.datasetId)}
                  />
                ))}
              </div>
              {activeDataset ? (
                <div className="field-static">
                  <strong>Archivio attivo: {activeDataset.label}</strong>
                  <br />
                  Centro di distanza: {activeDataset.referenceQuery}
                  <br />
                  {activeDataset.leadCount} lead · {activeDataset.hotlistCount} hotlist · {activeDataset.withoutSiteCount} senza sito
                </div>
              ) : null}
            </section>

            <section className="panel">
              <div className="panel-head">
                <h2>Nuova area da scansionare</h2>
                <span>{appendToExisting ? "Aggiunge lead" : "Crea o aggiorna un archivio"}</span>
              </div>
              <label className="field">
                <span>Centro da cui misurare la distanza</span>
                <input
                  value={appendToExisting && activeDataset ? activeDataset.referenceQuery : referenceInput}
                  onChange={(event) => setReferenceInput(event.target.value)}
                  placeholder="Es. Vedano Olona, Varese, Lombardia, Italia"
                  disabled={appendToExisting && !!activeDataset}
                />
              </label>
              <label className="field">
                <span>Provincia o area OSM da cercare</span>
                <input value={provinceInput} onChange={(event) => setProvinceInput(event.target.value)} />
              </label>
              <label className="toggle-row">
                <input
                  type="checkbox"
                  checked={appendToExisting}
                  onChange={(event) => setAppendToExisting(event.target.checked)}
                />
                Unisci i nuovi risultati all'archivio attivo
              </label>
              <div className="helper-copy">
                {appendToExisting
                  ? `I lead nuovi verranno aggiunti a "${activeDataset?.label || "questo archivio"}". I duplicati verranno aggiornati, non duplicati.`
                  : "Se usi un centro gia' noto aggiorni il suo archivio. Se usi un centro nuovo, viene creato un nuovo archivio."}
              </div>
              <button type="button" className="primary-button block-button" onClick={handleCreateDataset} disabled={populateLoading}>
                {populateLoading ? "Scansione in corso..." : "Avvia scansione"}
              </button>
              {(populateLoading || populateStatus) ? (
                <div className="progress-card">
                  <div className="progress-head">
                    <strong>{populateLoading ? "Progresso scansione" : "Ultimo aggiornamento"}</strong>
                    <span>{populateProgress}%</span>
                  </div>
                  {populateStage ? <div className="progress-stage">Fase: {populateStage}</div> : null}
                  <div className="progress-track">
                    <div className="progress-fill" style={{ width: `${Math.max(populateProgress, populateLoading ? 6 : 0)}%` }} />
                  </div>
                  <div className="progress-copy">{populateStatus || "In attesa..."}</div>
                  <div className="progress-hint">
                    Se ricarichi la pagina durante la scansione, il monitoraggio riparte appena torni nella mappa.
                  </div>
                </div>
              ) : null}
            </section>

            <section className="panel">
              <div className="panel-head">
                <h2>Filtri mappa</h2>
                <button type="button" className="ghost-button" onClick={resetFilters}>
                  Azzera
                </button>
              </div>

              <label className="field">
                <span>Cerca per nome, comune o categoria</span>
                <input
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Nome, comune, categoria..."
                />
              </label>

              <label className="field">
                <span>Categoria principale</span>
                <select value={selectedCategory} onChange={(event) => setSelectedCategory(event.target.value)}>
                  <option value="">Tutte</option>
                  {categories.map((category) => (
                    <option key={category} value={category}>
                      {category}
                    </option>
                  ))}
                </select>
              </label>

              <div className="priority-grid">
                {PRIORITY_OPTIONS.map((priority) => (
                  <button
                    type="button"
                    key={priority}
                    className={`priority-chip ${selectedPriorities.has(priority) ? "active" : ""}`}
                    onClick={() => togglePriority(priority)}
                  >
                    <span className="dot" style={{ background: PRIORITY_COLORS[priority] || "#adb5bd" }} />
                    {priority}
                  </button>
                ))}
              </div>

              <label className="toggle-row">
                <input type="checkbox" checked={onlyHotlist} onChange={(event) => setOnlyHotlist(event.target.checked)} />
                Mostra solo lead gia' in hotlist
              </label>

              <label className="toggle-row">
                <input
                  type="checkbox"
                  checked={onlyWithoutSite}
                  onChange={(event) => setOnlyWithoutSite(event.target.checked)}
                />
                Mostra solo attivita' senza sito
              </label>
            </section>
          </div>
        ) : (
          <div className="collapsed-panel-note">
            <span>{activeDataset?.label || "Dataset"}</span>
            <strong>{filteredLeads.length}</strong>
          </div>
        )}
      </aside>

      <main className={`workspace${isListCollapsed ? " list-collapsed" : ""}`}>
        <section className="map-panel">
          <div className="map-panel-head">
            <div>
              <div className="eyebrow">Mappa attiva</div>
              <h2>{activeDataset ? activeDataset.referenceName : "Nessun archivio selezionato"}</h2>
            </div>
            <div className="stat-row">
              <span>{filteredLeads.length} lead</span>
              <span>{filteredLeads.filter((lead) => lead.in_hotlist).length} hotlist</span>
              <span>{filteredLeads.filter((lead) => lead.ha_sito === "NO").length} senza sito</span>
            </div>
          </div>

          {leadsError ? <div className="notice">{leadsError}</div> : null}

          <div className="map-stage">
            <div ref={mapContainerRef} className="map-canvas" />
            <div className="map-card">
              <span className="map-card-kicker">Focus mappa</span>
              <strong>{selectedLead ? selectedLead.nome : activeDataset?.label || "Nessun lead selezionato"}</strong>
              <p>
                {selectedLead
                  ? `${selectedLead.categoria || "Categoria N/D"} · ${selectedLead.comune || "Comune N/D"} · ${selectedLead.distanza_km.toFixed(2)} km`
                  : activeDataset
                    ? `${activeDataset.referenceQuery} · ${activeDataset.leadCount} lead`
                    : "Seleziona o crea un archivio per vedere i lead sulla mappa."}
              </p>
              <div className="map-card-actions">
                <button
                  type="button"
                  className="primary-button"
                  disabled={!selectedLead}
                  onClick={() => selectedLead && focusLead(selectedLead.id)}
                >
                  Apri lead sulla mappa
                </button>
                <button
                  type="button"
                  className="secondary-button"
                  disabled={!activeDataset}
                  onClick={() => {
                    if (activeDataset && mapRef.current) {
                      mapRef.current.setView([activeDataset.referenceLat, activeDataset.referenceLon], 12, {
                        animate: true
                      });
                      referenceMarkerRef.current?.openPopup();
                    }
                  }}
                >
                  Torna al centro dell'archivio
                </button>
              </div>
            </div>
          </div>
        </section>

        <section className={`list-panel${isListCollapsed ? " collapsed" : ""}`}>
          <div className="panel-rail">
            <div className="list-head-inner">
              {!isListCollapsed && (
                <div>
                  <h2>Lead</h2>
                  <span>{leadsLoading ? "Caricamento..." : `${filteredLeads.length} risultati`}</span>
                </div>
              )}
              {isListCollapsed && <span className="panel-rail-title">Lead</span>}
            </div>
            <button
              type="button"
              className="panel-toggle"
              onClick={() => setIsListCollapsed((current) => !current)}
              aria-label={isListCollapsed ? "Apri elenco lead" : "Chiudi elenco lead"}
              title={isListCollapsed ? "Apri elenco" : "Chiudi elenco"}
            >
              {isListCollapsed ? "‹" : "›"}
            </button>
          </div>

          {!isListCollapsed ? (
            <>

              <div className="lead-list">
                {filteredLeads.length ? (
                  filteredLeads.map((lead, index) => (
                    <LeadCard
                      key={lead.id}
                      lead={lead}
                      index={index}
                      active={lead.id === selectedLeadId}
                      onClick={() => focusLead(lead.id)}
                    />
                  ))
                ) : (
                  <div className="empty-state">
                    Nessun lead corrisponde ai filtri attivi.
                  </div>
                )}
              </div>
            </>
          ) : (
            <div className="collapsed-panel-note">
              <span>Lead</span>
              <strong>{filteredLeads.length}</strong>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
