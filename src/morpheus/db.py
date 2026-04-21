from __future__ import annotations

import csv
import io
import math
import re
import sqlite3
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Generator
from uuid import uuid4

from .paths import (
    DB_PATH,
    DEFAULT_HOTLIST,
    DEFAULT_OSM_OUTPUT,
    OSM_RUNS_DIR,
    ensure_parent_dir,
)
from .osm_finder import (
    DEFAULT_PROVINCE_QUERY,
    DEFAULT_REFERENCE_POINT,
    DEFAULT_REFERENCE_QUERY,
    MorpheusFinder,
)

JOBS_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id      TEXT PRIMARY KEY,
    job_type    TEXT NOT NULL DEFAULT 'populate',
    status      TEXT NOT NULL DEFAULT 'queued',
    progress    INTEGER DEFAULT 0,
    stage       TEXT DEFAULT '',
    message     TEXT DEFAULT '',
    error       TEXT DEFAULT '',
    dataset_id  TEXT DEFAULT '',
    result_json TEXT DEFAULT '',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
"""

INDEXES_SQL = """
CREATE INDEX IF NOT EXISTS idx_attivita_dataset ON attivita(dataset_id);
CREATE INDEX IF NOT EXISTS idx_attivita_dataset_priorita ON attivita(dataset_id, priorita);
CREATE INDEX IF NOT EXISTS idx_attivita_dataset_comune ON attivita(dataset_id, comune);
CREATE INDEX IF NOT EXISTS idx_attivita_dataset_facebook ON attivita(dataset_id, facebook_url);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
"""

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
    facebook_url          TEXT DEFAULT '',
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
    "facebook_url",
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
    "facebook_url": "ALTER TABLE attivita ADD COLUMN facebook_url TEXT DEFAULT ''",
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


def _clean_merge_value(value: str | None) -> str:
    cleaned = str(value or "").strip()
    return "" if cleaned in {"", "N/D"} else cleaned


def _norm_dedup(nome: str, lat: float | None, lon: float | None) -> tuple:
    return (
        _slugify(nome),
        round(lat, 3) if lat is not None else None,
        round(lon, 3) if lon is not None else None,
    )


def _merge_distinct_values(existing: str | None, new_value: str | None) -> str:
    values: list[str] = []
    for raw_value in (existing, new_value):
        for item in str(raw_value or "").split(" | "):
            cleaned = _clean_merge_value(item)
            if cleaned and cleaned not in values:
                values.append(cleaned)
    return " | ".join(values)


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
    conn.executescript(JOBS_SCHEMA)
    conn.executescript(INDEXES_SQL)
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

    existing_fingerprints: set[tuple] = set()
    if not replace_dataset:
        existing_fingerprints = {
            _norm_dedup(r[0], r[1], r[2])
            for r in conn.execute(
                "SELECT nome, lat, lon FROM attivita WHERE dataset_id = ? AND lat IS NOT NULL AND lon IS NOT NULL",
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
    seen_in_batch: set[tuple] = set()
    skipped_dedup = 0
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

            fp = _norm_dedup(nome, lat, lon)
            if fp in existing_fingerprints or fp in seen_in_batch:
                skipped_dedup += 1
                continue
            if lat is not None and lon is not None:
                seen_in_batch.add(fp)

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
                    "",
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

    dedup_msg = f", {skipped_dedup} duplicati saltati" if skipped_dedup else ""
    print(
        f"  Importate {dataset_count} attività nel dataset '{resolved_dataset_id}' "
        f"({with_coords} con coordinate, {in_hotlist} in hotlist, {with_scores} con score LLM{dedup_msg})"
    )
    return dataset_count


def query_leads(
    priorita: list[str] | None = None,
    categoria: list[str] | None = None,
    solo_senza_sito: bool = False,
    solo_hotlist: bool = False,
    comune: str | None = None,
    limit: int | None = None,
    offset: int = 0,
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
        if offset and offset > 0:
            sql += " OFFSET ?"
            params.append(offset)

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


def merge_lead_enrichment(
    osm_url: str,
    *,
    telefono: str = "",
    email: str = "",
    sito: str = "",
    facebook_url: str = "",
    db_path: Path = DB_PATH,
) -> dict | None:
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        """
        SELECT osm_url, dataset_id, telefono, email, sito, facebook_url, ha_sito
        FROM attivita
        WHERE osm_url = ?
        """,
        (osm_url,),
    ).fetchone()
    if row is None:
        conn.close()
        return None

    merged_phone = _merge_distinct_values(row["telefono"], telefono)
    merged_email = _merge_distinct_values(row["email"], email)
    merged_site = _merge_distinct_values(row["sito"], sito)
    merged_facebook = _merge_distinct_values(row["facebook_url"], facebook_url)
    ha_sito = "SI" if merged_site else "NO"
    updated_at = datetime.now().isoformat()

    conn.execute(
        """
        UPDATE attivita
        SET telefono = ?,
            email = ?,
            sito = ?,
            facebook_url = ?,
            ha_sito = ?,
            aggiornato_il = ?
        WHERE osm_url = ?
        """,
        (
            merged_phone or "N/D",
            merged_email or "N/D",
            merged_site or "N/D",
            merged_facebook,
            ha_sito,
            updated_at,
            osm_url,
        ),
    )
    conn.commit()
    conn.close()
    return {
        "osm_url": osm_url,
        "dataset_id": row["dataset_id"] or "",
        "telefono": merged_phone,
        "email": merged_email,
        "sito": merged_site,
        "facebook_url": merged_facebook,
        "ha_sito": ha_sito,
    }


def touch_dataset(dataset_id: str, db_path: Path = DB_PATH) -> None:
    if not dataset_id:
        return
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE dataset_runs SET updated_at = ? WHERE dataset_id = ?",
        (datetime.now().isoformat(), dataset_id),
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


def save_job(
    job_id: str,
    payload: dict,
    *,
    job_type: str = "populate",
    db_path: Path = DB_PATH,
) -> None:
    """Upsert a job record; merges payload over existing state."""
    init_db(db_path)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    now = datetime.now().isoformat()
    existing = conn.execute(
        "SELECT * FROM jobs WHERE job_id = ?", (job_id,)
    ).fetchone()
    if existing:
        base = dict(existing)
    else:
        base = {
            "job_id": job_id,
            "job_type": job_type,
            "status": "queued",
            "progress": 0,
            "stage": "",
            "message": "",
            "error": "",
            "dataset_id": "",
            "result_json": "",
            "created_at": now,
        }
    for key, value in payload.items():
        if key in base and value is not None:
            if key == "result_json" and not isinstance(value, str):
                import json as _json
                base[key] = _json.dumps(value)
            else:
                base[key] = value
    base["updated_at"] = now
    conn.execute(
        """
        INSERT OR REPLACE INTO jobs
          (job_id, job_type, status, progress, stage, message, error,
           dataset_id, result_json, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            base["job_id"],
            base.get("job_type", job_type),
            base["status"],
            base.get("progress", 0),
            base.get("stage", ""),
            base.get("message", ""),
            base.get("error", ""),
            base.get("dataset_id", ""),
            base.get("result_json", ""),
            base["created_at"],
            base["updated_at"],
        ),
    )
    conn.commit()
    conn.close()


def get_job(job_id: str, db_path: Path = DB_PATH) -> dict | None:
    """Return a job record as dict, or None if not found."""
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
    conn.close()
    if row is None:
        return None
    result = dict(row)
    if result.get("result_json"):
        import json as _json
        try:
            result["_result"] = _json.loads(result["result_json"])
        except Exception:
            result["_result"] = {}
    return result


def mark_stale_jobs(db_path: Path = DB_PATH) -> None:
    """Mark jobs that were running/queued at shutdown as interrupted."""
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        UPDATE jobs
        SET status = 'interrupted',
            message = 'Il server si è riavviato mentre il job era in esecuzione.',
            updated_at = ?
        WHERE status IN ('running', 'queued')
        """,
        (datetime.now().isoformat(),),
    )
    conn.commit()
    conn.close()


def fetch_facebook_candidates(
    dataset_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db_path: Path = DB_PATH,
) -> list[dict]:
    """Return leads without a facebook_url for enrichment."""
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    resolved_dataset_id = _resolve_dataset_id(conn, dataset_id)
    if not resolved_dataset_id:
        conn.close()
        return []
    rows = conn.execute(
        """
        SELECT osm_url, nome, comune, categoria, sottocategoria
        FROM attivita
        WHERE dataset_id = ?
          AND (facebook_url IS NULL OR facebook_url = '')
        ORDER BY CASE priorita
          WHEN 'ALTISSIMA' THEN 1
          WHEN 'ALTA' THEN 2
          WHEN 'MEDIA' THEN 3
          WHEN 'BASSA' THEN 4
          ELSE 5 END, distanza_km, nome
        LIMIT ? OFFSET ?
        """,
        (resolved_dataset_id, limit, offset),
    ).fetchall()
    total = conn.execute(
        """
        SELECT COUNT(*) FROM attivita
        WHERE dataset_id = ?
          AND (facebook_url IS NULL OR facebook_url = '')
        """,
        (resolved_dataset_id,),
    ).fetchone()[0]
    conn.close()
    return [dict(r) | {"_total_candidates": total} for r in rows]


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


# ── Lead editing ──────────────────────────────────────────────────────────────

_LEAD_EDITABLE_FIELDS = {
    "stato",
    "proposta",
    "rating",
    "in_hotlist",
    "email",
    "telefono",
    "sito",
    "criticita",
}


def update_lead_fields(
    osm_url: str,
    updates: dict[str, Any],
    db_path: Path = DB_PATH,
) -> dict | None:
    """Partial update of editable fields on a single lead.

    Only keys present in *updates* AND in the whitelist are written.
    Recomputes ``ha_sito`` when ``sito`` is changed.
    Returns the full updated row as a dict, or ``None`` if the lead was not found.
    """
    allowed = {k: v for k, v in updates.items() if k in _LEAD_EDITABLE_FIELDS and v is not None}
    if not allowed:
        # Nothing to update — still return the current row so caller gets a 200.
        init_db(db_path)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM attivita WHERE osm_url = ?", (osm_url,)).fetchone()
        conn.close()
        return dict(row) if row else None

    init_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    row = conn.execute("SELECT * FROM attivita WHERE osm_url = ?", (osm_url,)).fetchone()
    if row is None:
        conn.close()
        return None

    # Normalise special values
    if "in_hotlist" in allowed:
        allowed["in_hotlist"] = 1 if allowed["in_hotlist"] else 0
    if "sito" in allowed:
        sito_val = str(allowed["sito"]).strip()
        allowed["sito"] = sito_val or "N/D"
        allowed["ha_sito"] = "SI" if sito_val and sito_val != "N/D" else "NO"

    allowed["aggiornato_il"] = datetime.now().isoformat()

    set_clause = ", ".join(f"{col} = ?" for col in allowed)
    values = list(allowed.values()) + [osm_url]
    conn.execute(f"UPDATE attivita SET {set_clause} WHERE osm_url = ?", values)
    conn.commit()

    updated = conn.execute("SELECT * FROM attivita WHERE osm_url = ?", (osm_url,)).fetchone()
    conn.close()
    return dict(updated) if updated else None


def update_leads_bulk(
    osm_urls: list[str],
    updates: dict[str, Any],
    db_path: Path = DB_PATH,
) -> int:
    """Update a set of leads with the same field values. Returns count of rows updated."""
    allowed = {k: v for k, v in updates.items() if k in _LEAD_EDITABLE_FIELDS and v is not None}
    if not allowed or not osm_urls:
        return 0

    if "in_hotlist" in allowed:
        allowed["in_hotlist"] = 1 if allowed["in_hotlist"] else 0
    if "sito" in allowed:
        sito_val = str(allowed["sito"]).strip()
        allowed["sito"] = sito_val or "N/D"
        allowed["ha_sito"] = "SI" if sito_val and sito_val != "N/D" else "NO"

    allowed["aggiornato_il"] = datetime.now().isoformat()

    init_db(db_path)
    conn = sqlite3.connect(db_path)
    set_clause = ", ".join(f"{col} = ?" for col in allowed)
    placeholders = ",".join("?" * len(osm_urls))
    values = list(allowed.values()) + list(osm_urls)
    cursor = conn.execute(
        f"UPDATE attivita SET {set_clause} WHERE osm_url IN ({placeholders})",
        values,
    )
    count = cursor.rowcount
    conn.commit()
    conn.close()
    return count


# ── Dataset deletion ───────────────────────────────────────────────────────────

def delete_dataset(
    dataset_id: str,
    db_path: Path = DB_PATH,
) -> dict:
    """Delete a dataset and all its leads. Returns counts."""
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    lead_count = conn.execute(
        "SELECT COUNT(*) FROM attivita WHERE dataset_id = ?", (dataset_id,)
    ).fetchone()[0]
    conn.execute("DELETE FROM attivita WHERE dataset_id = ?", (dataset_id,))
    conn.execute("DELETE FROM dataset_runs WHERE dataset_id = ?", (dataset_id,))
    conn.commit()
    conn.close()
    return {"dataset_id": dataset_id, "deleted_leads": lead_count}


# ── Manual lead creation ──────────────────────────────────────────────────────

def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    return round(r * 2 * math.asin(math.sqrt(a)), 2)


def _score_to_priority(score: float) -> str:
    if score >= 0.75:
        return "ALTISSIMA"
    if score >= 0.55:
        return "ALTA"
    if score >= 0.35:
        return "MEDIA"
    if score >= 0.20:
        return "BASSA"
    return "MOLTO BASSA"


def create_manual_lead(
    dataset_id: str,
    fields: dict[str, Any],
    db_path: Path = DB_PATH,
) -> dict | None:
    """Insert a manually-entered lead into the given dataset.

    Returns the full row as dict, or None if dataset not found or nome missing.
    """
    nome = (fields.get("nome") or "").strip()
    if not nome:
        return None

    init_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    dataset_row = conn.execute(
        "SELECT reference_lat, reference_lon FROM dataset_runs WHERE dataset_id = ?",
        (dataset_id,),
    ).fetchone()
    if dataset_row is None:
        conn.close()
        return None

    ref_lat = dataset_row["reference_lat"]
    ref_lon = dataset_row["reference_lon"]

    try:
        lat = float(fields["lat"]) if fields.get("lat") not in (None, "") else None
        lon = float(fields["lon"]) if fields.get("lon") not in (None, "") else None
    except (TypeError, ValueError):
        lat = lon = None

    sito = (fields.get("sito") or "").strip()
    if sito == "N/D":
        sito = ""
    ha_sito = "SI" if sito else "NO"

    distanza_km = 0.0
    priorita = "BASSA"
    if lat is not None and lon is not None and ref_lat is not None and ref_lon is not None:
        distanza_km = _haversine_km(ref_lat, ref_lon, lat, lon)
        max_dist = 50.0
        dist_norm = max(0.0, 1.0 - distanza_km / max_dist)
        assenza_sito = 1.0 if ha_sito == "NO" else 0.0
        score = 0.5 * dist_norm + 0.3 * assenza_sito
        priorita = _score_to_priority(score)

    osm_url = f"manual://{uuid4().hex}"
    now = datetime.now().isoformat()

    conn.execute(
        """
        INSERT INTO attivita (
            osm_url, nome, lat, lon, priorita, distanza_km, categoria,
            sottocategoria, comune, indirizzo, telefono, email, sito,
            facebook_url, ha_sito, stato, proposta, criticita, rating,
            in_hotlist, rilevanza_score, rilevanza_motivazione,
            dataset_id, source_osm_url, aggiornato_il
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            osm_url, nome, lat, lon, priorita, distanza_km,
            (fields.get("categoria") or "").strip(),
            "",
            (fields.get("comune") or "").strip(),
            (fields.get("indirizzo") or "").strip(),
            (fields.get("telefono") or "").strip(),
            (fields.get("email") or "").strip(),
            sito or "N/D",
            (fields.get("facebook_url") or "").strip(),
            ha_sito,
            "", "", "", "", 0, None, "",
            dataset_id, "manual", now,
        ),
    )
    conn.commit()

    row = conn.execute("SELECT * FROM attivita WHERE osm_url = ?", (osm_url,)).fetchone()
    conn.close()
    return dict(row) if row else None


# ── Distinct comuni ────────────────────────────────────────────────────────────

def list_comuni(
    dataset_id: str | None = None,
    db_path: Path = DB_PATH,
) -> list[str]:
    """Return sorted distinct *comune* values for a dataset (or the active one)."""
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    resolved = _resolve_dataset_id(conn, dataset_id)
    if not resolved:
        conn.close()
        return []
    rows = conn.execute(
        """
        SELECT DISTINCT comune FROM attivita
        WHERE dataset_id = ? AND comune IS NOT NULL AND comune != '' AND comune != 'N/D'
        ORDER BY comune
        """,
        (resolved,),
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


# ── CSV export ─────────────────────────────────────────────────────────────────

_EXPORT_COLUMNS = (
    "nome",
    "comune",
    "categoria",
    "sottocategoria",
    "indirizzo",
    "telefono",
    "email",
    "sito",
    "facebook_url",
    "priorita",
    "distanza_km",
    "ha_sito",
    "stato",
    "proposta",
    "rating",
)


def export_leads_csv(
    dataset_id: str | None = None,
    *,
    priorita: list[str] | None = None,
    categoria: list[str] | None = None,
    solo_senza_sito: bool = False,
    solo_hotlist: bool = False,
    comune: str | None = None,
    db_path: Path = DB_PATH,
) -> Generator[str, None, None]:
    """Yield CSV rows (header + data) for the filtered leads."""
    leads = query_leads(
        priorita=priorita,
        categoria=categoria,
        solo_senza_sito=solo_senza_sito,
        solo_hotlist=solo_hotlist,
        comune=comune,
        limit=50_000,
        dataset_id=dataset_id,
        db_path=db_path,
    )

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_EXPORT_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    yield buf.getvalue()
    buf.seek(0)
    buf.truncate(0)

    for lead in leads:
        row = {col: lead.get(col, "") or "" for col in _EXPORT_COLUMNS}
        if "distanza_km" in row and row["distanza_km"]:
            try:
                row["distanza_km"] = f"{float(row['distanza_km']):.2f}"
            except (TypeError, ValueError):
                pass
        writer.writerow(row)
        yield buf.getvalue()
        buf.seek(0)
        buf.truncate(0)
