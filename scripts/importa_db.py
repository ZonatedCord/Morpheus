#!/usr/bin/env python3
"""
Popola il database SQLite a partire dai CSV esistenti.

Uso:
    python3 scripts/importa_db.py
    python3 scripts/importa_db.py --osm path/al/clienti.csv
    python3 scripts/importa_db.py --hotlist path/alla/hotlist.csv
    python3 scripts/importa_db.py --reference "Busto Arsizio, Varese, Lombardia, Italia"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from morpheus.db import dataset_id_from_reference, import_from_csv, init_db
from morpheus.paths import DB_PATH, DEFAULT_HOTLIST, DEFAULT_OSM_OUTPUT
from morpheus.varesotto_osm import DEFAULT_PROVINCE_QUERY, DEFAULT_REFERENCE_QUERY


def main() -> None:
    parser = argparse.ArgumentParser(description="Importa CSV nel database SQLite.")
    parser.add_argument("--osm", type=Path, default=DEFAULT_OSM_OUTPUT,
                        help=f"CSV base OSM (default: {DEFAULT_OSM_OUTPUT})")
    parser.add_argument("--hotlist", type=Path, default=DEFAULT_HOTLIST,
                        help=f"CSV hotlist arricchita (default: {DEFAULT_HOTLIST})")
    parser.add_argument("--reference", default=DEFAULT_REFERENCE_QUERY,
                        help=f"Centro di riferimento del dataset (default: {DEFAULT_REFERENCE_QUERY})")
    parser.add_argument("--province", default=DEFAULT_PROVINCE_QUERY,
                        help=f"Area OSM del dataset (default: {DEFAULT_PROVINCE_QUERY})")
    parser.add_argument("--dataset-id", default="",
                        help="ID dataset opzionale. Se omesso viene derivato da --reference.")
    parser.add_argument("--label", default="",
                        help="Etichetta visuale opzionale del dataset.")
    parser.add_argument("--append", action="store_true",
                        help="Aggiunge/aggiorna lead nel dataset esistente invece di sostituirlo.")
    args = parser.parse_args()

    dataset_id = args.dataset_id.strip() or dataset_id_from_reference(args.reference)
    dataset_label = args.label.strip() or ""

    print(f"Database: {DB_PATH}")
    print(f"CSV base: {args.osm}")
    print(f"Hotlist:  {args.hotlist}")
    print(f"Dataset:  {dataset_id}")
    print(f"Reference:{args.reference}")
    print(f"Mode:     {'append' if args.append else 'replace'}")
    print()

    if not args.osm.exists():
        print(f"ERRORE: CSV base non trovato: {args.osm}")
        print("Esegui prima: .venv/bin/python3 scripts/varesotto_osm.py")
        sys.exit(1)

    if not args.hotlist.exists():
        print(f"Nota: hotlist non trovata ({args.hotlist}), importo solo il CSV base.")

    print("Inizializzo database...")
    init_db(DB_PATH)

    print("Importo attività...")
    total = import_from_csv(
        args.osm,
        args.hotlist,
        DB_PATH,
        dataset_id=dataset_id,
        dataset_label=dataset_label or None,
        province_query=args.province,
        reference_query=args.reference,
        source_csv_path=str(args.osm),
        replace_dataset=not args.append,
    )

    print(f"\nDone. {total} attività nel dataset '{dataset_id}'.")
    print("Avvia la mappa con: bash scripts/run_map.sh")


if __name__ == "__main__":
    main()
