#!/usr/bin/env python3
"""
CLI per interrogare il database dei lead B2B.

Esempi:
    python3 scripts/cerca_lead.py --categoria ristorazione --limit 20
    python3 scripts/cerca_lead.py --priorita ALTISSIMA --senza-sito
    python3 scripts/cerca_lead.py --hotlist --priorita ALTISSIMA ALTA
    python3 scripts/cerca_lead.py --comune vedano --limit 10
    python3 scripts/cerca_lead.py --hotlist --output csv > hotlist.csv
    python3 scripts/cerca_lead.py --list-datasets
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from morpheus.db import count_leads, list_datasets, query_leads
from morpheus.paths import DB_PATH

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
    parser.add_argument("--dataset", "-d", metavar="DATASET",
                        help="Dataset/origine da interrogare (default: dataset più recente)")
    parser.add_argument("--list-datasets", action="store_true",
                        help="Mostra i dataset disponibili e termina")
    parser.add_argument("--limit", "-n", type=int, default=20, metavar="N",
                        help="Numero massimo di risultati (default: 20)")
    parser.add_argument("--output", choices=["table", "csv"], default="table",
                        help="Formato output: table (default) o csv")
    args = parser.parse_args()

    if args.list_datasets:
        datasets = list_datasets(DB_PATH)
        if not datasets:
            print("Nessun dataset disponibile.", file=sys.stderr)
            sys.exit(0)
        for dataset in datasets:
            active = " *" if dataset.get("is_active") else ""
            print(
                f"{dataset['dataset_id']}{active}\t{dataset['label']}\t"
                f"{dataset['lead_count']} lead\t{dataset['reference_query']}"
            )
        sys.exit(0)

    total = count_leads(DB_PATH, dataset_id=args.dataset)
    if total == 0:
        print("Database vuoto. Esegui: python3 scripts/importa_db.py", file=sys.stderr)
        sys.exit(1)

    leads = query_leads(
        priorita=args.priorita,
        categoria=args.categoria,
        solo_senza_sito=args.senza_sito,
        solo_hotlist=args.hotlist,
        comune=args.comune,
        limit=args.limit,
        dataset_id=args.dataset,
        db_path=DB_PATH,
    )

    if not leads:
        print("Nessun risultato con i filtri applicati.", file=sys.stderr)
        sys.exit(0)

    if args.output == "csv":
        print_csv_output(leads)
    else:
        print(f"\n{len(leads)} risultati (su {total} nel dataset)\n")
        print_table(leads)
        print()


if __name__ == "__main__":
    main()
