# FinderClientiVaresotto

Progetto Python per trovare attivita commerciali nella provincia di Varese, ordinarle per priorita geografica e gestire un flusso alternativo basato su LinkedIn.

## Struttura

```text
FinderClientiVaresotto/
├── data/
│   ├── input/
│   │   └── linkedin/
│   └── output/
│       ├── linkedin/
│       └── osm/
├── docs/
├── scripts/
└── src/
    └── finder_clienti_varesotto/
```

## Setup

```bash
bash scripts/setup.sh
source .venv/bin/activate
```

## Comandi principali

Flusso OSM:

```bash
python3 scripts/varesotto_client_finder.py
python3 scripts/varesotto_osm.py --limit 300
python3 scripts/varesotto_osm.py --output data/output/osm/clienti_varesotto_test.csv
```

Flusso LinkedIn:

```bash
python3 scripts/varesotto_linkedin.py
python3 scripts/varesotto_linkedin_import.py
```

Flusso messaggi mirati:

```bash
python3 scripts/genera_messaggi_mirati.py --limit 30
```

Flusso ricerca online aziende:

```bash
python3 scripts/ricerca_aziende_online.py --limit 10
```

Shortlist per ChatGPT / Deep Research:

```bash
python3 scripts/prepara_shortlist_chatgpt.py --limit 30
```

## Output

- `data/output/osm/clienti_varesotto.csv`: output principale OSM.
- `data/output/osm/clienti_varesotto_test.csv`: export di test.
- `data/output/osm/clienti_varesotto.xlsx`: versione spreadsheet gia presente.
- `data/output/linkedin/clienti_varesotto_linkedin.csv`: output del flusso LinkedIn.
- `data/output/outreach/attivita_messaggi_mirati.csv`: analisi commerciale e bozze di messaggio.
- `data/output/research/attivita_shortlist_outreach_ready.csv`: shortlist arricchita e curata.
- `data/output/research/clienti_varesotto_outreach_ready.csv`: CSV totale in formato outreach-ready.
- `data/output/research/clienti_varesotto_outreach_ok.csv`: subset di lead `OK`.
- `data/output/research/clienti_varesotto_outreach_parziali_contattabili.csv`: subset di lead `PARZIALI` contattabili.
- `data/output/research/clienti_varesotto_outreach_hotlist.csv`: hotlist finale combinata.
- `data/input/research/attivita_shortlist_chatgpt.csv`: shortlist da caricare in ChatGPT / Deep Research.
- `data/input/research/attivita_shortlist_chatgpt_template.csv`: template risultati atteso da ChatGPT / Deep Research.

## Documentazione

- `docs/RIEPILOGO_PROGETTO.md`
- `docs/README.md`
- `docs/STRUTTURA_PROGETTO.md`
- `docs/FLUSSO_OSM.md`
- `docs/FLUSSO_LINKEDIN.md`
- `docs/FLUSSO_RICERCA_ONLINE.md`
- `docs/FLUSSO_MESSAGGI_MIRATI.md`
- `docs/FLUSSO_CHATGPT_DEEP_RESEARCH.md`
- `docs/PROMPT_CHATGPT_DEEP_RESEARCH.md`
- `docs/STRATEGIA_ACQUISIZIONE.md`
- `data/README.md`

## Note operative

- `.venv` e l'ambiente virtuale consigliato.
- `venv` e mantenuto come ambiente legacy per non rompere path esistenti.
- `__pycache__` e cache Python rigenerabile: non fa parte della struttura logica del progetto.
