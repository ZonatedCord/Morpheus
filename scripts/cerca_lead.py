#!/usr/bin/env python3
"""
CLI per interrogare il database dei lead B2B.

Esempi:
    python scripts/cerca_lead.py --categoria ristorazione --limit 20
    python scripts/cerca_lead.py --priorita ALTISSIMA --senza-sito
    python scripts/cerca_lead.py --hotlist --priorita ALTISSIMA ALTA
    python scripts/cerca_lead.py --comune vedano --limit 10
    python scripts/cerca_lead.py --hotlist --output csv > hotlist.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from finder_clienti_varesotto.db import count_leads, query_leads
from finder_clienti_varesotto.paths import DB_PATH

COLS_DISPLAY = ["nome", "categoria", "comune", "telefono", "sito", "priorita", "distanza_km", "in_hotlist"]
COLS_CSV = ["nome", "categoria", "comune", "telefono", "email", "sito", "ha_sito",
            "priorita", "distanza_km", "stato", "proposta", "rating", "in_hotlist"]

COL_WIDTHS = {"nome": 30, "categoria": 16, "comune": 16, "telefono": 14,
              "sito": 28, "priorita": 10, "distanza_km": 8, "in_hotlist": 2}


def fmt_cell(val: object, col: str) -> str:
    w = COL_WIDTHS.get(col, 14)
    s = str(val) if val is not None else ""
    if col == "in_hotlist":
        s = "★" if val else ""
    elif col == "sito" and s not in ("", "N/D"):
        s = s.replace("https://", "").replace("http://", "").rstrip("/")
    return s[:w].ljust(w)


def print_table(leads: list[dict]) -> None:
    header = "  ".join(fmt_cell(c.upper(), c) for c in COLS_DISPLAY)
    print(header)
    print("-" * len(header))
    for r in leads:
        print("  ".join(fmt_cell(r.get(c, ""), c) for c in COLS_DISPLAY))


def print_csv_output(leads: list[dict]) -> None:
    writer = csv.DictWriter(sys.stdout, fieldnames=COLS_CSV, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(leads)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Cerca lead nel database B2B.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--categoria", "-c", nargs="+", metavar="CAT",
                        help="Filtra per categoria (es. Ristorazione)")
    parser.add_argument("--priorita", "-p", nargs="+", metavar="PRI",
                        help="Filtra per priorità (es. ALTISSIMA ALTA)")
    parser.add_argument("--comune", "-m", metavar="COMUNE",
                        help="Filtra per comune (substring, case-insensitive)")
    parser.add_argument("--senza-sito", action="store_true",
                        help="Solo attività senza sito web")
    parser.add_argument("--hotlist", action="store_true",
                        help="Solo lead nella hotlist arricchita")
    parser.add_argument("--limit", "-n", type=int, default=30, metavar="N",
                        help="Numero massimo di risultati (default: 30)")
    parser.add_argument("--output", choices=["table", "csv"], default="table",
                        help="Formato output: table (default) o csv")
    args = parser.parse_args()

    total = count_leads(DB_PATH)
    if total == 0:
        print("Database vuoto. Esegui: python scripts/importa_db.py", file=sys.stderr)
        sys.exit(1)

    # Normalizza categoria (case-insensitive match contro valori nel DB)
    categoria = None
    if args.categoria:
        # Passa as-is, il DB è case-sensitive ma la query usa IN()
        categoria = args.categoria

    leads = query_leads(
        priorita=args.priorita,
        categoria=categoria,
        solo_senza_sito=args.senza_sito,
        solo_hotlist=args.hotlist,
        comune=args.comune,
        limit=args.limit,
        db_path=DB_PATH,
    )

    if not leads:
        print("Nessun risultato con i filtri applicati.", file=sys.stderr)
        sys.exit(0)

    if args.output == "csv":
        print_csv_output(leads)
    else:
        print(f"\n{len(leads)} risultati (su {total} totali)\n")
        print_table(leads)
        print()


if __name__ == "__main__":
    main()
