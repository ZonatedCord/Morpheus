#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys

from _bootstrap import bootstrap_project


bootstrap_project()

from morpheus.db import count_leads, init_db
from morpheus.llm_filter import score_batch
from morpheus.paths import DB_PATH


def _truncate(value: str, width: int) -> str:
    return value if len(value) <= width else value[: width - 3] + "..."


def main() -> int:
    parser = argparse.ArgumentParser(description="Scorizza i lead hotlist via Ollama locale.")
    parser.add_argument("--servizio", required=True, help="Servizio da valutare, es. 'sito web'")
    parser.add_argument("--limit", type=int, default=100, help="Numero massimo di lead da processare")
    parser.add_argument("--model", default=None, help="Modello Ollama opzionale. Se omesso, viene scelto automaticamente.")
    args = parser.parse_args()

    init_db(DB_PATH)
    total = count_leads(DB_PATH)
    if total == 0:
        print("Database vuoto. Esegui prima: python3 scripts/importa_db.py", file=sys.stderr)
        return 1

    results = score_batch(
        servizio=args.servizio,
        limit=args.limit,
        model=args.model,
        db_path=DB_PATH,
    )
    scored = [lead for lead in results if lead.get("score") is not None]
    top = scored[:10]

    print(f"Servizio: {args.servizio}")
    print(f"Lead analizzati: {len(results)}")
    print(f"Lead aggiornati con score: {len(scored)}")
    print()

    if not top:
        print("Nessun punteggio assegnato. Verifica che Ollama sia attivo su http://127.0.0.1:11434.")
        return 0

    print("Top 10 lead per rilevanza:\n")
    for lead in top:
        motivo = _truncate(lead.get("motivazione", ""), 88)
        print(
            f"{lead.get('score', '-')}/10"
            f" | {lead.get('nome', '')}"
            f" | {lead.get('categoria', '')}"
            f" | {lead.get('comune', '')}"
            f" | {lead.get('priorita', '')}"
        )
        if motivo:
            print(f"    {motivo}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
