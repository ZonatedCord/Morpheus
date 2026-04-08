#!/usr/bin/env python3
"""
Popola il database SQLite a partire dai CSV esistenti.

Uso:
    python scripts/importa_db.py
    python scripts/importa_db.py --osm path/al/clienti.csv
    python scripts/importa_db.py --hotlist path/alla/hotlist.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from finder_clienti_varesotto.db import import_from_csv, init_db
from finder_clienti_varesotto.paths import DB_PATH, DEFAULT_HOTLIST, DEFAULT_OSM_OUTPUT


def main() -> None:
    parser = argparse.ArgumentParser(description="Importa CSV nel database SQLite.")
    parser.add_argument("--osm", type=Path, default=DEFAULT_OSM_OUTPUT,
                        help=f"CSV base OSM (default: {DEFAULT_OSM_OUTPUT})")
    parser.add_argument("--hotlist", type=Path, default=DEFAULT_HOTLIST,
                        help=f"CSV hotlist arricchita (default: {DEFAULT_HOTLIST})")
    args = parser.parse_args()

    print(f"Database: {DB_PATH}")
    print(f"CSV base: {args.osm}")
    print(f"Hotlist:  {args.hotlist}")
    print()

    if not args.osm.exists():
        print(f"ERRORE: CSV base non trovato: {args.osm}")
        print("Esegui prima: python scripts/varesotto_osm.py")
        sys.exit(1)

    if not args.hotlist.exists():
        print(f"Nota: hotlist non trovata ({args.hotlist}), importo solo il CSV base.")

    print("Inizializzo database...")
    init_db(DB_PATH)

    print("Importo attività...")
    total = import_from_csv(args.osm, args.hotlist, DB_PATH)

    print(f"\nDone. {total} attività totali nel database.")
    print("Avvia la mappa con: python app.py")


if __name__ == "__main__":
    main()
