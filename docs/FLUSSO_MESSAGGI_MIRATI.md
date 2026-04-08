# Flusso Messaggi Mirati

## Obiettivo

Preparare un primo messaggio commerciale personalizzato senza scriverlo da zero ogni volta.

Il flusso usa:

- dati strutturati del CSV OSM
- note manuali e recensioni raccolte da te
- regole per trasformare i segnali in una proposta mirata

## File coinvolti

- `scripts/genera_messaggi_mirati.py`
- `data/input/research/attivita_insights.csv`
- `data/output/outreach/attivita_messaggi_mirati.csv`
- `data/output/outreach/attivita_messaggi_mirati.md`

## Come funziona

1. Legge il CSV base delle attivita.
2. Seleziona i prospect prioritari, di default quelli senza sito.
3. Sincronizza un file `attivita_insights.csv` con le colonne che puoi compilare a mano.
4. Usa dati strutturati e note manuali per costruire:
   - punto debole principale
   - leva commerciale
   - proposta mirata
   - apertura messaggio
   - bozza WhatsApp
   - bozza email

## Comando base

```bash
python3 scripts/genera_messaggi_mirati.py --limit 30
```

## Workflow consigliato

1. Esegui lo script una prima volta.
2. Apri `data/input/research/attivita_insights.csv`.
3. Per ogni attivita, aggiungi:
   - cosa fanno davvero
   - 1 o 2 punti forti emersi dalle recensioni
   - 1 criticita utile
   - eventuale proposta preferita
4. Riesegui lo script.
5. Apri `data/output/outreach/attivita_messaggi_mirati.csv` e usa la bozza come base del contatto.

## Limite importante

Lo script non deve inventare recensioni o problemi.

Se non ci sono note manuali:

- usa solo segnali oggettivi del dataset
- formula osservazioni prudenti
- indica cosa verificare prima del contatto

Questo evita messaggi aggressivi o poco credibili.
