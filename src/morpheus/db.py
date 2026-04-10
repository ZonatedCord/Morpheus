from __future__ import annotations

import csv
import re
import sqlite3
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .paths import (
    DB_PATH,
    DEFAULT_HOTLIST,
    DEFAULT_OSM_OUTPUT,
    OSM_RUNS_DIR,
    ensure_parent_dir,
)
from .varesotto_osm import (
    DEFAULT_PROVINCE_QUERY,
    DEFAULT_REFERENCE_POINT,
    DEFAULT_REFERENCE_QUERY,
    MorpheusFinder,
)

ATTIVITA_SCHEMA = """
CREATE TABLE IF NOT EXISTS attivita (
    osm_url               TEXT PRIMARY KEY,
    nome                  TEXT NOT NULL,
    lat                   REAL,
    lon                   REAL,
    priorita              TEXT,
    distanza_km           REAL,
    categoria             TEXT,
    sottocategoria        TEXT,
    comune                TEXT,
    indirizzo             TEXT,
    telefono              TEXT,
    email                 TEXT,
    sito                  TEXT,
    ha_sito               TEXT,
    stato                 TEXT DEFAULT '',
    proposta              TEXT DEFAULT '',
    criticita             TEXT DEFAULT '',
    rating                TEXT DEFAULT '',
    in_hotlist            INTEGER DEFAULT 0,
    rilevanza_score       INTEGER,
    rilevanza_motivazione TEXT DEFAULT '',
    aggiornato_il         TEXT
);
"""

DATASET_SCHEMA = """
CREATE TABLE IF NOT EXISTS dataset_runs (
    dataset_id       TEXT PRIMARY KEY,
    label            TEXT NOT NULL,
    province_query   TEXT NOT NULL,
    reference_query  TEXT NOT NULL,
    reference_name   TEXT NOT NULL,
    reference_lat    REAL,
    reference_lon    REAL,
    source_csv_path  TEXT DEFAULT '',
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL
);
"""

ATTIVITA_COLUMNS = (
    "osm_url",
    "nome",
    "lat",
    "lon",
    "priorita",
    "distanza_km",
    "categoria",
    "sottocategoria",
    "comune",
    "indirizzo",
    "telefono",
    "email",
    "sito",
    "ha_sito",
    "stato",
    "proposta",
    "criticita",
    "rating",
    "in_hotlist",
    "rilevanza_score",
    "rilevanza_motivazione",
    "dataset_id",
    "source_osm_url",
    "aggiornato_il",
)

OPTIONAL_COLUMNS = {
    "rilevanza_score": "ALTER TABLE attivita ADD COLUMN rilevanza_score INTEGER",
    "rilevanza_motivazione": "ALTER TABLE attivita ADD COLUMN rilevanza_motivazione TEXT DEFAULT ''",
    "dataset_id": "ALTER TABLE attivita ADD COLUMN dataset_id TEXT DEFAULT ''",
    "source_osm_url": "ALTER TABLE attivita ADD COLUMN source_osm_url TEXT DEFAULT ''",
}

LEGACY_DATASET_ID = "vedano-olona-varese-lombardia-italia"


def _norm(value: str) -> str:
    return value.strip().lower()


def _slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_value).strip("-")
    return slug or f"dataset-{datetime.now().strftime('%Y%m%d%H%M%S')}"


def dataset_id_from_reference(reference_query: str) -> str:
    return _slugify(reference_query)


def _merge_metadata_value(current: str, new: str) -> str:
    values: list[str] = []
    for raw in (current, new):
        for part in str(raw or "").split(" | "):
            cleaned = part.strip()
            if cleaned and cleaned not in values:
                values.append(cleaned)
    return " | ".join(values)


def _merge_text_values(existing: str, new_value: str, *, separator: str = " | ") -> str:
    values: list[str] = []
    for raw_value in (existing, new_value):
        for item in str(raw_value or "").split(separator):
            cleaned = item.strip()
            if cleaned and cleaned not in values:
                values.append(cleaned)
    return separator.join(values)


def _ensure_optional_columns(conn: sqlite3.Connection) -> None:
    existing = {row[1] for row in conn.execute("PRAGMA table_info(attivita)")}
    for col, ddl in OPTIONAL_COLUMNS.items():
        if col not in existing:
            conn.execute(ddl)


def _bootstrap_legacy_dataset(conn: sqlite3.Connection) -> None:
    row_count = conn.execute("SELECT COUNT(*) FROM attivita").fetchone()[0]
    if row_count == 0:
        return

    blank_dataset_rows = conn.execute(
        "SELECT COUNT(*) FROM attivita WHERE COALESCE(dataset_id, '') = ''"
    ).fetchone()[0]
    if blank_dataset_rows == 0:
        return

    now = datetime.now().isoformat()
    conn.execute(
        """
        INSERT OR IGNORE INTO dataset_runs (
            dataset_id, label, province_query, reference_query, reference_name,
            reference_lat, reference_lon, source_csv_path, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            LEGACY_DATASET_ID,
            DEFAULT_REFERENCE_POINT["name"],
            DEFAULT_PROVINCE_QUERY,
            DEFAULT_REFERENCE_QUERY,
            DEFAULT_REFERENCE_POINT["name"],
            DEFAULT_REFERENCE_POINT["lat"],
            DEFAULT_REFERENCE_POINT["lon"],
            str(DEFAULT_OSM_OUTPUT),
            now,
            now,
        ),
    )
    conn.execute(
        """
        UPDATE attivita
        SET dataset_id = ?, source_osm_url = COALESCE(NULLIF(source_osm_url, ''), osm_url)
        WHERE COALESCE(dataset_id, '') = ''
        """,
        (LEGACY_DATASET_ID,),
    )


def init_db(db_path: Path = DB_PATH) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(ATTIVITA_SCHEMA)
    conn.executescript(DATASET_SCHEMA)
    _ensure_optional_columns(conn)
    _bootstrap_legacy_dataset(conn)
    conn.commit()
    conn.close()


def _resolve_dataset_id(conn: sqlite3.Connection, dataset_id: str | None) -> str | None:
    if dataset_id:
        row = conn.execute(
            "SELECT dataset_id FROM dataset_runs WHERE dataset_id = ?",
            (dataset_id,),
        ).fetchone()
        return row[0] if row else None

    row = conn.execute(
        "SELECT dataset_id FROM dataset_runs ORDER BY updated_at DESC, dataset_id DESC LIMIT 1"
    ).fetchone()
    if row:
        return row[0]

    row = conn.execute(
        "SELECT dataset_id FROM attivita WHERE COALESCE(dataset_id, '') != '' LIMIT 1"
    ).fetchone()
    return row[0] if row else None


def _get_dataset_summary(conn: sqlite3.Connection, dataset_id: str) -> dict | None:
    row = conn.execute(
        """
        SELECT
            dr.dataset_id,
            dr.label,
            dr.province_query,
            dr.reference_query,
            dr.reference_name,
            dr.reference_lat,
            dr.reference_lon,
            dr.source_csv_path,
            dr.created_at,
            dr.updated_at,
            COALESCE(COUNT(a.osm_url), 0) AS lead_count,
            COALESCE(SUM(a.in_hotlist), 0) AS hotlist_count,
            COALESCE(SUM(CASE WHEN a.ha_sito = 'NO' THEN 1 ELSE 0 END), 0) AS without_site_count
        FROM dataset_runs dr
        LEFT JOIN attivita a ON a.dataset_id = dr.dataset_id
        WHERE dr.dataset_id = ?
        GROUP BY dr.dataset_id
        """,
        (dataset_id,),
    ).fetchone()
    return dict(row) if row else None


def list_datasets(db_path: Path = DB_PATH) -> list[dict]:
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    active_dataset_id = _resolve_dataset_id(conn, None)
    rows = conn.execute(
        """
        SELECT
            dr.dataset_id,
            dr.label,
            dr.province_query,
            dr.reference_query,
            dr.reference_name,
            dr.reference_lat,
            dr.reference_lon,
            dr.source_csv_path,
            dr.created_at,
            dr.updated_at,
            COALESCE(COUNT(a.osm_url), 0) AS lead_count,
            COALESCE(SUM(a.in_hotlist), 0) AS hotlist_count,
            COALESCE(SUM(CASE WHEN a.ha_sito = 'NO' THEN 1 ELSE 0 END), 0) AS without_site_count
        FROM dataset_runs dr
        LEFT JOIN attivita a ON a.dataset_id = dr.dataset_id
        GROUP BY dr.dataset_id
        ORDER BY dr.updated_at DESC, dr.dataset_id DESC
        """
    ).fetchall()
    conn.close()

    datasets = [dict(row) for row in rows]
    for dataset in datasets:
        dataset["is_active"] = dataset["dataset_id"] == active_dataset_id
    return datasets


def import_from_csv(
    osm_csv: Path = DEFAULT_OSM_OUTPUT,
    hotlist_csv: Path = DEFAULT_HOTLIST,
    db_path: Path = DB_PATH,
    *,
    dataset_id: str | None = None,
    dataset_label: str | None = None,
    province_query: str = DEFAULT_PROVINCE_QUERY,
    reference_query: str = DEFAULT_REFERENCE_QUERY,
    reference_name: str | None = None,
    reference_lat: float | None = None,
    reference_lon: float | None = None,
    source_csv_path: str | None = None,
    replace_dataset: bool = True,
) -> int:
    if not osm_csv.exists():
        raise FileNotFoundError(f"CSV base non trovato: {osm_csv}")

    init_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    resolved_dataset_id = dataset_id or dataset_id_from_reference(reference_query)
    resolved_reference_name = reference_name or DEFAULT_REFERENCE_POINT["name"]
    resolved_label = dataset_label or resolved_reference_name
    resolved_reference_lat = (
        reference_lat if reference_lat is not None else DEFAULT_REFERENCE_POINT["lat"]
    )
    resolved_reference_lon = (
        reference_lon if reference_lon is not None else DEFAULT_REFERENCE_POINT["lon"]
    )
    resolved_source_csv = source_csv_path or str(osm_csv)
    now = datetime.now().isoformat()

    existing_scores = {
        row["osm_url"]: (row["rilevanza_score"], row["rilevanza_motivazione"] or "")
        for row in conn.execute(
            """
            SELECT osm_url, rilevanza_score, rilevanza_motivazione
            FROM attivita
            WHERE dataset_id = ?
            """,
            (resolved_dataset_id,),
        ).fetchall()
    }

    hotlist: dict[str, dict] = {}
    if hotlist_csv.exists():
        with hotlist_csv.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                key = _norm(row.get("Nome Attivita", "") or "")
                if key:
                    hotlist[key] = row

    rows = []
    seen_ids: dict[str, int] = {}
    with osm_csv.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            nome = (row.get("Nome Attivita'") or "").strip()
            if not nome:
                continue

            try:
                lat = float(row.get("Lat") or "")
                lon = float(row.get("Lon") or "")
            except (TypeError, ValueError):
                lat = lon = None

            try:
                distanza_km = float(row.get("Distanza da Vedano Olona (km)") or 0)
            except ValueError:
                distanza_km = 0.0

            source_osm_url = (row.get("OSM URL") or "").strip() or nome
            seen_ids[source_osm_url] = seen_ids.get(source_osm_url, 0) + 1
            source_record_id = (
                source_osm_url
                if seen_ids[source_osm_url] == 1
                else f"{source_osm_url}#{seen_ids[source_osm_url]}"
            )
            record_id = f"{resolved_dataset_id}::{source_record_id}"

            hotlist_row = hotlist.get(_norm(nome), {})
            sito = (hotlist_row.get("Sito") or row.get("Sito Web") or "").strip()
            if sito == "N/D":
                sito = ""
            ha_sito = "SI" if sito else "NO"
            rilevanza_score, rilevanza_motivazione = existing_scores.get(record_id, (None, ""))

            rows.append(
                (
                    record_id,
                    nome,
                    lat,
                    lon,
                    (row.get("Priorita'") or "").strip(),
                    distanza_km,
                    (row.get("Categoria") or "").strip(),
                    (row.get("Sottocategoria") or "").strip(),
                    (row.get("Comune") or "").strip(),
                    (row.get("Indirizzo") or "").strip(),
                    (hotlist_row.get("Telefono") or row.get("Telefono") or "").strip(),
                    (hotlist_row.get("Email") or row.get("Email") or "").strip(),
                    sito or "N/D",
                    ha_sito,
                    hotlist_row.get("Stato", ""),
                    hotlist_row.get("Proposta Mirata Base", ""),
                    hotlist_row.get("Criticita", ""),
                    hotlist_row.get("Rating Principale", ""),
                    1 if hotlist_row else 0,
                    rilevanza_score,
                    rilevanza_motivazione,
                    resolved_dataset_id,
                    source_record_id,
                    now,
                )
            )

    if replace_dataset:
        conn.execute("DELETE FROM attivita WHERE dataset_id = ?", (resolved_dataset_id,))

    placeholders = ",".join("?" for _ in ATTIVITA_COLUMNS)
    columns_sql = ", ".join(ATTIVITA_COLUMNS)
    conn.executemany(
        f"INSERT OR REPLACE INTO attivita ({columns_sql}) VALUES ({placeholders})",
        rows,
    )

    existing_dataset = conn.execute(
        """
        SELECT created_at, province_query, source_csv_path, label, reference_query,
               reference_name, reference_lat, reference_lon
        FROM dataset_runs
        WHERE dataset_id = ?
        """,
        (resolved_dataset_id,),
    ).fetchone()
    created_at = existing_dataset["created_at"] if existing_dataset else now
    stored_province_query = province_query
    stored_source_csv = resolved_source_csv
    stored_label = resolved_label
    stored_reference_query = reference_query
    stored_reference_name = resolved_reference_name
    stored_reference_lat = resolved_reference_lat
    stored_reference_lon = resolved_reference_lon
    if existing_dataset and not replace_dataset:
        stored_province_query = _merge_text_values(existing_dataset["province_query"], province_query)
        stored_source_csv = _merge_text_values(existing_dataset["source_csv_path"], resolved_source_csv)
        stored_label = existing_dataset["label"] or resolved_label
        stored_reference_query = existing_dataset["reference_query"] or reference_query
        stored_reference_name = existing_dataset["reference_name"] or resolved_reference_name
        stored_reference_lat = (
            existing_dataset["reference_lat"]
            if existing_dataset["reference_lat"] is not None
            else resolved_reference_lat
        )
        stored_reference_lon = (
            existing_dataset["reference_lon"]
            if existing_dataset["reference_lon"] is not None
            else resolved_reference_lon
        )
    conn.execute(
        """
        INSERT OR REPLACE INTO dataset_runs (
            dataset_id, label, province_query, reference_query, reference_name,
            reference_lat, reference_lon, source_csv_path, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            resolved_dataset_id,
            stored_label,
            stored_province_query,
            stored_reference_query,
            stored_reference_name,
            stored_reference_lat,
            stored_reference_lon,
            stored_source_csv,
            created_at,
            now,
        ),
    )
    conn.commit()

    dataset_count = conn.execute(
        "SELECT COUNT(*) FROM attivita WHERE dataset_id = ?",
        (resolved_dataset_id,),
    ).fetchone()[0]
    in_hotlist = conn.execute(
        "SELECT COUNT(*) FROM attivita WHERE dataset_id = ? AND in_hotlist = 1",
        (resolved_dataset_id,),
    ).fetchone()[0]
    with_coords = conn.execute(
        "SELECT COUNT(*) FROM attivita WHERE dataset_id = ? AND lat IS NOT NULL AND lon IS NOT NULL",
        (resolved_dataset_id,),
    ).fetchone()[0]
    with_scores = conn.execute(
        "SELECT COUNT(*) FROM attivita WHERE dataset_id = ? AND rilevanza_score IS NOT NULL",
        (resolved_dataset_id,),
    ).fetchone()[0]
    conn.close()

    print(
        f"  Importate {dataset_count} attività nel dataset '{resolved_dataset_id}' "
        f"({with_coords} con coordinate, {in_hotlist} in hotlist, {with_scores} con score LLM)"
    )
    return dataset_count


def query_leads(
    priorita: list[str] | None = None,
    categoria: list[str] | None = None,
    solo_senza_sito: bool = False,
    solo_hotlist: bool = False,
    comune: str | None = None,
    limit: int | None = None,
    dataset_id: str | None = None,
    db_path: Path = DB_PATH,
) -> list[dict]:
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    resolved_dataset_id = _resolve_dataset_id(conn, dataset_id)
    if not resolved_dataset_id:
        conn.close()
        return []

    where = ["dataset_id = ?"]
    params: list[object] = [resolved_dataset_id]

    if priorita:
        normalized_priorita = [item.strip().upper() for item in priorita if item and item.strip()]
        if normalized_priorita:
            where.append(f"UPPER(priorita) IN ({','.join('?' * len(normalized_priorita))})")
            params.extend(normalized_priorita)
    if categoria:
        normalized_categorie = [item.strip().lower() for item in categoria if item and item.strip()]
        if normalized_categorie:
            where.append(f"LOWER(categoria) IN ({','.join('?' * len(normalized_categorie))})")
            params.extend(normalized_categorie)
    if solo_senza_sito:
        where.append("ha_sito = 'NO'")
    if solo_hotlist:
        where.append("in_hotlist = 1")
    if comune:
        where.append("LOWER(comune) LIKE ?")
        params.append(f"%{comune.strip().lower()}%")

    sql = "SELECT * FROM attivita WHERE " + " AND ".join(where)
    sql += (
        " ORDER BY CASE priorita"
        " WHEN 'ALTISSIMA' THEN 1"
        " WHEN 'ALTA' THEN 2"
        " WHEN 'MEDIA' THEN 3"
        " WHEN 'BASSA' THEN 4"
        " ELSE 5 END, distanza_km, nome"
    )
    if limit and limit > 0:
        sql += " LIMIT ?"
        params.append(limit)

    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def count_leads(db_path: Path = DB_PATH, dataset_id: str | None = None) -> int:
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    resolved_dataset_id = _resolve_dataset_id(conn, dataset_id)
    if not resolved_dataset_id:
        conn.close()
        return 0
    count = conn.execute(
        "SELECT COUNT(*) FROM attivita WHERE dataset_id = ?",
        (resolved_dataset_id,),
    ).fetchone()[0]
    conn.close()
    return count


def update_rilevanza_score(
    osm_url: str,
    score: int | None,
    motivazione: str = "",
    db_path: Path = DB_PATH,
) -> None:
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        UPDATE attivita
        SET rilevanza_score = ?, rilevanza_motivazione = ?, aggiornato_il = ?
        WHERE osm_url = ?
        """,
        (score, motivazione, datetime.now().isoformat(), osm_url),
    )
    conn.commit()
    conn.close()


def fetch_scoring_candidates(
    limit: int = 100,
    db_path: Path = DB_PATH,
    dataset_id: str | None = None,
) -> list[dict]:
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    resolved_dataset_id = _resolve_dataset_id(conn, dataset_id)
    if not resolved_dataset_id:
        conn.close()
        return []

    rows = conn.execute(
        """
        SELECT osm_url, nome, categoria, comune, priorita, ha_sito, distanza_km, dataset_id
        FROM attivita
        WHERE dataset_id = ?
          AND in_hotlist = 1
          AND priorita IN ('ALTISSIMA', 'ALTA')
        ORDER BY CASE priorita
            WHEN 'ALTISSIMA' THEN 1
            WHEN 'ALTA' THEN 2
            ELSE 3
        END, distanza_km, nome
        LIMIT ?
        """,
        (resolved_dataset_id, limit),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_active_dataset(db_path: Path = DB_PATH, dataset_id: str | None = None) -> dict | None:
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    resolved_dataset_id = _resolve_dataset_id(conn, dataset_id)
    if not resolved_dataset_id:
        conn.close()
        return None
    dataset = _get_dataset_summary(conn, resolved_dataset_id)
    conn.close()
    return dataset


def create_dataset_from_reference(
    reference_query: str,
    *,
    dataset_id: str | None = None,
    province_query: str = DEFAULT_PROVINCE_QUERY,
    limit: int = 0,
    hotlist_csv: Path = DEFAULT_HOTLIST,
    db_path: Path = DB_PATH,
    replace_dataset: bool = True,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict:
    resolved_dataset_id = dataset_id or dataset_id_from_reference(reference_query)
    output_path = ensure_parent_dir(
        OSM_RUNS_DIR / f"{resolved_dataset_id}--{_slugify(province_query)}.csv"
    )

    if dataset_id and not replace_dataset:
        existing_dataset = get_active_dataset(db_path, dataset_id)
        if existing_dataset is None:
            raise RuntimeError(f"Dataset di destinazione non trovato: {dataset_id}")
        if _norm(existing_dataset.get("reference_query") or "") != _norm(reference_query):
            raise RuntimeError(
                "Per unire i risultati devi usare lo stesso centro di distanza del dataset attivo."
            )

    finder = MorpheusFinder(
        province_query=province_query,
        reference_query=reference_query,
        output_file=output_path,
        limit=limit,
        progress_callback=progress_callback,
    )
    finder.run()

    import_from_csv(
        output_path,
        hotlist_csv,
        db_path,
        dataset_id=resolved_dataset_id,
        dataset_label=finder.reference_point["name"],
        province_query=province_query,
        reference_query=reference_query,
        reference_name=finder.reference_point["name"],
        reference_lat=finder.reference_point["lat"],
        reference_lon=finder.reference_point["lon"],
        source_csv_path=str(output_path),
        replace_dataset=replace_dataset,
    )

    dataset = get_active_dataset(db_path, resolved_dataset_id)
    if dataset is None:
        raise RuntimeError(f"Dataset non creato correttamente: {resolved_dataset_id}")
    return dataset
