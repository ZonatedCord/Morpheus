# Morpheus

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.x-lightgrey.svg)](https://flask.palletsprojects.com/)

> *"Morpheus ti mostra la verità."*

![Morpheus — mappa lead locali](assets/screenshot.png)

Migliaia di attività locali esistono, lavorano, hanno clienti — ma online non esistono. Nessun sito, nessuna scheda Google, solo un profilo Facebook abbandonato. Sono **addormentate**.

**Morpheus le sveglia.**

Doppio riferimento voluto: Morfeo greco, dio del sogno — le attività senza presenza digitale dormono. Morpheus di Matrix — il tool tira fuori dal sonno le aziende invisibili online e le porta davanti a chi può aiutarle.

Raccoglie dati da **OpenStreetMap** e **Foursquare**, classifica ogni attività con uno scoring composito (distanza · assenza sito · categoria) e le mostra su una **mappa web interattiva** pronta per l'outreach.

---

## Indice

- [Funzionalità](#funzionalità)
- [Come funziona](#come-funziona)
- [Setup](#setup)
- [Avvio](#avvio)
- [Scoring](#scoring)
- [Interfaccia web](#interfaccia-web)
- [API Flask](#api-flask)
- [CLI](#cli)
- [Scoring LLM (opzionale)](#scoring-llm-opzionale)
- [Variabili d'ambiente](#variabili-dampiente)
- [Struttura del progetto](#struttura-del-progetto)
- [Stack](#stack)

---

## Funzionalità

| Feature | Descrizione |
|---------|-------------|
| **Scansione OSM** | 12 query Overpass per 9 categorie merceologiche |
| **Foursquare** | POI aggiuntivi via Places API v3 (opzionale) |
| **Scoring composito** | Priorità calcolata su distanza + assenza sito + categoria target |
| **Score personalizzato** | Slider in-app per ribilanciare i pesi senza toccare il DB |
| **Arricchimento Facebook** | Ricerca automatica profili pubblici (Brave + DuckDuckGo, ~2 req/s) |
| **Verifica siti morti** | Check HEAD/GET parallelo, badge "Sito morto" per domini scaduti |
| **Aggiunta manuale** | Modal con parsing URL Facebook/Google Maps + geocodifica Nominatim |
| **Bulk actions** | Selezione multipla, aggiornamento stato, export CSV filtrato |
| **Dataset multipli** | Scansioni separate per area geografica, unibili tra loro |
| **Job asincroni** | Scansioni in background con polling live e ripresa dopo refresh |

---

## Come funziona

```
1. Geocodifica      Nominatim risolve il punto di riferimento → lat/lon
2. Query Overpass   12 query OSM per categoria → attività grezze
3. Foursquare       Query circolare opzionale → POI aggiuntivi
4. Deduplicazione   Chiave (nome_slug, lat_3d, lon_3d) cross-source
5. Scoring          Score composito [0,1] → fascia di priorità
6. CSV              Salvataggio in data/output/osm/runs/
7. Import DB        SQLite — preserva score LLM esistenti
8. Mappa            Leaflet con viewport culling e cluster per città
```

La pipeline viene avviata dalla UI con un click e gira in background. Il frontend fa polling ogni 1.5s e aggiorna la mappa al completamento.

---

## Setup

**Requisiti:** Python 3.11+, Node.js 18+

```bash
# 1. Clona
git clone https://github.com/tuo-username/morpheus.git
cd morpheus

# 2. Ambiente Python
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 3. Frontend
cd frontend
npm install
npm run build
cd ..

# 4. Variabili d'ambiente (tutte opzionali)
cp .env.example .env
# Modifica .env se vuoi Foursquare o scoring configurato
```

---

## Avvio

```bash
# Metodo rapido
bash scripts/run_map.sh

# Oppure direttamente
.venv/bin/python3 app.py
```

Apri **http://localhost:5000**.

Al primo avvio il database è vuoto. Dalla UI:
1. Scrivi il centro geografico (es. `Varese, Lombardia, Italia`)
2. Scrivi la provincia/area OSM (es. `Provincia di Varese, Lombardia, Italia`)
3. Clicca **Avvia scansione** — la mappa si popola in 2–5 minuti

---

## Scoring

Ogni attività riceve uno score composito **[0, 1]**:

```
score = (w_dist × dist_norm) + (w_sito × assenza_sito) + (w_cat × cat_target)
        ────────────────────────────────────────────────────────────────────────
                              w_dist + w_sito + w_cat

dist_norm    = max(0, 1 − distanza_km / max_distance_km)
assenza_sito = 1.0 se ha_sito = "NO", altrimenti 0.0
cat_target   = 1.0 se categoria è tra le target, altrimenti 0.0
```

Pesi di default: `w_dist = 0.5`, `w_sito = 0.3`, `w_cat = 0.2`

| Score | Priorità |
|-------|----------|
| ≥ 0.75 | **ALTISSIMA** |
| ≥ 0.55 | **ALTA** |
| ≥ 0.35 | **MEDIA** |
| ≥ 0.20 | **BASSA** |
| < 0.20 | **MOLTO BASSA** |

I pesi sono ribilanciabili in tempo reale dalla sidebar senza toccare il database.

### Categorie rilevate

`Ristorazione` · `Ospitalità` · `Beauty & Benessere` · `Fitness & Sport` · `Sanità` · `Servizi Professionali` · `Artigiani` · `Negozi` · `Intrattenimento`

---

## Interfaccia web

```
┌─────────────────┬──────────────────────────────┬────────────────────┐
│   Sidebar       │         Mappa Leaflet         │   Lista lead       │
│                 │                               │                    │
│ · Dataset       │  Cluster per città (zoom <11) │ · Cards filtrabili │
│ · Nuova area    │  Marker individuali (zoom ≥11)│ · Stato outreach   │
│ · Facebook      │  Viewport culling + padding   │ · Bulk selection   │
│ · Siti morti    │                               │ · Export CSV       │
│ · Filtri mappa  │                               │ · +Aggiunta manuale│
│ · Score custom  │                               │                    │
└─────────────────┴──────────────────────────────┴────────────────────┘
```

**Aggiunta manuale di un'attività:**
1. Click sul pulsante `+` in alto a destra nella lista
2. Incolla un URL Facebook o Google Maps → i dati vengono estratti automaticamente
3. Oppure compila il form a mano
4. Click su `📍 Geocodifica` per ricavare lat/lon dall'indirizzo
5. Salva → il lead appare subito in cima alla lista

**Arricchimento Facebook:**
Cerca automaticamente la pagina Facebook pubblica di ogni attività usando Brave Search e DuckDuckGo come motori. ~2 richieste/secondo, robusto a rate limit. I lead già cercati (trovati o non trovati) non vengono ri-cercati.

---

## API Flask

| Endpoint | Metodo | Descrizione |
|----------|--------|-------------|
| `/api/datasets` | GET | Lista tutti i dataset con conteggi |
| `/api/datasets` | POST | Avvia scansione OSM + Foursquare (background job) |
| `/api/datasets/<id>` | DELETE | Elimina dataset e tutti i suoi lead |
| `/api/leads` | GET | Lead del dataset con filtri opzionali |
| `/api/leads` | POST | Crea lead manuale |
| `/api/leads` | PATCH | Bulk update (stato, hotlist, ecc.) |
| `/api/leads/<id>` | PATCH | Update singolo lead |
| `/api/leads/export` | GET | Export CSV con filtri correnti |
| `/api/leads/parse-url` | POST | Parsa URL Facebook/Google Maps |
| `/api/jobs/<id>` | GET | Stato job asincrono |
| `/api/geocode` | GET | Geocodifica indirizzo via Nominatim |
| `/api/comuni` | GET | Lista comuni per autocomplete |
| `/api/datasets/<id>/enrich/facebook` | POST | Avvia arricchimento Facebook |
| `/api/datasets/<id>/check-sites` | POST | Avvia verifica siti morti |

**Filtri per `GET /api/leads`:**

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `dataset_id` | string | ID dataset (default: dataset più recente) |
| `priorita` | string/list | Es. `ALTISSIMA,ALTA` |
| `categoria` | string/list | Es. `Ristorazione` |
| `comune` | string | Substring case-insensitive |
| `solo_senza_sito` | bool | Solo attività senza sito |
| `solo_hotlist` | bool | Solo lead in hotlist |
| `page_size` | int | Default 50000, max 100000 |

---

## CLI

```bash
# Importa un CSV nel database (se hai un CSV pre-esistente)
.venv/bin/python3 scripts/importa_db.py

# Con parametri
.venv/bin/python3 scripts/importa_db.py \
  --reference "Busto Arsizio, Varese, Lombardia, Italia" \
  --append   # aggiunge senza sovrascrivere

# Cerca lead da terminale
.venv/bin/python3 scripts/cerca_lead.py --categoria ristorazione --limit 20
.venv/bin/python3 scripts/cerca_lead.py --priorita ALTISSIMA ALTA --senza-sito
.venv/bin/python3 scripts/cerca_lead.py --hotlist --output csv > hotlist.csv
.venv/bin/python3 scripts/cerca_lead.py --list-datasets
```

---

## Scoring LLM (opzionale)

Richiede [Ollama](https://ollama.ai) attivo in locale con `qwen2.5:3b` o `gemma2:2b`.

```bash
ollama pull qwen2.5:3b

.venv/bin/python3 scripts/scorizza_lead.py \
  --servizio "sito web professionale" \
  --limit 50
```

Assegna uno score 0–10 ai lead in hotlist in base alla rilevanza per il servizio specificato. Lo score viene salvato nel DB e mostrato nella mappa.

---

## Variabili d'ambiente

Tutte opzionali. Copia `.env.example` in `.env` e compila.

| Variabile | Default | Descrizione |
|-----------|---------|-------------|
| `FSQ_API_KEY` | — | Foursquare Places API v3. Se assente, Foursquare viene saltato silenziosamente. |
| `SCORING_CATEGORIES` | — | Categorie target per il peso `cat_target`. Es. `Ristorazione,Artigiani` |
| `SCORING_MAX_DISTANCE_KM` | `50` | Distanza massima per normalizzare `dist_norm` |

---

## Struttura del progetto

```
morpheus/
├── app.py                        # Flask server, API REST, job asincroni
├── requirements.txt
├── .env.example
│
├── frontend/
│   ├── src/
│   │   ├── App.jsx               # Intera app React (mappa + sidebar + lista)
│   │   └── styles.css            # Design system completo
│   ├── package.json
│   └── dist/                     # Build produzione (gitignore)
│
├── scripts/
│   ├── run_map.sh                # Avvia Flask
│   ├── setup.sh                  # Setup ambiente Python
│   ├── importa_db.py             # Importa CSV nel DB SQLite
│   ├── cerca_lead.py             # Query CLI sul DB
│   └── scorizza_lead.py          # Scoring LLM via Ollama
│
├── src/morpheus/
│   ├── osm_finder.py             # MorpheusFinder — raccolta OSM + Foursquare
│   ├── db.py                     # Tutte le operazioni SQLite
│   ├── facebook_enrichment.py    # Ricerca profili Facebook pubblici
│   ├── site_checker.py           # Verifica raggiungibilità siti web
│   ├── url_parser.py             # Parsing URL Facebook/Google Maps + geocodifica
│   ├── llm_filter.py             # Scoring lead via Ollama
│   └── paths.py                  # Path centralizzate del progetto
│
└── data/
    ├── leads.db                  # Database SQLite (gitignore)
    └── output/
        └── osm/runs/             # CSV per ogni scansione (gitignore)
```

---

## Contributori

| Chi | Ruolo |
|-----|-------|
| [Marco Barlera](https://github.com/marcobarlera) | Ideazione, design, sviluppo principale |
| [Claude Sonnet](https://claude.ai) (Anthropic) | Co-sviluppatore AI — architettura, implementazione feature, debugging (sessioni 1–8) |

---

## Stack

| Strato | Tecnologia |
|--------|-----------|
| Backend | Python 3.11+ · Flask 3 |
| Database | SQLite (nessuna dipendenza esterna) |
| Geodati primari | OpenStreetMap via Overpass API |
| Geocodifica | Nominatim (OSM, gratuito) |
| Geodati secondari | Foursquare Places API v3 (opzionale) |
| Ricerca Facebook | Brave Search + DuckDuckGo (scraping HTML) |
| Frontend | React 18 · Vite · Leaflet |
| Mappe satellite | Esri World Imagery (nessuna API key) |
| Scoring LLM | Ollama locale — `qwen2.5:3b` / `gemma2:2b` (opzionale) |
