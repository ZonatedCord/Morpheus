import { memo, startTransition, useCallback, useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
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
const CATEGORIE = [
  "Ristorazione", "Ospitalità", "Beauty & Benessere",
  "Fitness & Sport", "Sanità", "Servizi Professionali",
  "Artigiani", "Negozi", "Intrattenimento"
];
const DEFAULT_PROVINCE = "Provincia di Varese, Lombardia, Italia";
const ACTIVE_DATASET_STORAGE_KEY = "lead-atlas.activeDataset";
const POPULATION_JOB_STORAGE_KEY = "lead-atlas.activePopulationJob";
const FACEBOOK_JOB_STORAGE_KEY = "lead-atlas.activeFacebookJob";
const PAGE_SIZE = 50000; // carica tutti i lead in una sola pagina — il viewport culling gestisce le performance

const TILE_LAYERS = {
  osm: {
    label: "Mappa",
    url: "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    attribution: "© OpenStreetMap",
  },
  satellite: {
    label: "Satellite",
    url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    attribution: "© Esri, Maxar, Earthstar Geographics",
  },
};

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
    id: String(lead.id || lead.osm_url || `${lead.dataset_id ?? "dataset"}-${index}`),
    lat: Number(lead.lat),
    lon: Number(lead.lon),
    distanza_km: Number(lead.distanza_km ?? 0),
    priorita: lead.priorita ?? "",
    categoria: lead.categoria ?? "",
    comune: lead.comune ?? "",
    telefono: lead.telefono ?? "",
    sito: lead.sito ?? "",
    ha_sito: lead.ha_sito ?? "",
    in_hotlist: Boolean(lead.in_hotlist),
    facebook_url: lead.facebook_url ?? "",
    indirizzo: lead.indirizzo ?? "",
  }));
}

const CLUSTER_ZOOM_THRESHOLD = 11;

function makeCityIcon(count) {
  const size = count > 100 ? 46 : count > 30 ? 38 : 30;
  const fs = size > 38 ? 13 : 11;
  return L.divIcon({
    html: `<div style="width:${size}px;height:${size}px;border-radius:50%;background:rgba(9,146,104,0.88);border:2px solid #fff;display:flex;align-items:center;justify-content:center;color:#fff;font-weight:700;font-size:${fs}px;box-shadow:0 1px 5px rgba(0,0,0,0.35);">${count}</div>`,
    className: "",
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2]
  });
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
  if (lead.indirizzo && lead.indirizzo !== "N/D") html += `${escapeHtml(lead.indirizzo)}<br>`;
  if (lead.telefono && lead.telefono !== "N/D") html += `&#128222; ${escapeHtml(lead.telefono)}<br>`;
  if (lead.sito && lead.sito !== "N/D") {
    const href = escapeHtml(lead.sito);
    html += `&#127760; <a href="${href}" target="_blank" rel="noopener">${href}</a><br>`;
  }
  if (lead.facebook_url && lead.facebook_url !== "N/D" && lead.facebook_url !== "N/F") {
    const fbHref = escapeHtml(lead.facebook_url);
    html += `&#128241; <a href="${fbHref}" target="_blank" rel="noopener">Facebook</a><br>`;
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

const STATO_OPTIONS = ["Contattata", "Rifiutata", "Scartata"];
const SITE_CHECK_JOB_STORAGE_KEY = "lead-atlas.activeSiteCheckJob";
const DEFAULT_WEIGHTS = { dist: 5, sito: 3, cat: 2 };

function computeLocalScore(lead, weights, targetCats, maxDist) {
  const total = (weights.dist + weights.sito + weights.cat) || 1;
  const distNorm = Math.max(0, 1 - lead.distanza_km / maxDist);
  const sito = lead.ha_sito !== "SI" ? 1 : 0;
  const cat = targetCats.length > 0 && targetCats.includes(lead.categoria) ? 1 : 0;
  return (weights.dist * distNorm + weights.sito * sito + weights.cat * cat) / total;
}

function scoreToPriority(score) {
  if (score >= 0.75) return "ALTISSIMA";
  if (score >= 0.55) return "ALTA";
  if (score >= 0.35) return "MEDIA";
  if (score >= 0.20) return "BASSA";
  return "MOLTO BASSA";
}

function buildExportUrl(params) {
  const p = new URLSearchParams();
  if (params.datasetId) p.set("dataset_id", params.datasetId);
  if (params.onlyHotlist) p.set("solo_hotlist", "1");
  if (params.onlyWithoutSite) p.set("solo_senza_sito", "1");
  if (params.selectedCategory) p.set("categoria", params.selectedCategory);
  return `/api/leads/export?${p.toString()}`;
}

const LeadCard = memo(function LeadCard({ lead, active, index, onClick, onUpdateStato, selected, onToggleSelect }) {
  const displayPriority = lead._localPriority ?? lead.priorita;
  const priorityColor = PRIORITY_COLORS[displayPriority] || "#adb5bd";
  const siteLabel = lead.ha_sito === "MORTO" ? "Sito morto" : lead.ha_sito === "NO" ? "Senza sito" : "Con sito";
  const isScartata = lead.stato === "Scartata";

  function handleStatoClick(e, option) {
    e.stopPropagation();
    onUpdateStato(lead.id, lead.stato, lead.stato === option ? "" : option);
  }

  function handleCheckbox(e) {
    e.stopPropagation();
    onToggleSelect(lead.id);
  }

  return (
    <div className={`lead-card-outer${selected ? " bulk-selected" : ""}`}>
      <input
        type="checkbox"
        className="bulk-checkbox"
        checked={selected}
        onChange={handleCheckbox}
        onClick={(e) => e.stopPropagation()}
        aria-label={`Seleziona ${lead.nome}`}
      />
      <button type="button" className={`lead-card${active ? " active" : ""}${isScartata ? " scartata" : ""}`} onClick={onClick}>
        <div className="lead-card-index">{index + 1}</div>
        <div className="lead-card-body">
          <div className="lead-card-head">
            <div className="lead-card-name">{lead.nome}</div>
            {lead.in_hotlist ? <span className="lead-card-hotlist">★</span> : null}
            {lead.id?.startsWith("manual://") ? (
              <span style={{ fontSize: "9px", fontWeight: 600, color: "#64748b", background: "#f1f5f9", padding: "1px 5px", borderRadius: "999px", border: "1px solid #e2e8f0" }}>Manuale</span>
            ) : null}
          </div>
          <div className="lead-card-meta">
            <span>{lead.categoria || "Categoria N/D"}</span>
            <span>{lead.comune || "Comune N/D"}</span>
          </div>
          {lead.indirizzo && lead.indirizzo !== "N/D" && (
            <div className="lead-card-address">{lead.indirizzo}</div>
          )}
          <div className="lead-card-line">
            <span className="lead-card-priority">
              <span className="dot" style={{ background: priorityColor }} />
              {displayPriority || "N/D"}
            </span>
            <span>{lead.distanza_km.toFixed(2)} km</span>
          </div>
          <div className="lead-card-muted">
            <span className={lead.ha_sito === "MORTO" ? "tag-morto" : ""}>{siteLabel}</span>
            <span>{lead.telefono || "Telefono N/D"}</span>
            {lead.facebook_url && lead.facebook_url !== "N/D" && lead.facebook_url !== "N/F" && (
              <a
                href={lead.facebook_url}
                target="_blank"
                rel="noopener"
                style={{ color: "#1877F2", fontWeight: 600, fontSize: "10px" }}
                onClick={(e) => e.stopPropagation()}
              >
                Facebook
              </a>
            )}
          </div>
          <div className="lead-card-stato">
            {STATO_OPTIONS.map((option) => (
              <div
                key={option}
                role="button"
                tabIndex={0}
                className={`stato-btn stato-${option.toLowerCase()}${lead.stato === option ? " active" : ""}`}
                onClick={(e) => handleStatoClick(e, option)}
                onKeyDown={(e) => e.key === "Enter" && handleStatoClick(e, option)}
              >
                {option}
              </div>
            ))}
          </div>
        </div>
      </button>
    </div>
  );
});

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
  const [mapBounds, setMapBounds] = useState(null);
  const pendingPopupRef = useRef(null);
  const prevFilteredIdsRef = useRef(new Set());

  // Paginazione
  const [leadsTotal, setLeadsTotal] = useState(0);
  const [leadsPage, setLeadsPage] = useState(1);
  const [leadsHasMore, setLeadsHasMore] = useState(false);
  const [leadsLoadingMore, setLeadsLoadingMore] = useState(false);

  // Satellite
  const [tileLayerKey, setTileLayerKey] = useState("osm");

  // Autocomplete comuni
  const [comuni, setComuni] = useState([]);

  // Filtro Facebook
  const [onlyFacebook, setOnlyFacebook] = useState(false);

  // Scarta filter
  const [hideScartati, setHideScartati] = useState(true);

  // Score personalizzato
  const [scoreWeights, setScoreWeights] = useState(DEFAULT_WEIGHTS);
  const [scoreTargetCats, setScoreTargetCats] = useState([]);

  // Bulk selection
  const [selectedBulkIds, setSelectedBulkIds] = useState(new Set());

  // Site check job
  const [siteCheckJobId, setSiteCheckJobId] = useState("");
  const [siteCheckLoading, setSiteCheckLoading] = useState(false);
  const [siteCheckStatus, setSiteCheckStatus] = useState("");
  const [siteCheckProgress, setSiteCheckProgress] = useState(0);

  // Facebook enrichment
  const [facebookJobId, setFacebookJobId] = useState("");
  const [facebookLoading, setFacebookLoading] = useState(false);
  const [facebookStatus, setFacebookStatus] = useState("");
  const [facebookProgress, setFacebookProgress] = useState(0);

  // Modal aggiunta lead manuale
  const [showAddModal, setShowAddModal] = useState(false);
  const [addModalStep, setAddModalStep] = useState("url");
  const [parseUrlInput, setParseUrlInput] = useState("");
  const [parseLoading, setParseLoading] = useState(false);
  const [parseError, setParseError] = useState("");
  const [manualForm, setManualForm] = useState({
    nome: "", categoria: "", comune: "", indirizzo: "",
    lat: "", lon: "", telefono: "", email: "", sito: "", facebook_url: ""
  });
  const [saveLeadLoading, setSaveLeadLoading] = useState(false);

  const activeDataset = useMemo(
    () => datasets.find((dataset) => dataset.datasetId === activeDatasetId) || datasets[0] || null,
    [datasets, activeDatasetId]
  );

  // Stable refs so focusLead + selection effect can avoid O(n) lookups
  const leadsRef = useRef(leads);
  const leadsMapRef = useRef(new Map());
  const filteredLeadsRef = useRef([]);
  const selectedLeadIdRef = useRef(selectedLeadId);
  useEffect(() => {
    leadsRef.current = leads;
    leadsMapRef.current = new Map(leads.map((l) => [l.id, l]));
  }, [leads]);
  useEffect(() => { selectedLeadIdRef.current = selectedLeadId; }, [selectedLeadId]);

  const categories = useMemo(
    () => [...new Set(leads.map((lead) => lead.categoria).filter(Boolean))].sort((a, b) => a.localeCompare(b)),
    [leads]
  );

  const filteredLeads = useMemo(() => {
    const query = deferredSearch.trim().toLowerCase();
    const result = leads.filter((lead) => {
      const matchesSearch =
        !query ||
        [lead.nome, lead.categoria, lead.comune, lead.telefono, lead.sito]
          .filter(Boolean)
          .some((value) => String(value).toLowerCase().includes(query));
      const matchesPriority = selectedPriorities.has(lead.priorita);
      const matchesHotlist = !onlyHotlist || lead.in_hotlist;
      const matchesSite = !onlyWithoutSite || lead.ha_sito === "NO" || lead.ha_sito === "MORTO";
      const matchesCategory = !selectedCategory || lead.categoria === selectedCategory;
      const matchesFacebook = !onlyFacebook || (lead.facebook_url && lead.facebook_url !== "N/D" && lead.facebook_url !== "N/F");
      const matchesScartati = !hideScartati || lead.stato !== "Scartata";
      return matchesSearch && matchesPriority && matchesHotlist && matchesSite && matchesCategory && matchesFacebook && matchesScartati;
    });
    filteredLeadsRef.current = result;
    return result;
  }, [deferredSearch, hideScartati, leads, onlyFacebook, onlyHotlist, onlyWithoutSite, selectedCategory, selectedPriorities]);

  const localScoringActive = useMemo(
    () =>
      scoreWeights.dist !== DEFAULT_WEIGHTS.dist ||
      scoreWeights.sito !== DEFAULT_WEIGHTS.sito ||
      scoreWeights.cat !== DEFAULT_WEIGHTS.cat ||
      scoreTargetCats.length > 0,
    [scoreWeights, scoreTargetCats]
  );

  const scoredLeads = useMemo(() => {
    if (!localScoringActive) return filteredLeads;
    const maxDist = Math.max(50, ...filteredLeads.map((l) => l.distanza_km));
    return [...filteredLeads]
      .map((lead) => {
        const s = computeLocalScore(lead, scoreWeights, scoreTargetCats, maxDist);
        return { ...lead, _localScore: s, _localPriority: scoreToPriority(s) };
      })
      .sort((a, b) => b._localScore - a._localScore);
  }, [filteredLeads, localScoringActive, scoreTargetCats, scoreWeights]);

  const mapZoom = mapBounds?.zoom ?? 12;
  const isClusterMode = mapZoom < CLUSTER_ZOOM_THRESHOLD;
  const prevClusterModeRef = useRef(isClusterMode);

  // Cluster per comune (solo quando zoom < soglia)
  const cityGroups = useMemo(() => {
    if (!isClusterMode) return null;
    const groups = new Map();
    filteredLeads.forEach((lead) => {
      const key = lead.comune || "N/D";
      if (!groups.has(key)) groups.set(key, { name: key, count: 0, latSum: 0, lonSum: 0 });
      const g = groups.get(key);
      g.count++;
      g.latSum += lead.lat;
      g.lonSum += lead.lon;
    });
    return Array.from(groups.values()).map((g) => ({ ...g, lat: g.latSum / g.count, lon: g.lonSum / g.count }));
  }, [filteredLeads, isClusterMode]);

  // Solo i lead nel viewport corrente (con 25% di padding) — solo in modalità individuale
  const visibleLeads = useMemo(() => {
    if (isClusterMode || !mapBounds) return filteredLeads;
    const { n, s, e, w } = mapBounds;
    const latPad = (n - s) * 0.25;
    const lonPad = (e - w) * 0.25;
    return filteredLeads.filter(
      (lead) =>
        lead.id === selectedLeadId ||
        (lead.lat >= s - latPad && lead.lat <= n + latPad &&
         lead.lon >= w - lonPad && lead.lon <= e + lonPad)
    );
  }, [filteredLeads, mapBounds, selectedLeadId, isClusterMode]);

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

    const updateBounds = () => {
      const b = map.getBounds();
      setMapBounds({ n: b.getNorth(), s: b.getSouth(), e: b.getEast(), w: b.getWest(), zoom: map.getZoom() });
    };
    map.on("moveend", updateBounds);
    map.on("zoomend", updateBounds);
    map.whenReady(updateBounds);

    return () => {
      map.off("moveend", updateBounds);
      map.off("zoomend", updateBounds);
      map.remove();
      mapRef.current = null;
      markersLayerRef.current = null;
      markerRefs.current = new Map();
      prevFilteredIdsRef.current = new Set();
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
    if ("Notification" in window && Notification.permission === "default") {
      Notification.requestPermission();
    }
  }, []);

  function sendNotification(title, body) {
    if ("Notification" in window && Notification.permission === "granted") {
      new Notification(title, { body, icon: "/favicon.ico" });
    }
  }

  useEffect(() => {
    const savedJobId = window.localStorage.getItem(POPULATION_JOB_STORAGE_KEY);
    if (!savedJobId) return;
    setPopulateJobId(savedJobId);
    setPopulateLoading(true);
    setPopulateProgress(5);
    setPopulateStatus("Sto riprendendo il monitoraggio del popolamento...");
  }, []);

  useEffect(() => {
    const savedFbJobId = window.localStorage.getItem(FACEBOOK_JOB_STORAGE_KEY);
    if (!savedFbJobId) return;
    setFacebookJobId(savedFbJobId);
    setFacebookLoading(true);
    setFacebookProgress(5);
    setFacebookStatus("Sto riprendendo il monitoraggio della ricerca Facebook...");
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
          sendNotification("Morpheus — Scansione completata", payload.message || "Dataset pronto.");
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
      setLeadsTotal(0);
      setLeadsPage(1);
      setLeadsHasMore(false);
      return;
    }
    setLeadsLoading(true);
    setLeadsError("");
    try {
      const params = new URLSearchParams({ dataset_id: datasetId, page: 1, page_size: PAGE_SIZE });
      const response = await fetch(`/api/leads?${params.toString()}`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = await response.json();
      const raw = payload.leads ?? payload;
      const nextLeads = normalizeLeads(Array.isArray(raw) ? raw : []);
      startTransition(() => {
        setLeads(nextLeads);
      });
      setLeadsTotal(payload.total ?? nextLeads.length);
      setLeadsPage(1);
      setLeadsHasMore(payload.has_more ?? false);
      setSelectedLeadId(nextLeads[0]?.id ?? null);
    } catch (error) {
      setLeads([]);
      setSelectedLeadId(null);
      setLeadsTotal(0);
      setLeadsHasMore(false);
      setLeadsError("Endpoint /api/leads non disponibile o vuoto.");
    } finally {
      setLeadsLoading(false);
    }
  }

  async function loadMoreLeads() {
    if (!activeDatasetId || leadsLoadingMore || !leadsHasMore) return;
    setLeadsLoadingMore(true);
    const nextPage = leadsPage + 1;
    try {
      const params = new URLSearchParams({ dataset_id: activeDatasetId, page: nextPage, page_size: PAGE_SIZE });
      const response = await fetch(`/api/leads?${params.toString()}`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = await response.json();
      const raw = payload.leads ?? payload;
      const moreLeads = normalizeLeads(Array.isArray(raw) ? raw : []);
      startTransition(() => {
        setLeads((current) => [...current, ...moreLeads]);
      });
      setLeadsPage(nextPage);
      setLeadsHasMore(payload.has_more ?? false);
    } catch (_) {
      // silenzioso
    } finally {
      setLeadsLoadingMore(false);
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

  useEffect(() => {
    if (!activeDatasetId) { setComuni([]); return; }
    fetch(`/api/comuni?dataset_id=${encodeURIComponent(activeDatasetId)}`)
      .then((r) => r.json())
      .then((data) => setComuni(Array.isArray(data) ? data : []))
      .catch(() => setComuni([]));
  }, [activeDatasetId]);

  const focusLead = useCallback((leadId, pan = true) => {
    const lead =
      filteredLeadsRef.current.find((item) => item.id === leadId) ||
      leadsRef.current.find((item) => item.id === leadId);
    if (!lead) return;
    setSelectedLeadId(leadId);
    if (!mapRef.current) return;
    if (pan) {
      mapRef.current.flyTo([lead.lat, lead.lon], Math.max(mapRef.current.getZoom(), 15), {
        duration: 0.45
      });
    }
    const marker = markerRefs.current.get(leadId);
    if (marker) {
      marker.openPopup();
    } else {
      // Il marker non è ancora in viewport: verrà creato dopo moveend
      pendingPopupRef.current = leadId;
    }
  }, []);

  useEffect(() => {
    if (!markersLayerRef.current) {
      prevClusterModeRef.current = isClusterMode;
      return;
    }
    if (prevClusterModeRef.current === isClusterMode) return;

    markersLayerRef.current.clearLayers();
    markerRefs.current = new Map();
    prevFilteredIdsRef.current = new Set();
    prevClusterModeRef.current = isClusterMode;
  }, [isClusterMode]);

  // Modalità cluster: un pallino per comune con conteggio
  useEffect(() => {
    if (!markersLayerRef.current || !isClusterMode || cityGroups === null) return;
    markersLayerRef.current.clearLayers();
    markerRefs.current = new Map();
    prevFilteredIdsRef.current = new Set();

    cityGroups.forEach((group) => {
      const marker = L.marker([group.lat, group.lon], { icon: makeCityIcon(group.count) });
      marker.bindPopup(`<b>${escapeHtml(group.name)}</b><br>${group.count} lead`);
      marker.on("click", () => {
        if (mapRef.current) mapRef.current.setView([group.lat, group.lon], CLUSTER_ZOOM_THRESHOLD + 1);
      });
      marker.addTo(markersLayerRef.current);
    });
  }, [cityGroups, isClusterMode]);

  // Modalità individuale: viewport culling + aggiornamento incrementale
  useEffect(() => {
    if (!markersLayerRef.current || isClusterMode) return;
    const nextIds = new Set(visibleLeads.map((l) => l.id));

    // Rimuovi i marker usciti dal viewport o dal filtro
    prevFilteredIdsRef.current.forEach((id) => {
      if (!nextIds.has(id)) {
        const marker = markerRefs.current.get(id);
        if (marker) markersLayerRef.current.removeLayer(marker);
        markerRefs.current.delete(id);
      }
    });

    // Aggiungi solo i marker entrati nel viewport o nel filtro
    visibleLeads.forEach((lead) => {
      if (!prevFilteredIdsRef.current.has(lead.id)) {
        let marker;
        if (lead.in_hotlist) {
          marker = L.marker([lead.lat, lead.lon], { icon: makeStarIcon(false), zIndexOffset: 0 });
        } else {
          const color = PRIORITY_COLORS[lead.priorita] || "#adb5bd";
          marker = L.circleMarker([lead.lat, lead.lon], {
            radius: 5, color, fillColor: color, fillOpacity: 0.8, weight: 1
          });
        }
        marker.bindPopup(buildPopupHtml(lead), { maxWidth: 280 });
        marker.on("click", () => setSelectedLeadId(lead.id));
        marker.addTo(markersLayerRef.current);
        markerRefs.current.set(lead.id, marker);
        applyMarkerSelection(marker, lead, lead.id === selectedLeadIdRef.current);
        if (pendingPopupRef.current === lead.id) {
          marker.openPopup();
          pendingPopupRef.current = null;
        }
      }
    });

    prevFilteredIdsRef.current = nextIds;
  }, [visibleLeads, isClusterMode]);

  // Aggiorna SOLO i 2 marker che cambiano (prev → deselect, next → select) — O(1)
  const prevSelectedIdRef = useRef(null);
  useEffect(() => {
    const prevId = prevSelectedIdRef.current;
    if (prevId !== selectedLeadId) {
      if (prevId) {
        const lead = leadsMapRef.current.get(prevId);
        const marker = markerRefs.current.get(prevId);
        if (lead && marker) applyMarkerSelection(marker, lead, false);
      }
      if (selectedLeadId) {
        const lead = leadsMapRef.current.get(selectedLeadId);
        const marker = markerRefs.current.get(selectedLeadId);
        if (lead && marker) applyMarkerSelection(marker, lead, true);
      }
      prevSelectedIdRef.current = selectedLeadId;
    }
  }, [selectedLeadId]);

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
    setOnlyFacebook(false);
    setHideScartati(true);
    setSelectedCategory("");
    setSelectedPriorities(new Set(PRIORITY_OPTIONS));
    setSelectedBulkIds(new Set());
    setScoreWeights(DEFAULT_WEIGHTS);
    setScoreTargetCats([]);
  }

  // Satellite / tile layer switch
  useEffect(() => {
    const map = mapRef.current;
    const tile = tileLayerRef.current;
    if (!map || !tile) return;
    const layerCfg = TILE_LAYERS[tileLayerKey] || TILE_LAYERS.osm;
    tile.setUrl(layerCfg.url);
  }, [tileLayerKey]);

  // Polling job Facebook
  useEffect(() => {
    if (!facebookJobId) return undefined;
    let cancelled = false;

    const pollJob = async () => {
      try {
        const response = await fetch(`/api/jobs/${facebookJobId}`);
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
        if (cancelled) return;

        setFacebookLoading(payload.status === "queued" || payload.status === "running");
        setFacebookProgress(Number(payload.progress ?? 0));
        setFacebookStatus(payload.message || "Ricerca Facebook in corso...");

        if (payload.status === "completed" || payload.status === "error" || payload.status === "interrupted") {
          window.localStorage.removeItem(FACEBOOK_JOB_STORAGE_KEY);
          setFacebookJobId("");
          setFacebookLoading(false);
          if (payload.status === "completed") {
            sendNotification("Morpheus — Facebook completato", payload.message || "Arricchimento completato.");
            if (activeDatasetId) loadLeads(activeDatasetId);
          }
        }
      } catch (error) {
        if (!cancelled) setFacebookStatus(error.message || "Errore nel monitoraggio Facebook.");
      }
    };

    pollJob();
    const intervalId = window.setInterval(pollJob, 2000);
    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [facebookJobId]);

  // Polling job site-check
  useEffect(() => {
    if (!siteCheckJobId) return undefined;
    let cancelled = false;

    const pollJob = async () => {
      try {
        const response = await fetch(`/api/jobs/${siteCheckJobId}`);
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
        if (cancelled) return;

        setSiteCheckLoading(payload.status === "queued" || payload.status === "running");
        setSiteCheckProgress(Number(payload.progress ?? 0));
        setSiteCheckStatus(payload.message || "Verifica in corso...");

        if (payload.status === "completed" || payload.status === "error" || payload.status === "interrupted") {
          window.localStorage.removeItem(SITE_CHECK_JOB_STORAGE_KEY);
          setSiteCheckJobId("");
          setSiteCheckLoading(false);
          if (payload.status === "completed") {
            sendNotification("Morpheus — Verifica siti completata", payload.message || "Verifica completata.");
            if (activeDatasetId) loadLeads(activeDatasetId);
          }
        }
      } catch (error) {
        if (!cancelled) setSiteCheckStatus(error.message || "Errore monitoraggio verifica siti.");
      }
    };

    pollJob();
    const intervalId = window.setInterval(pollJob, 2000);
    return () => { cancelled = true; window.clearInterval(intervalId); };
  }, [siteCheckJobId]);

  async function handleStartSiteCheck() {
    if (!activeDatasetId) return;
    setSiteCheckLoading(true);
    setSiteCheckProgress(1);
    setSiteCheckStatus("Avvio verifica siti...");
    try {
      const response = await fetch(`/api/datasets/${activeDatasetId}/check-sites`, { method: "POST" });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "Errore avvio verifica");
      setSiteCheckJobId(payload.job_id);
      window.localStorage.setItem(SITE_CHECK_JOB_STORAGE_KEY, payload.job_id);
    } catch (error) {
      setSiteCheckLoading(false);
      setSiteCheckStatus(error.message || "Errore avvio verifica siti");
    }
  }

  function handleToggleBulkSelect(leadId) {
    setSelectedBulkIds((prev) => {
      const next = new Set(prev);
      if (next.has(leadId)) next.delete(leadId);
      else next.add(leadId);
      return next;
    });
  }

  function handleSelectAllVisible() {
    setSelectedBulkIds((prev) => {
      const visible = scoredLeads.slice(0, 300).map((l) => l.id);
      const allSelected = visible.every((id) => prev.has(id));
      if (allSelected) return new Set();
      return new Set(visible);
    });
  }

  async function handleBulkAction(updates) {
    const ids = [...selectedBulkIds];
    if (!ids.length) return;
    // Optimistic update
    setLeads((prev) =>
      prev.map((l) => ids.includes(l.id) ? { ...l, ...updates } : l)
    );
    setSelectedBulkIds(new Set());
    try {
      await fetch("/api/leads", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ids, updates }),
      });
    } catch {
      // revert on error — reload from server
      loadLeads(activeDatasetId);
    }
  }

  async function handleParseUrl() {
    if (!parseUrlInput.trim()) return;
    setParseLoading(true);
    setParseError("");
    try {
      const res = await fetch("/api/leads/parse-url", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: parseUrlInput.trim() }),
      });
      const data = await res.json();
      if (!res.ok) {
        setParseError(data.error || "Parsing fallito");
      } else {
        setManualForm({
          nome: data.nome || "",
          categoria: data.categoria || "",
          comune: data.comune || "",
          indirizzo: data.indirizzo || "",
          lat: data.lat != null ? String(data.lat) : "",
          lon: data.lon != null ? String(data.lon) : "",
          telefono: data.telefono || "",
          email: data.email || "",
          sito: data.sito || "",
          facebook_url: data.facebook_url || "",
        });
      }
    } catch {
      setParseError("Errore di rete durante il parsing");
    } finally {
      setParseLoading(false);
      setAddModalStep("form");
    }
  }

  async function handleSaveLead() {
    if (!manualForm.nome.trim() || !activeDatasetId) return;
    setSaveLeadLoading(true);
    try {
      const res = await fetch("/api/leads", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          dataset_id: activeDatasetId,
          ...manualForm,
          lat: manualForm.lat !== "" ? parseFloat(manualForm.lat) : null,
          lon: manualForm.lon !== "" ? parseFloat(manualForm.lon) : null,
        }),
      });
      if (res.ok) {
        setShowAddModal(false);
        setParseUrlInput("");
        setParseError("");
        setAddModalStep("url");
        setManualForm({ nome: "", categoria: "", comune: "", indirizzo: "", lat: "", lon: "", telefono: "", email: "", sito: "", facebook_url: "" });
        const leadsRes = await fetch(`/api/leads?dataset_id=${encodeURIComponent(activeDatasetId)}&page_size=${PAGE_SIZE}`);
        const leadsData = await leadsRes.json();
        setLeads(normalizeLeads(Array.isArray(leadsData) ? leadsData : leadsData.leads || []));
      }
    } finally {
      setSaveLeadLoading(false);
    }
  }

  async function handleStartFacebookEnrichment() {
    if (!activeDatasetId) return;
    setFacebookLoading(true);
    setFacebookProgress(1);
    setFacebookStatus("Avvio ricerca profili Facebook...");
    try {
      const response = await fetch(`/api/datasets/${activeDatasetId}/enrich/facebook`, {
        method: "POST",
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "Errore avvio Facebook");
      setFacebookJobId(payload.job_id);
      window.localStorage.setItem(FACEBOOK_JOB_STORAGE_KEY, payload.job_id);
    } catch (error) {
      setFacebookLoading(false);
      setFacebookStatus(error.message || "Errore avvio ricerca Facebook");
    }
  }

  async function handleUpdateStato(leadId, prevStato, newStato) {
    setLeads((prev) => prev.map((l) => l.id === leadId ? { ...l, stato: newStato } : l));
    try {
      const res = await fetch(`/api/leads/${encodeURIComponent(leadId)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ stato: newStato }),
      });
      if (!res.ok) {
        setLeads((prev) => prev.map((l) => l.id === leadId ? { ...l, stato: prevStato } : l));
      }
    } catch {
      setLeads((prev) => prev.map((l) => l.id === leadId ? { ...l, stato: prevStato } : l));
    }
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
          <span className="panel-rail-title">{isSidebarCollapsed ? "Filtri" : "Morpheus"}</span>
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
                <h2>Arricchimento Facebook</h2>
                <span>{facebookLoading ? `${facebookProgress}%` : "opzionale"}</span>
              </div>
              <p className="helper-copy">
                Cerca automaticamente i profili Facebook pubblici per i lead senza link Facebook.
                Il processo è lento (1–2 s/lead) e può richiedere diversi minuti.
              </p>
              <button
                type="button"
                className="secondary-button block-button"
                onClick={handleStartFacebookEnrichment}
                disabled={facebookLoading || !activeDatasetId}
              >
                {facebookLoading ? "Ricerca in corso..." : "Cerca profili Facebook"}
              </button>
              {facebookStatus ? (
                <div className="progress-card">
                  {facebookLoading && (
                    <>
                      <div className="progress-head">
                        <strong>Ricerca Facebook</strong>
                        <span>{facebookProgress}%</span>
                      </div>
                      <div className="progress-track">
                        <div className="progress-fill" style={{ width: `${Math.max(facebookProgress, 4)}%` }} />
                      </div>
                    </>
                  )}
                  <div className="progress-copy">{facebookStatus}</div>
                </div>
              ) : null}
            </section>

            <section className="panel">
              <div className="panel-head">
                <h2>Verifica siti web</h2>
                <span>{siteCheckLoading ? `${siteCheckProgress}%` : "opzionale"}</span>
              </div>
              <p className="helper-copy">
                Controlla i lead con sito web registrato. Segna come "Sito morto" quelli non raggiungibili (404, timeout, dominio scaduto).
              </p>
              <button
                type="button"
                className="secondary-button block-button"
                onClick={handleStartSiteCheck}
                disabled={siteCheckLoading || !activeDatasetId}
              >
                {siteCheckLoading ? "Verifica in corso..." : "Verifica siti web"}
              </button>
              {siteCheckStatus ? (
                <div className="progress-card">
                  {siteCheckLoading && (
                    <>
                      <div className="progress-head">
                        <strong>Verifica siti</strong>
                        <span>{siteCheckProgress}%</span>
                      </div>
                      <div className="progress-track">
                        <div className="progress-fill" style={{ width: `${Math.max(siteCheckProgress, 4)}%` }} />
                      </div>
                    </>
                  )}
                  <div className="progress-copy">{siteCheckStatus}</div>
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
                  list="comuni-datalist"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Nome, comune, categoria..."
                />
                <datalist id="comuni-datalist">
                  {comuni.map((c) => <option key={c} value={c} />)}
                </datalist>
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

              <label className="toggle-row">
                <input
                  type="checkbox"
                  checked={onlyFacebook}
                  onChange={(event) => setOnlyFacebook(event.target.checked)}
                />
                Mostra solo lead con Facebook
              </label>

              <label className="toggle-row">
                <input
                  type="checkbox"
                  checked={!hideScartati}
                  onChange={(e) => setHideScartati(!e.target.checked)}
                />
                Mostra lead scartati
              </label>
            </section>

            <section className="panel">
              <div className="panel-head">
                <h2>Score personalizzato</h2>
                <button
                  type="button"
                  className="ghost-button"
                  onClick={() => { setScoreWeights(DEFAULT_WEIGHTS); setScoreTargetCats([]); }}
                >
                  Reset
                </button>
              </div>
              {localScoringActive && (
                <div className="helper-copy" style={{ background: "#f0fdf4", borderColor: "#86efac", color: "#166534" }}>
                  Score personalizzato attivo — lista riordinata
                </div>
              )}
              <div className="score-sliders">
                {[
                  { key: "dist", label: "Distanza" },
                  { key: "sito", label: "Senza sito" },
                  { key: "cat", label: "Categoria target" },
                ].map(({ key, label }) => (
                  <label key={key} className="score-slider-row">
                    <span className="score-slider-label">{label}</span>
                    <input
                      type="range"
                      min={0}
                      max={10}
                      value={scoreWeights[key]}
                      onChange={(e) => setScoreWeights((w) => ({ ...w, [key]: Number(e.target.value) }))}
                    />
                    <span className="score-slider-val">{scoreWeights[key]}</span>
                  </label>
                ))}
              </div>
              <label className="field" style={{ marginTop: 2 }}>
                <span>Categorie target (per peso categoria)</span>
                <select
                  multiple
                  value={scoreTargetCats}
                  onChange={(e) => setScoreTargetCats([...e.target.selectedOptions].map((o) => o.value))}
                  style={{ height: "90px", fontSize: "11px" }}
                >
                  {categories.map((c) => (
                    <option key={c} value={c}>{c}</option>
                  ))}
                </select>
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
              {filteredLeads.some((lead) => lead.ha_sito === "MORTO") && (
                <span className="stat-morto">{filteredLeads.filter((lead) => lead.ha_sito === "MORTO").length} siti morti</span>
              )}
              <span>{filteredLeads.filter((lead) => lead.stato === "Contattata").length} contattati</span>
            </div>
          </div>

          {leadsError ? <div className="notice">{leadsError}</div> : null}

          <div className="map-stage">
            <div ref={mapContainerRef} className="map-canvas" />
            <div className="map-layer-toggle">
              {Object.entries(TILE_LAYERS).map(([key, cfg]) => (
                <button
                  key={key}
                  type="button"
                  className={`layer-btn ${tileLayerKey === key ? "active" : ""}`}
                  onClick={() => setTileLayerKey(key)}
                  title={cfg.label}
                >
                  {cfg.label}
                </button>
              ))}
            </div>
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
            {!isListCollapsed && activeDatasetId && (
              <>
                <a
                  href={buildExportUrl({ datasetId: activeDatasetId, onlyHotlist, onlyWithoutSite, selectedCategory })}
                  download
                  className="ghost-button"
                  title="Esporta CSV con i filtri correnti"
                  style={{ fontSize: "11px", padding: "4px 8px" }}
                >
                  ↓ CSV
                </a>
                <button
                  type="button"
                  className="ghost-button"
                  title="Aggiungi attività manualmente"
                  style={{ fontSize: "13px", fontWeight: 700, padding: "3px 8px" }}
                  onClick={() => { setShowAddModal(true); setAddModalStep("url"); setParseError(""); setParseUrlInput(""); }}
                >
                  +
                </button>
              </>
            )}
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
              {selectedBulkIds.size > 0 && (
                <div className="bulk-bar">
                  <span className="bulk-bar-count">{selectedBulkIds.size} selezionati</span>
                  <button type="button" className="bulk-action-btn bulk-ok" onClick={() => handleBulkAction({ stato: "Contattata" })}>Contattata</button>
                  <button type="button" className="bulk-action-btn bulk-no" onClick={() => handleBulkAction({ stato: "Rifiutata" })}>Rifiutata</button>
                  <button type="button" className="bulk-action-btn" onClick={() => handleBulkAction({ stato: "" })}>Rimuovi stato</button>
                  <button type="button" className="bulk-action-btn" onClick={() => handleBulkAction({ in_hotlist: true })}>+ Hotlist</button>
                  <button type="button" className="bulk-action-btn" onClick={() => setSelectedBulkIds(new Set())}>✕</button>
                </div>
              )}

              <div className="lead-list">
                {filteredLeads.length ? (
                  <>
                    <div className="bulk-select-all">
                      <button type="button" className="ghost-button" style={{ fontSize: "10px", padding: "2px 8px" }} onClick={handleSelectAllVisible}>
                        {scoredLeads.slice(0, 300).every((l) => selectedBulkIds.has(l.id)) ? "Deseleziona tutti" : "Seleziona tutti"}
                      </button>
                    </div>
                    {scoredLeads.slice(0, 300).map((lead, index) => (
                      <LeadCard
                        key={lead.id}
                        lead={lead}
                        index={index}
                        active={lead.id === selectedLeadId}
                        selected={selectedBulkIds.has(lead.id)}
                        onClick={() => focusLead(lead.id)}
                        onUpdateStato={handleUpdateStato}
                        onToggleSelect={handleToggleBulkSelect}
                      />
                    ))}
                    {scoredLeads.length > 300 && (
                      <div className="empty-state" style={{ fontSize: "0.8rem" }}>
                        +{scoredLeads.length - 300} lead non visualizzati. Usa i filtri per restringere.
                      </div>
                    )}
                  </>
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

      {showAddModal && (
        <div
          style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.45)", zIndex: 9999, display: "flex", alignItems: "center", justifyContent: "center" }}
          onClick={(e) => { if (e.target === e.currentTarget) setShowAddModal(false); }}
        >
          <div style={{ background: "#fff", borderRadius: "var(--radius-md)", padding: "20px 22px", width: "420px", maxWidth: "95vw", maxHeight: "90vh", overflowY: "auto", boxShadow: "var(--shadow-md)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "14px" }}>
              <span style={{ fontWeight: 700, fontSize: "14px", display: "flex", alignItems: "center", gap: "6px" }}>
                {addModalStep === "form" && (
                  <button onClick={() => setAddModalStep("url")} style={{ background: "none", border: "none", cursor: "pointer", fontSize: "16px", color: "var(--text-2)", padding: 0, lineHeight: 1 }}>←</button>
                )}
                {addModalStep === "url" ? "Aggiungi attività" : "Dati attività"}
              </span>
              <button onClick={() => setShowAddModal(false)} style={{ background: "none", border: "none", cursor: "pointer", fontSize: "20px", color: "var(--text-3)", lineHeight: 1 }}>✕</button>
            </div>

            {addModalStep === "url" && (
              <>
                <div style={{ fontSize: "12px", color: "var(--text-2)", marginBottom: "8px" }}>
                  Incolla un link Facebook o Google Maps per estrarre i dati automaticamente:
                </div>
                <input
                  type="text"
                  className="field"
                  placeholder="https://facebook.com/... o https://maps.google.com/..."
                  value={parseUrlInput}
                  onChange={(e) => setParseUrlInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleParseUrl()}
                  style={{ marginBottom: "8px" }}
                />
                {parseError && <div style={{ fontSize: "11px", color: "var(--danger)", marginBottom: "8px" }}>{parseError}</div>}
                <button
                  className="btn-primary"
                  onClick={handleParseUrl}
                  disabled={parseLoading || !parseUrlInput.trim()}
                  style={{ marginBottom: "8px" }}
                >
                  {parseLoading ? "Analisi in corso..." : "Analizza URL"}
                </button>
                <button
                  onClick={() => { setManualForm({ nome: "", categoria: "", comune: "", indirizzo: "", lat: "", lon: "", telefono: "", email: "", sito: "", facebook_url: "" }); setAddModalStep("form"); }}
                  style={{ background: "none", border: "none", cursor: "pointer", fontSize: "12px", color: "var(--text-3)", display: "block", textAlign: "center", width: "100%" }}
                >
                  Compila manualmente senza URL
                </button>
              </>
            )}

            {addModalStep === "form" && (
              <>
                {[
                  { label: "Nome *", key: "nome", type: "text" },
                  { label: "Comune", key: "comune", type: "text" },
                  { label: "Indirizzo", key: "indirizzo", type: "text" },
                  { label: "Lat", key: "lat", type: "number" },
                  { label: "Lon", key: "lon", type: "number" },
                  { label: "Telefono", key: "telefono", type: "text" },
                  { label: "Email", key: "email", type: "text" },
                  { label: "Sito web", key: "sito", type: "text" },
                  { label: "Facebook", key: "facebook_url", type: "text" },
                ].map(({ label, key, type }) => (
                  <div key={key} style={{ marginBottom: "8px" }}>
                    <div style={{ fontSize: "11px", fontWeight: 600, color: "var(--text-2)", marginBottom: "3px" }}>{label}</div>
                    <input
                      type={type}
                      className="field"
                      value={manualForm[key]}
                      onChange={(e) => setManualForm((f) => ({ ...f, [key]: e.target.value }))}
                      style={{ marginBottom: 0 }}
                    />
                  </div>
                ))}
                <div style={{ marginBottom: "12px" }}>
                  <div style={{ fontSize: "11px", fontWeight: 600, color: "var(--text-2)", marginBottom: "3px" }}>Categoria</div>
                  <select
                    className="field"
                    value={manualForm.categoria}
                    onChange={(e) => setManualForm((f) => ({ ...f, categoria: e.target.value }))}
                    style={{ marginBottom: 0 }}
                  >
                    <option value="">— seleziona —</option>
                    {CATEGORIE.map((c) => <option key={c} value={c}>{c}</option>)}
                  </select>
                </div>
                <div style={{ display: "flex", gap: "8px" }}>
                  <button onClick={() => setShowAddModal(false)} style={{ flex: 1, padding: "8px", fontSize: "12px", background: "var(--surface)", border: "1px solid var(--border-strong)", borderRadius: "var(--radius-sm)", cursor: "pointer", fontFamily: "inherit" }}>
                    Annulla
                  </button>
                  <button
                    className="btn-primary"
                    onClick={handleSaveLead}
                    disabled={saveLeadLoading || !manualForm.nome.trim()}
                    style={{ flex: 1, marginTop: 0 }}
                  >
                    {saveLeadLoading ? "Salvataggio..." : "Salva lead"}
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
