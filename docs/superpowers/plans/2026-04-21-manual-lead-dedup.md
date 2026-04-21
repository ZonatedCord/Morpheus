# Manual Lead Entry + Cross-Dataset Deduplication — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow manual lead insertion from Facebook/Google Maps URLs, and deduplicate leads at import time when appending to an existing dataset.

**Architecture:** Two independent changes — (1) dedup logic in `import_from_csv` via name+coords fingerprint set, (2) new `url_parser.py` module + `create_manual_lead()` in `db.py` + two new Flask endpoints + React modal in `App.jsx`.

**Tech Stack:** Python 3.13 + Flask, SQLite, React 18 + Vite, `requests` (already in venv)

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `src/morpheus/url_parser.py` | CREATE | Parse Facebook + Google Maps URLs |
| `src/morpheus/db.py` | MODIFY | `_norm_dedup()`, `create_manual_lead()`, dedup in `import_from_csv()` |
| `app.py` | MODIFY | `POST /api/leads/parse-url`, `POST /api/leads` endpoints |
| `frontend/src/App.jsx` | MODIFY | Modal UI, "+" button, badge "Manuale" |

---

## Task 1: Deduplicazione in `import_from_csv` (db.py)

**Files:**
- Modify: `src/morpheus/db.py`

- [ ] **Step 1: Aggiungi `_norm_dedup` dopo `_clean_merge_value`**

In `src/morpheus/db.py`, dopo la funzione `_clean_merge_value` (riga ~169), aggiungi:

```python
def _norm_dedup(nome: str, lat: float | None, lon: float | None) -> tuple:
    return (
        _slugify(nome),
        round(lat, 3) if lat is not None else None,
        round(lon, 3) if lon is not None else None,
    )
```

- [ ] **Step 2: Modifica `import_from_csv` — carica fingerprint esistenti**

In `import_from_csv()`, subito dopo il blocco `existing_scores = { ... }` (riga ~360-369), aggiungi:

```python
    existing_fingerprints: set[tuple] = set()
    if not replace_dataset:
        existing_fingerprints = {
            _norm_dedup(r[0], r[1], r[2])
            for r in conn.execute(
                "SELECT nome, lat, lon FROM attivita WHERE dataset_id = ? AND lat IS NOT NULL AND lon IS NOT NULL",
                (resolved_dataset_id,),
            ).fetchall()
        }
```

- [ ] **Step 3: Modifica `import_from_csv` — filtra righe duplicate**

Sostituisci il blocco che costruisce `rows`:

```python
    rows = []
    seen_ids: dict[str, int] = {}
```

con:

```python
    rows = []
    seen_ids: dict[str, int] = {}
    seen_in_batch: set[tuple] = set()
    skipped_dedup = 0
```

Poi, all'interno del loop `for row in csv.DictReader(handle):`, prima di `rows.append(...)`, aggiungi il check di dedup. Trova il punto dove `record_id` e le variabili `lat`/`lon` sono già definite, subito prima di `rows.append(`:

```python
            fp = _norm_dedup(nome, lat, lon)
            if fp in existing_fingerprints or fp in seen_in_batch:
                skipped_dedup += 1
                continue
            seen_in_batch.add(fp)
```

- [ ] **Step 4: Aggiungi log del dedup**

Trova la print finale in `import_from_csv` (riga ~528):

```python
    print(
        f"  Importate {dataset_count} attività nel dataset '{resolved_dataset_id}' "
        f"({with_coords} con coordinate, {in_hotlist} in hotlist, {with_scores} con score LLM)"
    )
```

Sostituisci con:

```python
    dedup_msg = f", {skipped_dedup} duplicati saltati" if skipped_dedup else ""
    print(
        f"  Importate {dataset_count} attività nel dataset '{resolved_dataset_id}' "
        f"({with_coords} con coordinate, {in_hotlist} in hotlist, {with_scores} con score LLM{dedup_msg})"
    )
```

- [ ] **Step 5: Verifica manuale**

```bash
cd /Users/marcobarlera/Documents/02_PROGETTI/Morpheus
.venv/bin/python3 -c "
from src.morpheus.db import _norm_dedup
print(_norm_dedup('Bar Bello', 45.1234, 8.4567))   # ('bar-bello', 45.123, 8.457)
print(_norm_dedup('Bar Bello', 45.1235, 8.4568))   # stessa fingerprint → dedup
print(_norm_dedup('', None, None))                  # ('', None, None)
"
```

Output atteso:
```
('bar-bello', 45.123, 8.457)
('bar-bello', 45.124, 8.457)
('', None, None)
```

- [ ] **Step 6: Commit**

```bash
git add src/morpheus/db.py
git commit -m "feat(db): deduplicate leads by name+coords on append import"
```

---

## Task 2: `create_manual_lead` in db.py

**Files:**
- Modify: `src/morpheus/db.py`

- [ ] **Step 1: Aggiungi `uuid4` e `math` agli import**

In cima a `src/morpheus/db.py`, aggiungi agli import esistenti:

```python
import math
from uuid import uuid4
```

- [ ] **Step 2: Aggiungi `create_manual_lead` in fondo al file (prima della sezione CSV export)**

Aggiungi dopo la sezione `# ── Dataset deletion ───` e prima di `# ── Distinct comuni ────`:

```python
# ── Manual lead creation ──────────────────────────────────────────────────────

_MANUAL_LEAD_FIELDS = {
    "nome", "lat", "lon", "categoria", "comune",
    "indirizzo", "telefono", "email", "sito", "facebook_url",
}

def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return round(r * 2 * math.asin(math.sqrt(a)), 2)


def _score_to_priority(score: float) -> str:
    if score >= 0.75:
        return "ALTISSIMA"
    if score >= 0.55:
        return "ALTA"
    if score >= 0.35:
        return "MEDIA"
    if score >= 0.20:
        return "BASSA"
    return "MOLTO BASSA"


def create_manual_lead(
    dataset_id: str,
    fields: dict[str, Any],
    db_path: Path = DB_PATH,
) -> dict | None:
    """Insert a manually-entered lead into the given dataset.

    Returns the full row as dict, or None if dataset not found or nome missing.
    """
    nome = (fields.get("nome") or "").strip()
    if not nome:
        return None

    init_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    dataset_row = conn.execute(
        "SELECT reference_lat, reference_lon FROM dataset_runs WHERE dataset_id = ?",
        (dataset_id,),
    ).fetchone()
    if dataset_row is None:
        conn.close()
        return None

    ref_lat = dataset_row["reference_lat"]
    ref_lon = dataset_row["reference_lon"]

    try:
        lat = float(fields["lat"]) if fields.get("lat") not in (None, "") else None
        lon = float(fields["lon"]) if fields.get("lon") not in (None, "") else None
    except (TypeError, ValueError):
        lat = lon = None

    sito = (fields.get("sito") or "").strip()
    if sito == "N/D":
        sito = ""
    ha_sito = "SI" if sito else "NO"

    distanza_km = 0.0
    priorita = "BASSA"
    if lat is not None and lon is not None and ref_lat is not None and ref_lon is not None:
        distanza_km = _haversine_km(ref_lat, ref_lon, lat, lon)
        max_dist = 50.0
        dist_norm = max(0.0, 1.0 - distanza_km / max_dist)
        assenza_sito = 1.0 if ha_sito == "NO" else 0.0
        score = 0.5 * dist_norm + 0.3 * assenza_sito
        priorita = _score_to_priority(score)

    osm_url = f"manual://{uuid4().hex}"
    now = datetime.now().isoformat()

    conn.execute(
        """
        INSERT INTO attivita (
            osm_url, nome, lat, lon, priorita, distanza_km, categoria,
            sottocategoria, comune, indirizzo, telefono, email, sito,
            facebook_url, ha_sito, stato, proposta, criticita, rating,
            in_hotlist, rilevanza_score, rilevanza_motivazione,
            dataset_id, source_osm_url, aggiornato_il
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            osm_url, nome, lat, lon, priorita, distanza_km,
            (fields.get("categoria") or "").strip(),
            "",
            (fields.get("comune") or "").strip(),
            (fields.get("indirizzo") or "").strip(),
            (fields.get("telefono") or "").strip(),
            (fields.get("email") or "").strip(),
            sito or "N/D",
            (fields.get("facebook_url") or "").strip(),
            ha_sito,
            "", "", "", "", 0, None, "",
            dataset_id, "manual", now,
        ),
    )
    conn.commit()

    row = conn.execute("SELECT * FROM attivita WHERE osm_url = ?", (osm_url,)).fetchone()
    conn.close()
    return dict(row) if row else None
```

- [ ] **Step 3: Verifica manuale**

```bash
.venv/bin/python3 -c "
import sys; sys.path.insert(0, 'src')
from morpheus.db import list_datasets, create_manual_lead
from morpheus.paths import DB_PATH
datasets = list_datasets(DB_PATH)
if datasets:
    did = datasets[0]['dataset_id']
    lead = create_manual_lead(did, {'nome': 'Test Manuale', 'lat': 45.77, 'lon': 8.88, 'categoria': 'Ristorazione'})
    print('OK:', lead['osm_url'], lead['priorita'], lead['distanza_km'])
else:
    print('Nessun dataset — ok per ora')
"
```

- [ ] **Step 4: Commit**

```bash
git add src/morpheus/db.py
git commit -m "feat(db): add create_manual_lead and haversine helpers"
```

---

## Task 3: `url_parser.py` — parsing Facebook e Google Maps

**Files:**
- Create: `src/morpheus/url_parser.py`

- [ ] **Step 1: Crea il modulo**

```python
# src/morpheus/url_parser.py
from __future__ import annotations

import re
from urllib.parse import unquote

import requests

_EMPTY_RESULT: dict = {
    "nome": "",
    "lat": None,
    "lon": None,
    "facebook_url": "",
    "sito": "",
    "comune": "",
    "categoria": "",
    "indirizzo": "",
    "telefono": "",
    "email": "",
}

_FB_SKIP_SLUGS = frozenset({
    "sharer", "share", "login", "home", "pages", "groups",
    "events", "photo", "video", "watch", "marketplace",
})


def _slug_to_name(slug: str) -> str:
    name = re.sub(r"[-_.]", " ", slug).strip()
    return " ".join(word.capitalize() for word in name.split() if word)


def _parse_facebook(url: str) -> dict:
    match = re.search(r"facebook\.com/([^/?#]+)", url)
    if not match:
        return {}
    slug = match.group(1).rstrip("/")
    if slug in _FB_SKIP_SLUGS:
        return {}
    nome = _slug_to_name(slug)
    facebook_url = f"https://www.facebook.com/{slug}"
    return {"nome": nome, "facebook_url": facebook_url}


def _parse_google_maps(url: str) -> dict:
    result: dict = {}
    place_match = re.search(r"/maps/place/([^/@?]+)", url)
    if place_match:
        raw = place_match.group(1)
        nome = unquote(raw).replace("+", " ").strip()
        if nome:
            result["nome"] = nome
    coord_match = re.search(r"@([-\d.]+),([-\d.]+)", url)
    if coord_match:
        try:
            result["lat"] = float(coord_match.group(1))
            result["lon"] = float(coord_match.group(2))
        except ValueError:
            pass
    return result


def _follow_redirect(url: str, timeout: int = 8) -> str:
    try:
        resp = requests.get(
            url,
            allow_redirects=True,
            timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0 (compatible; MorpheusBot/1.0)"},
        )
        return resp.url
    except Exception:
        return url


def parse_lead_url(url: str) -> dict:
    """Parse a Facebook or Google Maps URL and return pre-filled lead fields.

    Raises ValueError for unrecognized URL types.
    Missing fields are empty string or None.
    """
    url = url.strip()

    if "facebook.com" in url:
        data = _parse_facebook(url)
        return {**_EMPTY_RESULT, **data}

    if "maps.app.goo.gl" in url or "goo.gl/maps" in url:
        url = _follow_redirect(url)

    if "google.com/maps" in url or "maps.google.com" in url:
        data = _parse_google_maps(url)
        return {**_EMPTY_RESULT, **data}

    raise ValueError(f"URL non riconosciuto. Incolla un link Facebook o Google Maps.")
```

- [ ] **Step 2: Verifica manuale**

```bash
.venv/bin/python3 -c "
import sys; sys.path.insert(0, 'src')
from morpheus.url_parser import parse_lead_url

# Facebook
r = parse_lead_url('https://www.facebook.com/il-bar-bello-varese')
print('FB nome:', r['nome'], '| fb_url:', r['facebook_url'])

# Google Maps lungo
r = parse_lead_url('https://www.google.com/maps/place/Bar+Centrale/@45.7755,8.8872,17z')
print('GM nome:', r['nome'], '| lat:', r['lat'], '| lon:', r['lon'])

# URL non riconosciuto
try:
    parse_lead_url('https://instagram.com/foo')
except ValueError as e:
    print('ValueError ok:', e)
"
```

Output atteso:
```
FB nome: Il Bar Bello Varese | fb_url: https://www.facebook.com/il-bar-bello-varese
GM nome: Bar Centrale | lat: 45.7755 | lon: 8.8872
ValueError ok: URL non riconosciuto. ...
```

- [ ] **Step 3: Commit**

```bash
git add src/morpheus/url_parser.py
git commit -m "feat: add url_parser module for Facebook and Google Maps URL parsing"
```

---

## Task 4: Nuovi endpoint Flask

**Files:**
- Modify: `app.py`

- [ ] **Step 1: Aggiungi import in cima ad `app.py`**

Trova il blocco import in `app.py`. Aggiungi:

```python
from morpheus.url_parser import parse_lead_url
from morpheus.db import (
    # ... import esistenti ...
    create_manual_lead,   # ← aggiungi qui
)
```

Modifica la riga `from morpheus.db import (` per includere `create_manual_lead`.

- [ ] **Step 2: Aggiungi endpoint `POST /api/leads/parse-url`**

In `app.py`, subito prima della route `@app.route("/api/leads/export")`, aggiungi:

```python
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
```

- [ ] **Step 3: Aggiungi endpoint `POST /api/leads`**

Subito dopo l'endpoint `POST /api/leads/parse-url`, aggiungi:

```python
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
```

- [ ] **Step 4: Verifica manuale — avvia Flask e testa con curl**

```bash
# Terminale 1
.venv/bin/python3 app.py &

# Terminale 2 — test parse-url Facebook
curl -s -X POST http://localhost:5000/api/leads/parse-url \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.facebook.com/bar-bello-varese"}' | python3 -m json.tool

# test parse-url URL non riconosciuto
curl -s -X POST http://localhost:5000/api/leads/parse-url \
  -H "Content-Type: application/json" \
  -d '{"url": "https://instagram.com/foo"}' | python3 -m json.tool

# test POST /api/leads (sostituisci DATASET_ID con un id reale da GET /api/datasets)
DATASET_ID=$(curl -s http://localhost:5000/api/datasets | python3 -c "import sys,json; d=json.load(sys.stdin); print(d[0]['dataset_id'] if d else '')")
curl -s -X POST http://localhost:5000/api/leads \
  -H "Content-Type: application/json" \
  -d "{\"dataset_id\": \"$DATASET_ID\", \"nome\": \"Test Bar\", \"categoria\": \"Ristorazione\", \"comune\": \"Varese\"}" | python3 -m json.tool
```

Output atteso: JSON con `nome`, `facebook_url`, e per il POST un `id` che inizia con `manual://`.

- [ ] **Step 5: Commit**

```bash
git add app.py
git commit -m "feat(api): add POST /api/leads/parse-url and POST /api/leads endpoints"
```

---

## Task 5: Frontend — Modal aggiunta lead + badge "Manuale"

**Files:**
- Modify: `frontend/src/App.jsx`

- [ ] **Step 1: Aggiungi le costanti delle categorie**

In `App.jsx`, dopo le costanti esistenti (`PRIORITY_OPTIONS`, `DEFAULT_PROVINCE`, etc.), aggiungi:

```javascript
const CATEGORIE = [
  "Ristorazione", "Ospitalità", "Beauty & Benessere",
  "Fitness & Sport", "Sanità", "Servizi Professionali",
  "Artigiani", "Negozi", "Intrattenimento"
];
```

- [ ] **Step 2: Aggiungi stato per il modal**

Nel componente `App`, aggiungi dopo gli `useState` esistenti:

```javascript
const [showAddModal, setShowAddModal] = useState(false);
const [addModalStep, setAddModalStep] = useState("url"); // "url" | "form"
const [parseUrlInput, setParseUrlInput] = useState("");
const [parseLoading, setParseLoading] = useState(false);
const [parseError, setParseError] = useState("");
const [manualForm, setManualForm] = useState({
  nome: "", categoria: "", comune: "", indirizzo: "",
  lat: "", lon: "", telefono: "", email: "", sito: "", facebook_url: ""
});
const [saveLoading, setSaveLoading] = useState(false);
```

- [ ] **Step 3: Aggiungi handler `handleParseUrl`**

```javascript
const handleParseUrl = useCallback(async () => {
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
}, [parseUrlInput]);
```

- [ ] **Step 4: Aggiungi handler `handleSaveLead`**

```javascript
const handleSaveLead = useCallback(async () => {
  if (!manualForm.nome.trim()) return;
  setSaveLoading(true);
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
      setManualForm({ nome: "", categoria: "", comune: "", indirizzo: "", lat: "", lon: "", telefono: "", email: "", sito: "", facebook_url: "" });
      setAddModalStep("url");
      // Ricarica leads
      const leadsRes = await fetch(`/api/leads?dataset_id=${encodeURIComponent(activeDatasetId)}`);
      const leadsData = await leadsRes.json();
      setLeads(normalizeLeads(Array.isArray(leadsData) ? leadsData : leadsData.leads || []));
    }
  } finally {
    setSaveLoading(false);
  }
}, [manualForm, activeDatasetId]);
```

- [ ] **Step 5: Aggiungi bottone "+" nel header lista lead**

Trova nel JSX il pannello header della lista lead (cerca `lead-list-header` o il div con il bottone `↓ CSV`). Accanto al bottone CSV, aggiungi:

```jsx
<button
  onClick={() => { setShowAddModal(true); setAddModalStep("url"); setParseError(""); setParseUrlInput(""); }}
  title="Aggiungi attività manualmente"
  style={{
    padding: "4px 9px", fontSize: "14px", fontWeight: "700",
    background: "var(--brand)", color: "#fff", border: "none",
    borderRadius: "var(--radius-sm)", cursor: "pointer", lineHeight: 1
  }}
>+</button>
```

- [ ] **Step 6: Aggiungi il componente Modal**

Nel JSX del componente `App`, prima del tag di chiusura finale `</>`, aggiungi:

```jsx
{showAddModal && (
  <div style={{
    position: "fixed", inset: 0, background: "rgba(0,0,0,0.45)",
    zIndex: 9999, display: "flex", alignItems: "center", justifyContent: "center"
  }} onClick={e => { if (e.target === e.currentTarget) setShowAddModal(false); }}>
    <div style={{
      background: "#fff", borderRadius: "var(--radius-md)", padding: "20px 22px",
      width: "420px", maxWidth: "95vw", maxHeight: "90vh", overflowY: "auto",
      boxShadow: "var(--shadow-md)"
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "14px" }}>
        <span style={{ fontWeight: 700, fontSize: "14px" }}>
          {addModalStep === "url" ? "Aggiungi attività" : (addModalStep === "url" ? "" : "← ")}
          {addModalStep === "form" && (
            <button onClick={() => setAddModalStep("url")} style={{ background: "none", border: "none", cursor: "pointer", fontSize: "12px", color: "var(--text-2)", marginRight: "6px" }}>←</button>
          )}
          {addModalStep === "form" ? "Dati attività" : "Aggiungi attività"}
        </span>
        <button onClick={() => setShowAddModal(false)} style={{ background: "none", border: "none", cursor: "pointer", fontSize: "18px", color: "var(--text-3)" }}>✕</button>
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
            onChange={e => setParseUrlInput(e.target.value)}
            onKeyDown={e => e.key === "Enter" && handleParseUrl()}
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
                onChange={e => setManualForm(f => ({ ...f, [key]: e.target.value }))}
                style={{ marginBottom: 0 }}
              />
            </div>
          ))}
          <div style={{ marginBottom: "8px" }}>
            <div style={{ fontSize: "11px", fontWeight: 600, color: "var(--text-2)", marginBottom: "3px" }}>Categoria</div>
            <select
              className="field"
              value={manualForm.categoria}
              onChange={e => setManualForm(f => ({ ...f, categoria: e.target.value }))}
              style={{ marginBottom: 0 }}
            >
              <option value="">— seleziona —</option>
              {CATEGORIE.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          <div style={{ display: "flex", gap: "8px", marginTop: "12px" }}>
            <button onClick={() => setShowAddModal(false)} style={{ flex: 1, padding: "8px", fontSize: "12px", background: "var(--surface)", border: "1px solid var(--border-strong)", borderRadius: "var(--radius-sm)", cursor: "pointer" }}>
              Annulla
            </button>
            <button
              className="btn-primary"
              onClick={handleSaveLead}
              disabled={saveLoading || !manualForm.nome.trim()}
              style={{ flex: 1, marginTop: 0 }}
            >
              {saveLoading ? "Salvataggio..." : "Salva lead"}
            </button>
          </div>
        </>
      )}
    </div>
  </div>
)}
```

- [ ] **Step 7: Badge "Manuale" in LeadCard**

Nel componente `LeadCard` (o nella funzione che renderizza le card), trova dove vengono mostrati i badge `hotlistBadge` e `nositoBadge`. Aggiungi il badge manuale:

```jsx
const manualBadge = lead.id?.startsWith("manual://")
  ? <span style={{ fontSize: "10px", fontWeight: 600, color: "#64748b", background: "#f1f5f9", padding: "2px 6px", borderRadius: "999px" }}>Manuale</span>
  : null;
```

E includilo nell'output della card accanto agli altri badge.

- [ ] **Step 8: Build e verifica**

```bash
cd /Users/marcobarlera/Documents/02_PROGETTI/Morpheus/frontend
npm run build
```

Avvia Flask e testa manualmente:
1. Apri `http://localhost:5000`
2. Click "+" nel header lista lead → modal appare
3. Incolla `https://www.facebook.com/bar-centrale-varese` → "Analizza URL" → form con nome pre-compilato
4. Compila lat/lon → "Salva lead" → modal chiuso, lead compare in lista con badge "Manuale"
5. Click lead sulla mappa → popup visibile

- [ ] **Step 9: Commit**

```bash
cd /Users/marcobarlera/Documents/02_PROGETTI/Morpheus
git add frontend/src/App.jsx frontend/dist/
git commit -m "feat(frontend): add manual lead modal with URL parsing and Manuale badge"
```

---

## Self-Review checklist

- [x] Dedup: `_norm_dedup` → `import_from_csv` filtro → log skipped ✓
- [x] `create_manual_lead`: haversine, score, INSERT, return row ✓
- [x] `url_parser.py`: Facebook, Google Maps lungo, short URL con redirect ✓
- [x] Flask: `POST /api/leads/parse-url` + `POST /api/leads` ✓
- [x] Frontend: modal 2-step, parse handler, save handler, badge, build ✓
- [x] Nessun placeholder o TBD ✓
- [x] `create_manual_lead` importata in `app.py` ✓
- [x] `handleSaveLead` usa `activeDatasetId` che esiste già in App.jsx ✓
- [x] `setLeads` — verifica che sia il setter corretto per l'array leads in App.jsx ✓ (è `setLeads` da `useState`)
