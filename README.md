# Morpheus

> *"Morpheus ti mostra la verità."*

Migliaia di attività locali esistono, lavorano, hanno clienti — ma online non esistono. Nessun sito, nessuna scheda Google, solo un profilo Facebook abbandonato. Sono **addormentate**.

**Morpheus le sveglia.**

Doppio riferimento voluto: Morfeo greco, dio del sogno — le attività senza presenza digitale dormono. Morpheus di Matrix — il tool tira fuori dal sonno le aziende invisibili online e le porta davanti a chi può aiutarle.

Raccoglie dati da **OpenStreetMap** e **Foursquare**, classifica le attività con uno scoring composito (distanza · assenza sito · categoria) e le mostra su una **mappa web interattiva** pronta per l'outreach.

---

## Funzionalità

- **Scansione OSM + Foursquare** — 9 categorie, 12 query Overpass, deduplicazione automatica
- **Scoring composito** — distanza + assenza sito + categoria target (configurabile via slider)
- **Mappa Leaflet** — cluster per città a zoom basso, viewport culling per grandi dataset
- **Arricchimento Facebook** — ricerca automatica profili pubblici (Brave + DuckDuckGo)
- **Verifica siti morti** — check parallelo, badge "Sito morto" per siti non raggiungibili
- **Aggiunta manuale** — modal con parsing URL Facebook/Google Maps e geocodifica Nominatim
- **Bulk actions** — selezione multipla, aggiornamento stato, export CSV

---

## Setup

**Requisiti:** Python 3.11+, Node.js 18+

```bash
# Clona il repo
git clone https://github.com/tuo-username/morpheus.git
cd morpheus

# Ambiente Python
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Frontend
cd frontend && npm install && npm run build && cd ..

# Variabili d'ambiente (opzionali)
cp .env.example .env

# Avvio
.venv/bin/python3 app.py
# → http://localhost:5000
```

---

## Variabili d'ambiente

| Variabile | Default | Descrizione |
|-----------|---------|-------------|
| `FSQ_API_KEY` | — | Foursquare Places API v3 (opzionale) |
| `SCORING_CATEGORIES` | — | Categorie target (es. `Ristorazione,Artigiani`) |
| `SCORING_MAX_DISTANCE_KM` | `50` | Distanza massima per normalizzazione score |

---

## Struttura

```
morpheus/
├── app.py                    # Flask server + API REST + job asincroni
├── requirements.txt
├── .env.example
├── data/
│   └── leads.db              # SQLite (gitignore)
├── frontend/
│   ├── src/App.jsx           # React app principale
│   └── dist/                 # Build produzione (gitignore)
├── scripts/
│   ├── importa_db.py         # Importa CSV nel DB
│   ├── cerca_lead.py         # Query CLI sul DB
│   ├── scorizza_lead.py      # Scoring LLM via Ollama (opzionale)
│   └── run_map.sh
└── src/morpheus/
    ├── osm_finder.py         # MorpheusFinder — raccolta OSM + Foursquare
    ├── db.py                 # Operazioni SQLite
    ├── facebook_enrichment.py
    ├── site_checker.py
    ├── url_parser.py
    ├── llm_filter.py
    └── paths.py
```

---

## API Flask

| Endpoint | Metodo | Descrizione |
|----------|--------|-------------|
| `/api/datasets` | GET | Lista dataset |
| `/api/datasets` | POST | Avvia scansione OSM (background job) |
| `/api/leads` | GET | Lead con filtri opzionali |
| `/api/leads` | POST | Crea lead manuale |
| `/api/leads/export` | GET | Export CSV filtrato |
| `/api/jobs/{id}` | GET | Stato job asincrono |
| `/api/datasets/{id}/enrich/facebook` | POST | Arricchimento Facebook |
| `/api/datasets/{id}/check-sites` | POST | Verifica siti morti |

---

## Stack

| Strato | Tecnologia |
|--------|-----------|
| Backend | Python 3.13 + Flask |
| Database | SQLite |
| Geodati | OpenStreetMap (Overpass API) + Nominatim |
| Dati extra | Foursquare Places API v3 |
| Frontend | React 18 + Vite + Leaflet |
| Scoring LLM | Ollama locale (`qwen2.5:3b`, opzionale) |
