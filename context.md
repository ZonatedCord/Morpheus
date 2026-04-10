# DataBase B2B — Context Document

> Aggiornato: 2026-04-10 | Da aggiornare a fine di ogni sessione con Claude Code.

---

## Cos'è questo progetto

Strumento di lead generation B2B iperlocale. Raccoglie attività commerciali nella
provincia di Varese (o qualsiasi altra area italiana) da OpenStreetMap, le classifica
per distanza da un punto di riferimento e priorità commerciale, le salva in un
database SQLite e le visualizza su una mappa web interattiva con pannello filtri e
lista scrollabile.

**Caso d'uso principale:** trovare attività locali senza sito web o con presenza
digitale debole, da contattare per proporre servizi web/marketing.

---

## Stack tecnologico

| Strato | Tecnologia |
|---|---|
| Backend API | Python 3.13 + Flask |
| Database | SQLite (file `data/leads.db`) |
| Fonte dati primaria | OpenStreetMap via Overpass API |
| Geocodifica | Nominatim (OSM) |
| Scoring LLM | Ollama locale (modelli: `qwen2.5:3b`, `gemma2:2b`) |
| Frontend | React 18 + Vite + Leaflet |
| CSS | CSS custom (no framework) — Font: Fira Sans / Fira Code |
| Build | `npm run build` → `frontend/dist/` servito da Flask |

---

## Struttura del progetto

```
DataBase B2B/
├── app.py                          # Server Flask + API REST + job asincroni
├── context.md                      # Questo file
├── data/
│   ├── leads.db                    # Database SQLite
│   └── output/
│       ├── osm/runs/               # CSV intermedi per ogni scansione OSM
│       └── research/               # Output pipeline outreach
├── frontend/
│   ├── src/
│   │   ├── App.jsx                 # Componente React principale (tutto in un file)
│   │   ├── styles.css              # CSS design system completo
│   │   └── main.jsx                # Entry point React
│   └── dist/                       # Build produzione servita da Flask
├── scripts/                        # Script CLI standalone
│   ├── importa_db.py               # Importa CSV esistenti nel DB
│   ├── cerca_lead.py               # Query CLI sul DB
│   ├── scorizza_lead.py            # Scoring LLM via Ollama
│   ├── varesotto_osm.py            # Wrapper CLI per VaresottoOSMFinder
│   └── ...                         # Pipeline outreach (LinkedIn, messaggi, research)
└── src/finder_clienti_varesotto/   # Libreria Python core
    ├── varesotto_osm.py            # VaresottoOSMFinder — raccolta dati OSM
    ├── db.py                       # Tutte le operazioni sul DB SQLite
    ├── llm_filter.py               # Scoring lead via Ollama
    ├── paths.py                    # Tutte le path del progetto
    └── ...                         # Moduli outreach/research
```

---

## Come arrivano i dati: pipeline completa

### Step 1 — Raccolta dati (OSM/Overpass)

`VaresottoOSMFinder` in `varesotto_osm.py` esegue la pipeline:

1. **Geocodifica il punto di riferimento** via Nominatim  
   Es. "Vedano Olona, Varese, Lombardia, Italia" → lat/lon
2. **Risolve l'area OSM** della provincia via Nominatim → `area_id` Overpass
3. **Esegue 11 query Overpass** (una per SearchGroup) sull'area:
   - Ristorazione (`amenity`: bar, ristorante, cafe, pub…)
   - Ospitalità (`tourism`: hotel, B&B, chalet…)
   - Beauty & Benessere (`amenity`/`shop`: parrucchiere, estetica…)
   - Fitness & Sport (`leisure`/`shop`: fitness, sports…)
   - Sanità (`amenity`/`shop`: dentista, farmacia, ottico…)
   - Servizi Professionali (`office`: commercialista, avvocato…)
   - Artigiani (`craft`: qualsiasi)
   - Negozi (`shop`: qualsiasi)
4. **Deduplicazione** per chiave `(nome_normalizzato, lat_arrotondato, lon_arrotondato)`
5. **Ordinamento** per distanza crescente, poi "senza sito" prima, poi categoria
6. **Salvataggio CSV** in `data/output/osm/runs/`

Endpoint Overpass usati (con fallback): `lz4.overpass-api.de`, `overpass.kumi.systems`, `overpass-api.de`

### Step 2 — Importazione nel DB

`import_from_csv()` in `db.py`:
- Legge il CSV OSM + eventuale CSV hotlist (dati arricchiti manualmente)
- Merge hotlist: se il nome corrisponde, sovrascrive telefono/email/sito con i dati arricchiti
- Genera `osm_url` come chiave primaria composta: `dataset_id::source_osm_url`
- Preserva `rilevanza_score` esistenti (non sovrascrive scoring LLM)

### Step 3 — Flusso dalla UI (via Flask)

Quando l'utente clicca "Avvia scansione" nella mappa web:
1. `POST /api/datasets` → Flask lancia `_population_worker` in un Thread separato
2. Il worker chiama `create_dataset_from_reference()` → `VaresottoOSMFinder.run()` + `import_from_csv()`
3. Il frontend fa polling su `GET /api/jobs/{job_id}` ogni 1.5s
4. A completamento, ricarica datasets e lead

---

## Logica di classificazione

### Priorità distanza

Calcolata con formula Haversine dal punto di riferimento:

| Distanza | Priorità |
|---|---|
| ≤ 5 km | ALTISSIMA (rosso) |
| ≤ 10 km | ALTA (arancio) |
| ≤ 20 km | MEDIA (verde) |
| ≤ 30 km | BASSA (grigio scuro) |
| > 30 km | MOLTO BASSA (grigio chiaro) |

Questa è l'**unica logica di priorità automatica** — è basata esclusivamente sulla distanza dal punto di riferimento scelto, non sul valore commerciale dell'attività.

### Categorie OSM

Le categorie vengono assegnate leggendo i tag OSM nell'ordine:
`amenity` → `tourism` → `leisure` → `office` → `craft` → `shop`

Le 8 categorie finali sono:
`Ristorazione`, `Ospitalità`, `Beauty & Benessere`, `Fitness & Sport`, `Sanità`, `Servizi Professionali`, `Artigiani`, `Negozi`

### Opportunità web (campo derivato)

| Condizione | Valore |
|---|---|
| Nessun sito web | ALTA |
| Ha sito ma non email | MEDIA |
| Ha sito + email | BASSA |

Questo campo non è ancora esposto nella UI ma è nel DB e nei CSV.

### Scoring LLM (opzionale)

`llm_filter.py` usa Ollama locale per assegnare uno score 0–10 ai lead in hotlist
con priorità ALTISSIMA/ALTA. Il prompt chiede: "quanto è rilevante per vendere
'[servizio]'?". Richiede che Ollama sia attivo su `http://127.0.0.1:11434`.

---

## Schema database SQLite

### Tabella `attivita`

| Campo | Tipo | Note |
|---|---|---|
| `osm_url` | TEXT PK | Chiave: `dataset_id::source_osm_url` |
| `nome` | TEXT | Nome attività |
| `lat`, `lon` | REAL | Coordinate GPS |
| `priorita` | TEXT | ALTISSIMA/ALTA/MEDIA/BASSA/MOLTO BASSA |
| `distanza_km` | REAL | Dal punto di riferimento del dataset |
| `categoria` | TEXT | Una delle 8 macro-categorie |
| `sottocategoria` | TEXT | Valore OSM leggibile (es. "Ristorante") |
| `comune` | TEXT | Città |
| `telefono`, `email`, `sito` | TEXT | Contatti |
| `ha_sito` | TEXT | "SI" o "NO" |
| `stato` | TEXT | Stato outreach (dalla hotlist) |
| `proposta` | TEXT | Proposta commerciale (dalla hotlist) |
| `rating` | TEXT | Valutazione manuale |
| `in_hotlist` | INTEGER | 0/1 |
| `rilevanza_score` | INTEGER | Punteggio LLM 0–10 |
| `dataset_id` | TEXT | FK verso dataset_runs |

### Tabella `dataset_runs`

Ogni dataset corrisponde a una coppia (reference_query, province_query).
Il dataset "attivo" è quello con `updated_at` più recente.

---

## API Flask

| Endpoint | Metodo | Descrizione |
|---|---|---|
| `/api/datasets` | GET | Lista tutti i dataset con conteggi |
| `/api/datasets` | POST | Avvia scansione OSM (background job) |
| `/api/leads` | GET | Lead del dataset, con filtri opzionali |
| `/api/jobs/{job_id}` | GET | Stato del job di popolamento |
| `/` e `/<path>` | GET | Serve il frontend React (dist/) |

Il server Flask usa `threading` nativo (non async). I job di popolamento vengono
tenuti in memoria (`POPULATION_JOBS` dict con Lock) — non persistono al riavvio.

---

## Frontend React

Tutto il frontend è in un singolo file `App.jsx` (~795 righe) con nessun componente
separato oltre a `DatasetPill` e `LeadCard` inline.

**Struttura UI:**
```
[Sidebar: filtri + dataset] | [Mappa Leaflet] | [Lista lead]
```

Tutte e tre le colonne sono collassabili lateralmente.

**Stato gestito con `useState`/`useMemo`/`useDeferredValue`:**
- `datasets` — lista dataset dal DB
- `activeDatasetId` — dataset corrente (persiste in localStorage)
- `leads` — lead del dataset attivo (tutti, non paginati)
- `filteredLeads` — leads filtrati in-memory (deferred per non bloccare UI)
- `selectedLeadId` — lead selezionato (sincronizzato con mappa)
- `populateJobId` — job OSM attivo (persiste in localStorage per sopravvivere al reload)

**Librerie:**
- `leaflet` per la mappa (marker colorati per priorità, stelle per hotlist)
- Nessuna altra dipendenza UI (no React Router, no state manager)

---

## Modifiche fatte in questa sessione

### Restyling completo UI (2026-04-10)

**Motivazione:** il design precedente era troppo decorativo (glassmorphism,
blob radiali, border-radius da 30px, backdrop-filter su tutto) — non adatto
a un tool B2B professionale usato per lavoro.

**Design system applicato:** Data-Dense Dashboard
- Palette: blu professionale `#1E40AF` come accent, sfondi neutri `#F9FAFB`
- Tipografia: Fira Sans (interfaccia) + Fira Code (numeri, percentuali)
- Nessun gradiente decorativo, nessun glassmorphism
- Bordi visibili (`#E5E7EB`) che danno struttura senza rumore visivo
- Shadow leggere solo dove portano informazione (card mappa, shadow-md sui tasti)

**Cambiamenti strutturali a `styles.css`:**
- Riscritto da zero (~930 righe → ~680 righe più efficienti)
- CSS custom properties aggiornate: scala di grigi completa + palette blu/amber
- Layout con `border-right` invece di spaziature con gap
- `.sidebar-scroll` wrapper per scrolling interno della sidebar
- `.list-head-inner` per header unificato del pannello lead
- Sidebar e list panel: quando collassati a 52px, nascondono il titolo e centrano solo il bottone toggle
- Lead card: più compatta, alta densità, indice in `Fira Code`
- Map card overlay: `280px`, sfondo bianco opaco, testo scuro
- Stat row nella mappa: aggiunto contatore "senza sito"

**Cambiamenti strutturali a `App.jsx`:**
- Sidebar: aggiunto wrapper `<div className="sidebar-scroll">` per il contenuto scrollabile
- List panel: rimosso `panel-rail-right` separato, il toggle è ora nel `panel-rail` con `.list-head-inner`
- Map panel head: aggiunto terzo badge "senza sito" nella stat-row
- Toggle buttons: da caratteri ASCII (`←`, `→`) a unicode (`‹`, `›`)

**Bug fix:**
- I bottoni toggle scomparivano quando le colonne erano collassate a 52px perché
  `panel-rail` conteneva testo + bottone (>52px) con `overflow: hidden` sul parent.
  Fix: `.sidebar.collapsed .panel-rail` e `.list-panel.collapsed .panel-rail` con
  `justify-content: center` e titolo nascosto.

---

## Consigli per migliorare il progetto

### 1. Priorità non solo per distanza — il punto debole principale

Attualmente la priorità (ALTISSIMA/ALTA/MEDIA…) è **solo** distanza geografica.
Un ristorante a 4 km con sito web fatto bene ha priorità ALTISSIMA quanto un
artigiano a 4 km senza nessuna presenza online.

**Soluzione suggerita:** priorità composita pesata:

```
score = (distanza_normalizzata × 0.5)
      + (assenza_sito × 0.3)
      + (categoria_target × 0.2)
```

Dove `categoria_target` è configurabile dall'utente (es. "mi interessano Artigiani
e Ristorazione"). Questo consentirebbe di esporre nella UI i lead davvero più
caldi in cima, non solo i più vicini.

### 2. I lead non sono paginati — scalabilità

`GET /api/leads` restituisce **tutti** i lead del dataset senza paginazione.
Con dataset grandi (>2000 lead) il browser riceve un JSON pesante e React
deve renderizzare centinaia di card. La lista è già scrollabile ma non usa
virtualizzazione.

**Soluzione suggerita:**
- Aggiungere `limit` e `offset` all'endpoint `/api/leads`
- Usare `react-window` o `react-virtual` per virtualizzare la lista
- Oppure, più semplice: limitare la lista a 200 risultati con un badge
  "mostra tutti" che li carica in blocchi

### 3. I job di popolamento muoiono al riavvio del server

`POPULATION_JOBS` è un dizionario in memoria Python. Se Flask si riavvia
durante una scansione, il job id rimane in localStorage ma il server non lo
conosce più → il frontend va in loop di polling fallito.

**Soluzione suggerita:** salvare lo stato del job in una tabella SQLite
`jobs` (job_id, status, progress, stage, message, created_at) e fare
cleanup al boot dei job "running" più vecchi di N ore.

### 4. La hotlist è un CSV statico fuori dal DB

Il file `data/output/research/clienti_varesotto_outreach_hotlist.csv` è
il modo attuale per arricchire i lead (stato, proposta, rating, email).
Viene riletto ad ogni `import_from_csv`. Questo significa che le modifiche
manuali alla hotlist richiedono di re-importare il CSV.

**Soluzione suggerita:** esporre endpoint PATCH `/api/leads/{id}` per
aggiornare `stato`, `proposta`, `rating` direttamente dalla UI della mappa,
senza passare per CSV. Aggiungerebbe un enorme valore operativo.

### 5. Nessuna autenticazione

Il server Flask non ha autenticazione. Se esposto in rete locale o con un
tunnel (ngrok, Tailscale), chiunque può leggere e modificare i dati.

**Soluzione minima:** basic auth con una singola password in variabile
d'ambiente, configurabile in `app.py`.

### 6. La mappa non mostra tutti i lead per dataset grandi

Leaflet con migliaia di marker diventa lento. Attualmente i marker vengono
ricreati ogni volta che cambiano `filteredLeads`.

**Soluzione suggerita:** usare `leaflet.markercluster` per raggruppare i
marker vicini. Si integra facilmente con Leaflet e scala bene fino a 10k+
punti.

### 7. Nessun export dalla UI

Non è possibile esportare i lead filtrati dalla mappa come CSV o Excel.
Bisogna usare `cerca_lead.py --output csv` da CLI.

**Soluzione suggerita:** bottone "Esporta CSV" nel pannello filtri che chiama
un nuovo endpoint `GET /api/leads/export?dataset_id=...&[stessi filtri]`
che restituisce un CSV con header `Content-Disposition: attachment`.

### 8. Il campo `opportunita_web` non è visibile nella UI

Il campo è nel DB e nei CSV ma non compare nella lead card né nel popup Leaflet.
È uno dei dati più utili per prioritizzare i contatti.

**Soluzione suggerita:** aggiungere un badge "Opportunità Web: ALTA/MEDIA/BASSA"
nella lead card e nel popup della mappa.
