# Morpheus — Context Document

> Aggiornato: 2026-04-21 (sessione 7) | Da aggiornare a fine di ogni sessione con Claude Code.

---

## Cos'è questo progetto

**Morpheus** — strumento di lead generation B2B iperlocale. Raccoglie attività commerciali
nella provincia di Varese (o qualsiasi altra area italiana) da OpenStreetMap e Foursquare,
le classifica con uno scoring composito (distanza + assenza sito + categoria target),
le salva in un database SQLite e le visualizza su una mappa web interattiva.

**Caso d'uso principale:** trovare attività locali senza sito web o con presenza
digitale debole, da contattare per proporre servizi web/marketing.

---

## Stack tecnologico

| Strato                | Tecnologia                                               |
| --------------------- | -------------------------------------------------------- |
| Backend API           | Python 3.13 + Flask                                      |
| Database              | SQLite (file `data/leads.db`)                            |
| Fonte dati primaria   | OpenStreetMap via Overpass API                           |
| Fonte dati secondaria | Foursquare Places API v3 (richiede `FSQ_API_KEY` in env) |
| Geocodifica           | Nominatim (OSM)                                          |
| Scoring LLM           | Ollama locale (modelli: `qwen2.5:3b`, `gemma2:2b`)       |
| Frontend              | React 18 + Vite + Leaflet                                |
| CSS                   | CSS custom (no framework) — Font: Fira Sans / Fira Code  |
| Build                 | `npm run build` → `frontend/dist/` servito da Flask      |

---

## Struttura del progetto

```
Morpheus/
├── app.py                          # Server Flask + API REST + job asincroni
├── context.md                      # Questo file
├── data/
│   ├── leads.db                    # Database SQLite
│   └── output/
│       ├── osm/runs/               # CSV intermedi per ogni scansione
│       └── research/               # Output pipeline outreach
├── frontend/
│   ├── src/
│   │   ├── App.jsx                 # Componente React principale
│   │   ├── styles.css              # CSS design system completo
│   │   └── main.jsx                # Entry point React
│   └── dist/                       # Build produzione servita da Flask
├── scripts/                        # Script CLI standalone
│   ├── importa_db.py               # Importa CSV esistenti nel DB
│   ├── cerca_lead.py               # Query CLI sul DB
│   ├── scorizza_lead.py            # Scoring LLM via Ollama
│   └── ...                         # Pipeline outreach (LinkedIn, messaggi, research)
└── src/morpheus/                   # Package Python core (era finder_clienti_varesotto)
    ├── varesotto_osm.py            # MorpheusFinder — raccolta dati OSM + Foursquare
    ├── db.py                       # Tutte le operazioni sul DB SQLite
    ├── llm_filter.py               # Scoring lead via Ollama
    ├── paths.py                    # Tutte le path del progetto
    └── ...                         # Moduli outreach/research
```

---

## Come arrivano i dati: pipeline completa

### Step 1 — Raccolta dati (OSM + Foursquare)

`MorpheusFinder` in `varesotto_osm.py` esegue la pipeline in 5 step:

1. **Geocodifica il punto di riferimento** via Nominatim
2. **Risolve l'area OSM** della provincia → `area_id` Overpass
3. **Esegue 12 query Overpass** (una per SearchGroup):
   - Ristorazione (`amenity`: bar, ristorante, cafe, pub…)
   - Ospitalità (`tourism`: hotel, B&B, chalet…)
   - Beauty & Benessere (`amenity`/`shop`: parrucchiere, estetica…)
   - Fitness & Sport (`leisure`/`shop`: fitness, sports, studio danza…)
   - Sanità (`amenity`/`shop`: dentista, farmacia, ottico…)
   - Servizi Professionali (`office`: commercialista, avvocato, IT, notaio, logistica, associazione…)
   - **Intrattenimento** (`amenity`: cinema, teatro, discoteca, spazio eventi) — categoria nuova
   - Artigiani (`craft`: qualsiasi)
   - Negozi (`shop`: qualsiasi)
4. **Foursquare Places API** — query circolare dal punto di riferimento (raggio = max_distance_km,
   cap 100km). Saltata silenziosamente se `FSQ_API_KEY` non è in env.
5. **Deduplicazione** per chiave `(nome_normalizzato, lat_4d, lon_4d)` — cross-source
6. **Ordinamento** per score composito decrescente
7. **Salvataggio CSV** in `data/output/osm/runs/`

### Step 2 — Importazione nel DB

`import_from_csv()` in `db.py`:

- Legge il CSV + eventuale hotlist CSV (dati arricchiti manualmente)
- Merge hotlist: sovrascrive telefono/email/sito con i dati arricchiti
- Chiave primaria: `dataset_id::source_osm_url` (per Foursquare: `foursquare://{fsq_id}`)
- Preserva `rilevanza_score` esistenti (non sovrascrive scoring LLM)

### Step 3 — Flusso dalla UI (via Flask)

1. `POST /api/datasets` → Flask lancia `_population_worker` in Thread separato
2. Il worker chiama `create_dataset_from_reference()` → `MorpheusFinder.run()` + `import_from_csv()`
3. Il frontend fa polling su `GET /api/jobs/{job_id}` ogni 1.5s

---

## Logica di classificazione

### Scoring composito (IMPLEMENTATO in questa sessione)

La priorità non è più basata solo sulla distanza ma su uno **score composito [0, 1]**:

```
score = 0.5 × dist_norm + 0.3 × assenza_sito + 0.2 × cat_target

dist_norm   = max(0, 1 - distanza_km / max_distance_km)
assenza_sito = 1.0 se non ha sito, 0.0 se ce l'ha
cat_target   = 1.0 se categoria in target_categories, 0.0 altrimenti
```

**Fasce:**

| Score  | Priorità    |
| ------ | ----------- |
| ≥ 0.75 | ALTISSIMA   |
| ≥ 0.55 | ALTA        |
| ≥ 0.35 | MEDIA       |
| ≥ 0.20 | BASSA       |
| < 0.20 | MOLTO BASSA |

**Configurazione via env (opzionale):**

- `SCORING_CATEGORIES=Ristorazione,Artigiani` — categorie target (peso 0 se non impostato)
- `SCORING_MAX_DISTANCE_KM=50` — default 50 km

### Categorie

9 macro-categorie: `Ristorazione`, `Ospitalità`, `Beauty & Benessere`, `Fitness & Sport`,
`Sanità`, `Servizi Professionali`, `Artigiani`, `Negozi`, `Intrattenimento`

### Scoring LLM (opzionale, su hotlist)

`llm_filter.py` usa Ollama locale per assegnare uno score 0–10 ai lead in hotlist.
Il prompt chiede: "quanto è rilevante per vendere '[servizio]'?".
Richiede Ollama attivo su `http://127.0.0.1:11434`.

### Proposta commerciale

Attualmente la colonna `proposta` viene popolata **solo dalla hotlist CSV** (campo
`"Proposta Mirata Base"`, scritto a mano). Per i lead non in hotlist è vuota.

**TODO prossima sessione:** generare la proposta via Ollama (Opzione B) — estendere
`score_batch()` in `llm_filter.py` per chiedere al modello una proposta commerciale
breve oltre allo score, e salvarla in `proposta` (o un campo dedicato `proposta_llm`).

### Performance frontend (marker Leaflet)

Il frontend usa un sistema a due livelli per gestire dataset grandi (>1000 punti):

- **Cluster mode (zoom < 11):** i marker individuali vengono sostituiti da bolle per città
  (`makeCityIcon(count)`), raggruppate per `comune` con centroide calcolato come media lat/lon.
  Click su bolla → zoom a livello 12 sulla città.
- **Viewport culling (zoom ≥ 11):** vengono creati marker Leaflet solo per i lead visibili
  nel bounding box corrente della mappa (+ 25% padding). Aggiornato su `moveend`/`zoomend`.
- **Aggiornamento incrementale:** invece di `clearLayers()` + rebuild completo a ogni cambio
  filtro, si calcolano i delta (aggiunti/rimossi) tra `prevFilteredIdsRef` e `visibleLeads`.
- **Selezione O(1):** `prevSelectedIdRef` traccia il marker precedente; solo 2 marker vengono
  aggiornati per click invece di tutti.
- **Popup pending:** se `focusLead` porta a un lead fuori viewport, il popup viene aperto
  non appena il marker viene creato dopo il `flyTo` (via `pendingPopupRef`).
- **Lista lead:** capped a 300 elementi renderizzati con `LeadCard` wrappata in `React.memo`.

---

## Schema database SQLite

### Tabella `attivita`

| Campo                       | Tipo    | Note                                                           |
| --------------------------- | ------- | -------------------------------------------------------------- |
| `osm_url`                   | TEXT PK | Chiave: `dataset_id::source_osm_url` (o `foursquare://fsq_id`) |
| `nome`                      | TEXT    | Nome attività                                                  |
| `lat`, `lon`                | REAL    | Coordinate GPS                                                 |
| `priorita`                  | TEXT    | ALTISSIMA/ALTA/MEDIA/BASSA/MOLTO BASSA (da score composito)    |
| `distanza_km`               | REAL    | Dal punto di riferimento del dataset                           |
| `categoria`                 | TEXT    | Una delle 9 macro-categorie                                    |
| `sottocategoria`            | TEXT    | Valore OSM/Foursquare leggibile                                |
| `comune`                    | TEXT    | Città                                                          |
| `telefono`, `email`, `sito` | TEXT    | Contatti                                                       |
| `ha_sito`                   | TEXT    | "SI" o "NO"                                                    |
| `stato`                     | TEXT    | Stato outreach (dalla hotlist)                                 |
| `proposta`                  | TEXT    | Proposta commerciale (dalla hotlist — LLM in futuro)           |
| `rating`                    | TEXT    | Valutazione manuale                                            |
| `in_hotlist`                | INTEGER | 0/1                                                            |
| `rilevanza_score`           | INTEGER | Punteggio LLM 0–10                                             |
| `dataset_id`                | TEXT    | FK verso dataset_runs                                          |

### Tabella `dataset_runs`

Ogni dataset corrisponde a una coppia (reference_query, province_query).
Il dataset "attivo" è quello con `updated_at` più recente.

---

## API Flask

| Endpoint             | Metodo | Descrizione                                     |
| -------------------- | ------ | ----------------------------------------------- |
| `/api/datasets`      | GET    | Lista tutti i dataset con conteggi              |
| `/api/datasets`      | POST   | Avvia scansione OSM+Foursquare (background job) |
| `/api/leads`         | GET    | Lead del dataset, con filtri opzionali          |
| `/api/jobs/{job_id}` | GET    | Stato del job di popolamento                    |
| `/` e `/<path>`      | GET    | Serve il frontend React (dist/)                 |

---

## Frontend React

Tutto il frontend è in `App.jsx` con componenti `DatasetPill` e `LeadCard`.

**Struttura UI:**

```
[Sidebar: filtri + dataset] | [Mappa Leaflet] | [Lista lead]
```

**Stato gestito con `useState`/`useMemo`/`useDeferredValue`:**

- `datasets` / `activeDatasetId` / `leads` / `filteredLeads`
- `selectedLeadId` — sincronizzato con mappa
- `populateJobId` — persiste in localStorage

---

## Sessioni con Claude Code

### Sessione 2026-04-20 (sessione 6)

**Problemi affrontati e risolti:**

1. **Export CSV dalla UI** — bottone "↓ CSV" nel header del pannello lista lead.
   `buildExportUrl()` costruisce l'URL con i filtri correnti. Usa `/api/leads/export`.

2. **Autocomplete comune** — `<datalist id="comuni-datalist">` collegato al campo di ricerca.
   Popolato da `GET /api/comuni?dataset_id=...` al cambio dataset.

3. **Filtro Facebook** — toggle "Solo con Facebook" nella sidebar.

4. **KPI contattati** — `X contattati` nella stat-row mappa.

5. **Bulk actions** — selezione multipla lead nella lista:
   - `lead-card-outer` wrapper con checkbox (visibile su hover o quando selezionato)
   - Bulk action bar blu in cima alla lista (appare quando ≥1 selezionato)
   - Azioni: Contattata · Rifiutata · Rimuovi stato · +Hotlist · Deseleziona
   - Backend: `update_leads_bulk()` in `db.py`, endpoint `PATCH /api/leads` (senza ID)
   - Pulsante "Seleziona tutti" sopra la lista

6. **Verifica siti morti** — `src/morpheus/site_checker.py`:
   - `_check_url()`: HEAD → GET fallback, timeout 6s, 12 workers paralleli
   - `check_sites_batch()`: aggiorna `ha_sito = "MORTO"` per siti non raggiungibili
   - Endpoint `POST /api/datasets/<id>/check-sites` + worker asincrono
   - Frontend: sezione "Verifica siti web" in sidebar (pattern identico a Facebook)
   - Stat-row: badge rosso "X siti morti" quando presenti
   - `onlyWithoutSite` ora include ha_sito = "MORTO"
   - LeadCard: label "Sito morto" in rosso al posto di "Con sito"

7. **Score personalizzato** — pannello in sidebar con 3 slider (dist/sito/cat, range 0-10)
   e multiselect categorie target. Ricalcola `_localScore` + `_localPriority` lato client,
   riordina la lista senza toccare il DB. Badge verde "Score personalizzato attivo" quando attivo.
   `computeLocalScore()` + `scoreToPriority()` in `App.jsx`.

8. **Notifiche desktop** — `Notification.requestPermission()` al mount. `sendNotification()`
   chiamata al completamento di scansione OSM, Facebook enrichment e verifica siti.

9. **Scarta lead** — nuovo valore `stato="Scartata"` per McDonald's / lead irrilevanti.
   Card con opacity 0.45 + nome barrato. Nascosti per default (`hideScartati=true`).
   Toggle "Mostra lead scartati" nella sidebar filtri.

10. **Brainstorming miglioramenti** — identificate priorità future (vedi TODO).

### Sessione 2026-04-16 (quinta parte)

**Problemi affrontati e risolti:**

1. **Bug concorrenza + ottimizzazioni velocità Facebook** — riscritta `facebook_enrichment.py`:
   - `_throttled_get`: lock tenuto SOLO per prenotare lo slot temporale, rilasciato prima
     del sleep e prima dell'HTTP. Ogni thread prenota `fire_at = max(now, _last+INTERVAL)`,
     poi dorme fuori dal lock. Thread paralleli, non serializzati.
   - `REQUEST_INTERVAL`: 0.8s → 0.5s (+60% throughput)
   - `timeout`: 20s → 8s (risparmio su richieste lente)
   - `_apply_rate_penalty()`: su 429 sposta `_last_request_time` avanti di 10s per TUTTI
     i thread, non solo quello che ha ricevuto l'errore
   - `max_retries`: 3 → 2; sleep su errori: 2s → 1.5s
   - Seconda query saltata se `best_score > 0` (era `>= 4`) → dimezza richieste per la
     maggior parte dei lead
   - Skip immediato (N/F) per lead con nomi composti solo da stopwords
   - Batching esterno rimosso: fetch unico di tutti i candidati + submit tutti al pool
     in un colpo (no pause tra batch)
   - Throughput: da ~0.8 req/s (serializzato) a ~2 req/s effettivi

2. **Doppio motore di ricerca (Brave + DuckDuckGo)** — rate limiter separati per motore.
   I thread prenotano slot su Brave O su DDG in round-robin, senza bloccarsi a vicenda.
   Strategia per lead:
   1. query con virgolette su motore primario (round-robin)
   2. se 0 risultati → stessa query su motore secondario (fallback)
   3. se ancora 0 → query senza virgolette su primario
      `_extract_fb_urls_ddg()` gestisce il redirect DDG (`//duckduckgo.com/l/?uddg=...`).
      Throughput effettivo: ~4 req/s (2 canali × 0.5–0.6s per slot)

3. **Indirizzo nella UI** — il campo `indirizzo` (via + numero civico, da `addr:street` +
   `addr:housenumber` OSM) era già nel DB ma non mostrato. Aggiunto:
   - `normalizeLeads`: `indirizzo: lead.indirizzo ?? ""`
   - `LeadCard`: riga `.lead-card-address` con indirizzo (se presente e non "N/D")
   - `buildPopupHtml`: riga indirizzo prima del telefono
   - `styles.css`: stile `.lead-card-address` (font 10px, grigio, overflow ellipsis)

---

### Sessione 2026-04-15 (terza parte)

**Problemi affrontati e risolti:**

1. **Facebook enrichment con BeautifulSoup** — la versione precedente usava regex grezzo
   sull'HTML e trovava pochi risultati. Riscritto `search_facebook_page()` usando `BeautifulSoup`
   con 4 selettori CSS multipli per coprire le diverse strutture HTML di Brave Search.
   Ora il matching non richiede più che il nome sia nello slug dell'URL Facebook: score 1 = pagina
   valida (sufficiente), bonus +3 per token del nome nello slug, +2 per comune nello slug.

2. **Thread dinamici per Facebook** — aggiunto `_optimal_workers(total)`: 1/2/3/4/5 thread
   in base al totale lead (≤20/≤80/≤250/≤600/>600). Il semaforo `_RATE_SEM` è condiviso tra
   tutti i thread per rispettare `REQUEST_INTERVAL = 0.8s` e non essere bannati da Brave.

3. **Filtro attività chiuse corretto** — il filtro `any(k.startswith("disused:") for k in tags)`
   era troppo aggressivo: escludeva attività attive che avevano tag come `disused:old_name`.
   Corretto: controllo solo su chiavi primarie specifiche (`disused:amenity`, `disused:shop`,
   `disused:office`, `disused:tourism`, `disused:leisure`) + tag di stato top-level
   (`disused=yes`, `closed=yes`, `shop=vacant`, `amenity=vacant`, `opening_hours=off`).

4. **Satellite toggle** — spostato dalla barra sopra la mappa all'angolo in basso a destra
   della mappa (come Google Maps), tramite `.map-layer-toggle` assoluto con `z-index: 800`.
   CSS: `.layer-btn` con sfondo bianco; btn attivo ha colore brand, nessun bordo tra i due
   pulsanti (aspetto unificato). Stili `.map-tile-switch` / `.tile-btn` rimossi.

5. **Caricamento intero archivio** — `PAGE_SIZE` portato da 500 → 50000. Il server non limita
   più i risultati: `query_leads()` restituisce tutti i lead con coordinate in una sola richiesta.
   La performance della mappa è garantita dal **viewport culling** già implementato (solo i
   marker nel bounding box visibile + 25% padding vengono creati come oggetti Leaflet).
   Rimosso il pulsante "Carica altri" perché non più necessario.

6. **Bug `_get_job` — dati dataset scomparsi** — `result.update(extra)` distribuiva i campi
   del dataset al livello top di `result`, ma il frontend cercava `payload.dataset?.dataset_id`.
   Corretto: `result["dataset"] = extra` per i job di tipo `populate`.

7. **Cache Vite** — dopo modifiche ai bundle occorre eseguire
   `rm -rf node_modules/.vite dist && npm run build` per forzare una build pulita.
   Il nome-mangling di Vite rende inutile `grep "variableName" bundle.js` per debug.

**Dati persi (non recuperabili da questa sessione):**

- I dataset Como e Milano sono stati sovrascritti in una scansione precedente fatta senza
  "Unisci all'archivio attivo". L'utente dovrà ri-scansionare quelle aree con l'opzione
  di append abilitata.

---

### Sessione 2026-04-15 (seconda parte)

**Problemi affrontati e risolti:**

1. **Job persistenti** — rimosso `POPULATION_JOBS` dict in memoria; aggiunta tabella SQLite `jobs`
   con `save_job()`, `get_job()`, `mark_stale_jobs()` in `db.py`. Al riavvio Flask i job
   `running`/`queued` vengono marcati `interrupted`. Il `result_json` è serializzato come JSON TEXT.

2. **Paginazione lead** — `/api/leads` ora restituisce `{leads, total, page, page_size, has_more}`.
   Default `page_size=500`, max 2000. `query_leads()` accetta `offset`. Frontend carica prima
   pagina e mostra pulsante "Carica altri N rimanenti" se `has_more=true`.
   I lead usano `lead.id = osm_url` (stabile) invece di `${dataset_id}-${index}`.

3. **Facebook enrichment** — nuovo modulo `src/morpheus/facebook_enrichment.py`:
   - `search_facebook_page(session, nome, comune, categoria)` usa Brave Search con
     `site:facebook.com "nome" comune`, valida lo slug, restituisce URL o `""`.
   - `enrich_leads_facebook(dataset_id, db_path, progress_callback)` itera lead senza
     `facebook_url`, segna quelli non trovati come `N/F` (not found) per evitare ri-cerca.
   - Nuovo endpoint `POST /api/datasets/<dataset_id>/enrich/facebook` → job asincrono.
   - UI: sezione "Arricchimento Facebook" in sidebar, polling ogni 2s, link Facebook
     visibile nel popup Leaflet e nel `LeadCard`.

4. **Attività chiuse filtrate** — `_element_to_record()` in `varesotto_osm.py` ora salta elementi
   con tag `disused=yes`, `closed=yes`, `shop=vacant`, `amenity=vacant`, `opening_hours=off`,
   o qualsiasi key che inizia con `disused:` / `abandoned:`.

5. **Satellite** — tile layer switch (Mappa / Satellite) nella barra sopra la mappa.
   Usa ArcGIS World Imagery di Esri (no API key). CSS in `styles.css`.

### Sessione 2026-04-15 (prima parte)

**Problemi affrontati e risolti:**

1. **Bug cluster mappa** — il pallino verde del cluster restava visibile dopo il ritorno a zoom normale
   - In `frontend/src/App.jsx` cluster e marker individuali condividono `markersLayerRef`
   - Aggiunto reset esplicito del layer solo quando cambia modalità (`cluster` ↔ `individuale`)
   - Preservato l'aggiornamento incrementale dei marker durante pan/filtro normali

2. **Verifica frontend**
   - Build locale eseguita con `npm run build` in `frontend/`
   - Bundle generato correttamente in `frontend/dist/`

3. **Direzione ricerca Facebook / pipeline parallela**
   - Verificato che `src/morpheus/online_research.py` già estrae `Facebook URL` dai risultati pubblici di ricerca
   - Punto di integrazione consigliato: estendere `research_company()` con una sorgente separata per query Facebook pubbliche, non dentro `create_dataset_from_reference()`
   - Obiettivo: trattare Facebook come enrichment parallelo dei lead gia' raccolti, non come sorgente primaria del dataset geografico

### Sessione 2026-04-13

**Problemi affrontati e risolti:**

1. **Performance generale** — lag su slider filtri, click lead, caricamento iniziale
   - `LeadCard` wrappata in `React.memo`; `focusLead` in `useCallback`
   - Aggiornamento marker incrementale (delta add/remove invece di `clearLayers` + rebuild)
   - Lista lead capped a 300 elementi

2. **Selezione lead O(1)** — il click su un lead aggiornava tutti i marker (O(n))
   - Introdotto `prevSelectedIdRef` per tracciare solo il marker precedente
   - `applyMarkerSelection` chiamato su massimo 2 marker per evento click

3. **Lag a zoom basso** — tutti i 2000+ marker renderizzati simultaneamente
   - **Viewport culling:** solo marker nel bounding box corrente + 25% padding (zoom ≥ 11)
   - **Cluster mode:** bolle per città con conteggio (zoom < 11), senza `leaflet.markercluster`
   - `mapBounds` state `{ n, s, e, w, zoom }` aggiornato su `moveend`/`zoomend`

---

### Sessione 2026-04-10

**Problemi affrontati e risolti:**

1. **Rinomina progetto → Morpheus**
   - Package `src/finder_clienti_varesotto/` → `src/morpheus/`
   - Classe `VaresottoOSMFinder` → `MorpheusFinder`
   - Aggiornati tutti i riferimenti: `app.py`, tutti gli `scripts/`, HTML, React, `index.html`

2. **Scoring composito** (era solo distanza)
   - Implementato `_composite_score()` + `_composite_priority()` in `varesotto_osm.py`
   - Configurabile via env: `SCORING_CATEGORIES`, `SCORING_MAX_DISTANCE_KM`
   - `sort_results()` ora ordina per score desc, non per distanza

3. **Espansione tag Overpass**
   - `OFFICE_VALUES` + `association`, `it`, `logistics`, `notary`
   - `FITNESS_VALUES` + `dance` (leisure)
   - Nuova categoria Intrattenimento: `cinema`, `events_venue`, `nightclub`, `theatre`
   - Totale SearchGroups: 11 → 12

4. **Integrazione Foursquare Places API**
   - `_fetch_foursquare()` + `_foursquare_to_record()` + `_classify_foursquare()` in `MorpheusFinder`
   - Attivato se `FSQ_API_KEY` in env, skip silenzioso altrimenti
   - Dedup cross-source con chiave `(nome_norm, lat_4d, lon_4d)`
   - PK nel DB: `foursquare://{fsq_id}`

---

## TODO / Prossime sessioni

### Da sistemare — CRITICO (sessione 7)

1. **Salvataggio lead manuale non funziona correttamente** — il lead viene salvato nel DB ma
   non appare sempre visibile nella lista dopo il salvataggio. Il `scrollIntoView` + `setSelectedLeadId`
   potrebbe non funzionare se il lead ha `lat/lon = null` (escluso dal rendering marker mappa) o
   se i filtri attivi lo nascondono. Verificare: (a) il lead compare nella lista raw prima dei filtri?
   (b) il `data-lead-id` è presente sulla card? (c) i filtri di priorità lo nascondono?

2. **URL parsing — estrazione dati da Facebook/Google Maps** — Facebook blocca con 400 qualsiasi
   request non autenticata (login wall). Attualmente si estrae solo il nome dallo slug URL.
   Soluzioni da valutare:
   - **Google Places API** (`maps.googleapis.com/maps/api/place/findplacefromtext` + `details`) —
     dato nome + comune → restituisce indirizzo, telefono, coordinate, sito, orari. Richiede
     `GOOGLE_PLACES_API_KEY` in `.env`. ~$0.017 per richiesta details.
   - **Facebook Graph API** (`graph.facebook.com/{page-id}?fields=name,location,phone,website`) —
     richiede `FB_ACCESS_TOKEN` in `.env` (token utente con permesso `pages_read_engagement`).
   - **Fallback senza API**: per Google Maps URL lungo già si estraggono nome + coordinate dalla URL.
     Per Facebook: cercare la pagina su Google Search HTML e parsare snippet (nome, indirizzo, telefono).
   
   **Approccio consigliato prossima sessione:** aggiungere `GOOGLE_PLACES_API_KEY` opzionale.
   Se presente, il flow modal fa: URL Facebook/GMaps slug → cerca su Places API → pre-compila
   tutto il form (nome, indirizzo, comune, lat, lon, telefono, sito web). Se assente, fallback
   al parsing URL attuale + geocodifica manuale.

### Priorità alta

1. **Pubblicazione su GitHub** — rendere il repo pubblico. Checklist:
   - `data/leads.db` → nel `.gitignore` (dati personali/aziendali reali)
   - `data/output/osm/runs/*.csv` → nel `.gitignore` (dati reali aziende)
   - `context.md` → valutare se escludere (contiene email outreach personali) oppure rimuovere la sezione "Outreach — Contatti gestiti"
   - `.env` → già da escludere; aggiungere `.env.example` con chiavi vuote (`FSQ_API_KEY=`, `SCORING_CATEGORIES=`, `SCORING_MAX_DISTANCE_KM=`)
   - Verificare che `app.py` non abbia dati hardcoded (email, numeri, chiavi API)
   - `README.md` — setup guide: requisiti Python, `pip install`, `npm install`, avvio Flask
   - `.venv/`, `__pycache__/`, `frontend/node_modules/`, `frontend/dist/` → nel `.gitignore`

2. **Re-scan Como e Milano** — azione manuale: nuova scansione con `Unisci all'archivio attivo`.

3. **Email outreach semi-automatica** — template engine + invio via SMTP o Gmail API.
   Seleziona lead (già implementato bulk) → scegli template → invia → `stato="Inviata"`.

### Priorità media

4. ~~**Deduplicazione cross-dataset**~~ — implementato in sessione 7. Chiave `(nome_slug, lat_3d, lon_3d)` su append import.

5. **Proposta commerciale via Ollama** — estendere `score_batch()` in `llm_filter.py`
   per generare proposta breve. Campo separato `proposta_llm`.

6. **Mobile responsiveness** — layout non funziona su telefono.
   Breakpoint ≤768px: mappa full-screen + overlay schede.

### Sessione 2026-04-21 (sessione 7)

**Problemi affrontati e risolti:**

1. **Aggiunta lead manuale** — modal 2-step in `App.jsx`:
   - Step 1: incolla URL Facebook o Google Maps → `POST /api/leads/parse-url` → form pre-compilato
   - Step 2: form con tutti i campi + bottone `📍 Geocodifica` (chiama `GET /api/geocode?q=<indirizzo+comune>` via Nominatim) → riempie lat/lon automaticamente
   - `POST /api/leads` → `create_manual_lead()` in `db.py` con haversine + scoring inline
   - PK lead manuali: `manual://{uuid}`, badge "Manuale" nella LeadCard
   - Bottone `+` accanto a `↓ CSV` nel header lista lead
   - Facebook scraping: impossibile (400 login wall), estrae solo nome dallo slug URL
   - Google Maps URL lungo: estrae nome + coordinate dall'URL direttamente
   - Google Maps URL corto (`maps.app.goo.gl`): segue redirect, poi parsing

2. **Deduplicazione cross-dataset** — `import_from_csv()` con `replace_dataset=False`:
   - Carica fingerprint `(nome_slug, round(lat,3), round(lon,3))` esistenti nel dataset
   - Salta righe duplicate durante append. Log: "N duplicati saltati"
   - Nuovo modulo: `src/morpheus/url_parser.py`
   - Nuove funzioni in `db.py`: `create_manual_lead()`, `_haversine_km()`, `_score_to_priority()`, `_norm_dedup()`
   - Nuovi endpoint Flask: `POST /api/leads/parse-url`, `POST /api/leads`, `GET /api/geocode`

**Problemi rimasti aperti (vedi sezione "Da sistemare — CRITICO"):**
- Salvataggio lead manuale: scroll/selezione post-save non sempre funziona
- URL parsing Facebook: solo nome da slug, nessun dato strutturato (blocked)

---

### Già implementato

- ~~**PATCH /api/leads/{id}**~~ — `update_lead_fields()` in `db.py`, endpoint in `app.py`.
  `handleUpdateStato` nel frontend chiama PATCH per aggiornare `stato` (Contattata/Rifiutata).
- ~~**Export CSV dalla UI**~~ — bottone "↓ CSV" nel header lista lead.
- ~~**Filtro Facebook nella UI**~~ — toggle "Solo con Facebook" nella sidebar.
- ~~**Autocomplete comune**~~ — `<datalist>` nel campo ricerca, da `/api/comuni`.
- ~~**KPI contattati**~~ — stat-row mostra conteggio `stato=Contattata`.
- ~~**Bulk actions**~~ — checkbox + bulk bar + `PATCH /api/leads` bulk endpoint.
- ~~**Verifica siti morti**~~ — `site_checker.py`, `POST /api/datasets/<id>/check-sites`,
  `ha_sito="MORTO"`, badge rosso in LeadCard e stat-row.
- ~~**Score personalizzato**~~ — slider sidebar, ricalcolo client-side, riordino lista.
- ~~**Notifiche desktop**~~ — `Notification` API su completamento job.
- ~~**Scarta lead**~~ — `stato="Scartata"`, card barrata, nascosta per default.
- ~~**Paginazione lead**~~ — carica tutti i lead in una sola richiesta (PAGE_SIZE=50000),
  viewport culling gestisce la performance della mappa. Rimosso pulsante "Carica altri".
- ~~**Job persistenti**~~ — tabella SQLite `jobs`, `mark_stale_jobs()` all'avvio Flask.
- ~~**Marker clustering**~~ — cluster mode (zoom < 11) + viewport culling (zoom ≥ 11).
- ~~**Ricerca Facebook parallela**~~ — `facebook_enrichment.py`, thread dinamici basati sul
  totale lead, endpoint `POST /api/datasets/<id>/enrich/facebook`, link in mappa e lista.
- ~~**Satellite toggle**~~ — tasto nell'angolo basso-destra della mappa come Google Maps.
- ~~**Filtro attività chiuse**~~ — `_element_to_record()` salta elementi con tag disused/closed.

### Da sistemare — RISOLTO in sessione 5

- ~~**Facebook lentissimo**~~ — bug architetturale in `_throttled_get`: il lock veniva tenuto
  durante `time.sleep(wait)`, causando la serializzazione di tutti i thread. Fix: ogni thread
  prenota il proprio slot temporale (aggiorna `_last_request_time`) e rilascia il lock
  immediatamente, poi dorme fuori dal lock. Così più thread prenotano slot in parallelo.
  Anche rimosso il `_RATE_SEM` (superfluo con il nuovo design). Threshold seconda query
  abbassato da `best_score >= 4` a `best_score > 0` → dimezza le richieste per lead con
  un risultato immediato. `max_retries` ridotto da 3 a 2. Workers minimi alzati a 2/3/5.

- ~~**Indirizzo mancante**~~ — `indirizzo` era già nel DB ma non mostrato. Ora appare:
  come riga dedicata nella LeadCard (`.lead-card-address`, font 10px grigio) e nel popup
  Leaflet. `normalizeLeads` aggiunto `indirizzo: lead.indirizzo ?? ""`.

---

## Outreach — Contatti gestiti (sessione 2026-04-16)

| Nome                              | Canale   | Indirizzo                        | Stato    | Note                                                                            |
| --------------------------------- | -------- | -------------------------------- | -------- | ------------------------------------------------------------------------------- |
| Kiri Japanese Restaurant          | Email    | kirijapaneserestaurant@gmail.com | Inviata  | Proposta: sito vetrina + Google. Hanno già delivery, solo social.               |
| Azienda Agricola La Prateria      | Email    | info@laprateriamalnate.it        | Inviata  | Proposta: rinnovo sito datato + SEO locale. Allevamento estensivo, spaccio.     |
| Casa del Mobile Malnate           | Email    | casa_del_mobile@hotmail.it       | Inviata  | Solo Facebook, attività incerta (ultima attività 2022, ultima recensione 2024). |
| Black Star Tattoo                 | WhatsApp | (da Facebook)                    | Inviata  | Solo Facebook, nessun sito, nessuna visibilità Google.                          |
| Lombarda Serramenti (arredamenti) | Email    | info@lombardaserramenti.net      | Inviata  | Sito "in fase di rinnovamento". Proposta: completare il rinnovo.                |
| Visiva (grafica/stampa)           | —        | —                                | Scartato | Fa grafica/stampa, troppo vicino al nostro settore.                             |

Magari fare che posso inserire io le attività che vedo io o di persona o tipo se ti dò il link di facebook o google, anche modificare quelle esistenti? Perchè essendo che i dati non li prende da google magari alcuni sono sbagliati

Scritto a Cartoleria Marina Vedano Olona, Kiri su whatsapp,L' Arlecchino Show Bar su facebook, Le fontanelle su IG, Albergo Ristorante Marone facebook
