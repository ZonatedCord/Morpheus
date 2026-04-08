# Flusso ChatGPT Deep Research

## Obiettivo

Preparare un batch ridotto di attivita da dare a ChatGPT / Deep Research per fare una ricerca manuale guidata, con output strutturato e poi riutilizzabile nel flusso commerciale.

## Comando

```bash
python3 scripts/prepara_shortlist_chatgpt.py --limit 30
```

## File generati

- `data/input/research/attivita_shortlist_chatgpt.csv`
- `data/input/research/attivita_shortlist_chatgpt_template.csv`
- `data/output/research/attivita_shortlist_chatgpt.md`

## Uso consigliato

1. Genera la shortlist.
2. Carica in ChatGPT il file `attivita_shortlist_chatgpt.csv`.
3. Copia il prompt da `docs/PROMPT_CHATGPT_DEEP_RESEARCH.md`.
4. Chiedi un output CSV con le stesse colonne del template.
5. Usa i risultati per messaggi mirati o per un import successivo.

## Regole pratiche

- Lavora a piccoli batch, idealmente 15-30 attivita.
- Chiedi sempre di verificare il match con nome, comune e indirizzo.
- Se il match non e' affidabile, fai scrivere `DA_VERIFICARE`.
- Non usare il primo link trovato come verita: servono fonti coerenti.

## Quando usarlo

- Quando lo script automatico non trova abbastanza recensioni o dati qualitativi.
- Quando vuoi un supporto rapido su un sottoinsieme di aziende ad alta priorita.
- Quando vuoi affiancare il lavoro automatico con una ricerca guidata ma ancora strutturata.
