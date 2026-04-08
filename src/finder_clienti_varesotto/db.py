from __future__ import annotations

import csv
import sqlite3
from datetime import datetime
from pathlib import Path

from .paths import DB_PATH, DEFAULT_HOTLIST, DEFAULT_OSM_OUTPUT

SCHEMA = """
CREATE TABLE IF NOT EXISTS attivita (
    osm_url        TEXT PRIMARY KEY,
    nome           TEXT NOT NULL,
    lat            REAL,
    lon            REAL,
    priorita       TEXT,
    distanza_km    REAL,
    categoria      TEXT,
    sottocategoria TEXT,
    comune         TEXT,
    indirizzo      TEXT,
    telefono       TEXT,
    email          TEXT,
    sito           TEXT,
    ha_sito        TEXT,
    stato          TEXT DEFAULT '',
    proposta       TEXT DEFAULT '',
    criticita      TEXT DEFAULT '',
    rating         TEXT DEFAULT '',
    in_hotlist     INTEGER DEFAULT 0,
    aggiornato_il  TEXT
);
"""


def init_db(db_path: Path = DB_PATH) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


def _norm(s: str) -> str:
    return s.strip().lower()


def import_from_csv(
    osm_csv: Path = DEFAULT_OSM_OUTPUT,
    hotlist_csv: Path = DEFAULT_HOTLIST,
    db_path: Path = DB_PATH,
) -> int:
    if not osm_csv.exists():
        raise FileNotFoundError(f"CSV base non trovato: {osm_csv}")

    hotlist: dict[str, dict] = {}
    if hotlist_csv.exists():
        with hotlist_csv.open(encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                key = _norm(row.get("Nome Attivita", "") or "")
                if key:
                    hotlist[key] = row

    rows = []
    with osm_csv.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            nome = (row.get("Nome Attivita'") or "").strip()
            if not nome:
                continue

            try:
                lat = float(row.get("Lat") or "")
                lon = float(row.get("Lon") or "")
            except (ValueError, TypeError):
                lat = lon = None

            try:
                dist = float(row.get("Distanza da Vedano Olona (km)") or 0)
            except ValueError:
                dist = 0.0

            osm_url = (row.get("OSM URL") or "").strip() or nome
            hl = hotlist.get(_norm(nome), {})

            rows.append((
                osm_url,
                nome,
                lat,
                lon,
                (row.get("Priorita'") or "").strip(),
                dist,
                (row.get("Categoria") or "").strip(),
                (row.get("Sottocategoria") or "").strip(),
                (row.get("Comune") or "").strip(),
                (row.get("Indirizzo") or "").strip(),
                (hl.get("Telefono") or row.get("Telefono") or "").strip(),
                (hl.get("Email") or row.get("Email") or "").strip(),
                (hl.get("Sito") or row.get("Sito Web") or "").strip(),
                (row.get("Ha Sito Web") or "").strip(),
                hl.get("Stato", ""),
                hl.get("Proposta Mirata Base", ""),
                hl.get("Criticita", ""),
                hl.get("Rating Principale", ""),
                1 if hl else 0,
                datetime.now().isoformat(),
            ))

    conn = sqlite3.connect(db_path)
    conn.executemany(
        "INSERT OR REPLACE INTO attivita VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    conn.commit()
    total = conn.execute("SELECT COUNT(*) FROM attivita").fetchone()[0]
    in_hotlist = conn.execute("SELECT COUNT(*) FROM attivita WHERE in_hotlist=1").fetchone()[0]
    with_coords = conn.execute("SELECT COUNT(*) FROM attivita WHERE lat IS NOT NULL").fetchone()[0]
    conn.close()

    print(f"  Importate {len(rows)} attività ({with_coords} con coordinate, {in_hotlist} in hotlist)")
    return total


def query_leads(
    priorita: list[str] | None = None,
    categoria: list[str] | None = None,
    solo_senza_sito: bool = False,
    solo_hotlist: bool = False,
    comune: str | None = None,
    limit: int | None = None,
    db_path: Path = DB_PATH,
) -> list[dict]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    where: list[str] = []
    params: list = []

    if priorita:
        where.append(f"priorita IN ({','.join('?' * len(priorita))})")
        params.extend(priorita)
    if categoria:
        where.append(f"categoria IN ({','.join('?' * len(categoria))})")
        params.extend(categoria)
    if solo_senza_sito:
        where.append("ha_sito = 'NO'")
    if solo_hotlist:
        where.append("in_hotlist = 1")
    if comune:
        where.append("comune LIKE ?")
        params.append(f"%{comune}%")

    sql = "SELECT * FROM attivita"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += (
        " ORDER BY CASE priorita"
        " WHEN 'ALTISSIMA' THEN 1"
        " WHEN 'ALTA' THEN 2"
        " WHEN 'MEDIA' THEN 3"
        " WHEN 'BASSA' THEN 4"
        " ELSE 5 END, distanza_km"
    )
    if limit:
        sql += f" LIMIT {limit}"

    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def count_leads(db_path: Path = DB_PATH) -> int:
    if not db_path.exists():
        return 0
    conn = sqlite3.connect(db_path)
    n = conn.execute("SELECT COUNT(*) FROM attivita").fetchone()[0]
    conn.close()
    return n
