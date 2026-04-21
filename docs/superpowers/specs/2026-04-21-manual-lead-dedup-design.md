# Design: Aggiunta lead manuale + Deduplicazione cross-dataset

**Data:** 2026-04-21
**Sessione:** 7

---

## Scope

Due feature indipendenti:

1. **Aggiunta lead manuale** — inserire attività non presenti in OSM/Foursquare, con parsing automatico da URL Facebook o Google Maps.
2. **Deduplicazione a import-time** — evitare duplicati quando si fa append di più scansioni nello stesso dataset.

---

## Feature 1 — Aggiunta lead manuale

### Obiettivo

L'utente vuole inserire attività viste di persona o trovate su Facebook/Google Maps, anche se i dati OSM sono sbagliati o mancanti. Deve poter incollare un URL, ricevere un form pre-compilato, correggere e salvare.

### Backend

#### Nuovo modulo: `src/morpheus/url_parser.py`

Funzione pubblica: `parse_lead_url(url: str) -> dict`

Logica per tipo URL:

- **Facebook** (`facebook.com/<slug>`):
  - Estrae slug dal path
  - Converte in nome leggibile: `-`/`_` → spazio, title case
  - Ritorna `{ nome, facebook_url }` — nessuna coordinata

- **Google Maps URL lungo** (`google.com/maps/place/<Nome>/@lat,lon,...`):
  - Regex sul path: estrae nome (URL-decoded) e coordinate da `@lat,lon`
  - Ritorna `{ nome, lat, lon }`

- **Google Maps URL corto** (`maps.app.goo.gl/<hash>`):
  - `requests.get(url, allow_redirects=True, timeout=6)` → URL finale
  - Poi stesso parsing URL lungo
  - Ritorna `{ nome, lat, lon }`

Campi sempre presenti in output (stringa vuota se non estratti):
`nome, lat, lon, facebook_url, sito, comune, categoria, indirizzo, telefono, email`

#### Nuovo endpoint: `POST /api/leads/parse-url`

```
Input:  { "url": "https://..." }
Output: { "nome": "...", "lat": 45.12, "lon": 8.45, "facebook_url": "...", ... }
Errori: 400 se URL non riconosciuto, 422 se parsing fallisce
```

#### Nuova funzione in `db.py`: `create_manual_lead(dataset_id, fields, db_path)`

- PK: `manual://{uuid4().hex}`
- `source_osm_url`: `"manual"`
- `dataset_id`: passato dal frontend (dataset attivo)
- Campi accettati: `nome, lat, lon, categoria, comune, indirizzo, telefono, email, sito, facebook_url`
- `ha_sito`: calcolato da `sito` (SI/NO)
- `priorita`: calcolata inline in `create_manual_lead` con la formula composita (distanza + assenza sito) se lat/lon presenti e dataset ha coordinate di riferimento; altrimenti `"BASSA"`. Nessun import da `varesotto_osm.py` (evita dipendenza circolare).
- `distanza_km`: calcolata da `reference_lat/lon` del dataset (query su `dataset_runs`) se coordinate presenti, altrimenti `0.0`

#### Nuovo endpoint: `POST /api/leads`

```
Input:  { "dataset_id": "...", "nome": "...", "lat": ..., ... }
Output: lead creato (stesso formato di GET /api/leads)
Errori: 400 se nome mancante, 404 se dataset non trovato
```

### Frontend (`App.jsx`)

#### Punto di ingresso

Bottone `+` nel header del pannello lista lead, accanto al bottone `↓ CSV`.

#### Modal — Step 1 (URL input)

- Campo testo per URL Facebook o Google Maps
- Bottone "Analizza" → `POST /api/leads/parse-url`
- Spinner durante il parsing
- Se parsing fallisce: toast errore, si procede comunque al form vuoto
- Link "Compila manualmente" per saltare il parsing

#### Modal — Step 2 (form)

Campi:
| Campo | Tipo | Obbligatorio |
|-------|------|--------------|
| Nome | text | Sì |
| Categoria | select (9 opzioni) | No |
| Comune | text | No |
| Indirizzo | text | No |
| Lat / Lon | number (2 campi) | No |
| Telefono | text | No |
| Email | text | No |
| Sito web | text | No |
| Facebook | text | No |

- "Salva lead" disabilitato se nome vuoto
- Dopo salvataggio: modal chiuso, lista lead ricaricata, nuovo lead in cima
- Lead manuale: badge grigio `Manuale` nella LeadCard (rilevato da `id.startsWith("manual://")`)

---

## Feature 2 — Deduplicazione a import-time

### Obiettivo

Quando si fa append di più scansioni aree diverse nello stesso dataset, lo stesso bar di confine non deve comparire due volte.

### Logica

#### Nuova funzione in `db.py`: `_norm_dedup(nome, lat, lon) -> tuple`

```python
def _norm_dedup(nome: str, lat: float | None, lon: float | None) -> tuple:
    slug = _slugify(nome)  # già presente in db.py
    return (slug, round(lat, 3) if lat else None, round(lon, 3) if lon else None)
```

Precisione 3 decimali ≈ 111m — sufficiente per identificare la stessa attività fisica.

#### Modifica a `import_from_csv()` (solo quando `replace_dataset=False`)

Dopo aver letto i dati esistenti (`existing_scores`), carica anche le fingerprint:

```python
existing_fingerprints = {
    _norm_dedup(r["nome"], r["lat"], r["lon"])
    for r in conn.execute(
        "SELECT nome, lat, lon FROM attivita WHERE dataset_id = ?",
        (resolved_dataset_id,)
    ).fetchall()
    if r["lat"] and r["lon"]
}
```

Durante la costruzione di `rows`, salta le righe duplicate:

```python
seen_in_batch = set()
skipped = 0
for row in csv_rows:
    fp = _norm_dedup(nome, lat, lon)
    if fp in existing_fingerprints or fp in seen_in_batch:
        skipped += 1
        continue
    seen_in_batch.add(fp)
    rows.append(...)
```

Log finale: `"Saltati N duplicati (stesso nome + coordinate)"`

### Vincoli

- Nessuna modifica allo schema DB
- Nessun comportamento cambiato per `replace_dataset=True`
- Lead manuali (`lat/lon` assenti) non vengono deduplicati per coordinate — solo per nome esatto

---

## File toccati

| File | Modifica |
|------|----------|
| `src/morpheus/url_parser.py` | Nuovo modulo |
| `src/morpheus/db.py` | `create_manual_lead()`, `_norm_dedup()`, modifica `import_from_csv()` |
| `app.py` | `POST /api/leads/parse-url`, `POST /api/leads` |
| `frontend/src/App.jsx` | Modal aggiunta lead, badge "Manuale", bottone "+" |

---

## Non in scope

- Parsing da URL Instagram, TripAdvisor, o altri sorgenti
- Editing coordinate su mappa (drag marker)
- Deduplicazione cross-dataset a query-time (query SQL)
- Merge automatico di dati tra lead duplicati (es. unire telefono da uno e coordinate dall'altro)
