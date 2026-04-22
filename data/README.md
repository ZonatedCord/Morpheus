# data/

Tutti i file in questa cartella sono esclusi da git (`.gitignore`).
Contengono dati reali di attività commerciali — non pubblicare.

---

## Struttura

```
data/
├── leads.db              # Database SQLite principale
└── output/
    └── osm/
        ├── morpheus_leads.csv       # CSV default (primo import)
        └── runs/                    # Un CSV per ogni scansione
            └── <dataset-id>--<provincia>.csv
```

---

## Database SQLite — `leads.db`

### Tabella `attivita`

| Campo | Tipo | Note |
|-------|------|------|
| `osm_url` | TEXT PK | Chiave: `dataset_id::osm_url` · `foursquare://fsq_id` · `gplaces://place_id` · `manual://uuid` |
| `nome` | TEXT | Nome attività |
| `lat`, `lon` | REAL | Coordinate GPS (null per lead manuali senza geocodifica) |
| `priorita` | TEXT | ALTISSIMA / ALTA / MEDIA / BASSA / MOLTO BASSA |
| `distanza_km` | REAL | Dal punto di riferimento del dataset |
| `categoria` | TEXT | Una delle 9 macro-categorie |
| `sottocategoria` | TEXT | Tag OSM, categoria Foursquare o `primaryTypeDisplayName` Google Places |
| `comune` | TEXT | Città |
| `indirizzo` | TEXT | Via + numero civico (da `addr:street` + `addr:housenumber` OSM) |
| `telefono`, `email`, `sito` | TEXT | Contatti |
| `facebook_url` | TEXT | URL profilo Facebook (`N/F` = cercato e non trovato) |
| `ha_sito` | TEXT | `SI` / `NO` / `MORTO` (sito non raggiungibile) |
| `stato` | TEXT | Stato outreach: `Contattata` / `Rifiutata` / `Scartata` |
| `proposta` | TEXT | Proposta commerciale (da hotlist CSV o LLM) |
| `in_hotlist` | INTEGER | 0 / 1 |
| `rilevanza_score` | INTEGER | Score LLM 0–10 (da `scorizza_lead.py`) |
| `dataset_id` | TEXT | FK → `dataset_runs` |

### Tabella `dataset_runs`

| Campo | Note |
|-------|------|
| `dataset_id` | Slug del punto di riferimento (es. `varese-lombardia-italia`) |
| `label` | Nome leggibile del dataset |
| `reference_query` | Query Nominatim usata (es. `Varese, Lombardia, Italia`) |
| `reference_lat/lon` | Coordinate del punto di riferimento |
| `province_query` | Area OSM scansionata |
| `lead_count` | Conteggio aggregato lead |

### Tabella `jobs`

Job asincroni (scansione, Facebook, verifica siti). I job in stato `running` o `queued` al riavvio vengono marcati `interrupted`.

---

## CSV di scansione

Ogni scansione produce un CSV in `data/output/osm/runs/` con nome:

```
<dataset-id>--<provincia-slug>.csv
```

Colonne principali: `Nome Attivita'`, `Lat`, `Lon`, `Distanza da Vedano Olona (km)`, `Priorita'`, `Categoria`, `Sottocategoria`, `Comune`, `Indirizzo`, `Telefono`, `Email`, `Sito Web`, `OSM URL`.

---

## Hotlist CSV (opzionale)

File `data/output/research/morpheus_hotlist.csv` — arricchimento manuale dei lead prioritari.

Colonne riconosciute durante l'import:

| Colonna CSV | Campo DB |
|-------------|----------|
| `Nome Attivita` | chiave di match |
| `Telefono` | `telefono` |
| `Email` | `email` |
| `Sito` | `sito` |
| `Stato` | `stato` |
| `Proposta Mirata Base` | `proposta` |
| `Criticita` | `criticita` |
| `Rating Principale` | `rating` |
