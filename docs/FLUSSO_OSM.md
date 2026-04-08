# Flusso OSM

## Script coinvolti

- `scripts/varesotto_client_finder.py`: entrypoint storico compatibile.
- `scripts/varesotto_osm.py`: entrypoint diretto del finder OSM.
- `src/finder_clienti_varesotto/varesotto_osm.py`: logica applicativa.

## Funzionamento

1. Geocodifica il punto di riferimento, di default Vedano Olona.
2. Risolve l'area amministrativa della provincia di Varese.
3. Interroga Overpass per gruppi di attivita.
4. Deduplica, ordina per distanza e salva il CSV finale.

## Input e output

- Input implicito: rete, Nominatim e Overpass.
- Output principale: `data/output/osm/clienti_varesotto.csv`.
- Output di test opzionale: `data/output/osm/clienti_varesotto_test.csv`.

## Comandi utili

```bash
python3 scripts/varesotto_client_finder.py
python3 scripts/varesotto_osm.py --limit 300
python3 scripts/varesotto_osm.py --reference "Vedano Olona, Varese, Lombardia, Italia"
```

## Note

- Serve connessione internet.
- I dati dipendono dalla qualita dei tag OpenStreetMap.
- Gli output vengono salvati nella cartella `data/output/osm/` per separare questo flusso da quello LinkedIn.
