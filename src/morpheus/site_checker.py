from __future__ import annotations

import concurrent.futures
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import requests

from .paths import DB_PATH

_REQUEST_TIMEOUT = 6
_WORKERS = 12
_DEAD_STATUSES = {404, 410, 451}
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; Morpheus/1.0; site-checker)"}


def _check_url(url: str) -> str:
    """Returns 'SI' if reachable, 'MORTO' otherwise."""
    if not url or url in ("N/D", ""):
        return "NO"
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        resp = requests.head(url, timeout=_REQUEST_TIMEOUT, headers=_HEADERS, allow_redirects=True)
        if resp.status_code in _DEAD_STATUSES:
            return "MORTO"
        if resp.status_code >= 400:
            # Some servers reject HEAD — try GET
            resp2 = requests.get(url, timeout=_REQUEST_TIMEOUT, headers=_HEADERS, stream=True)
            resp2.close()
            if resp2.status_code in _DEAD_STATUSES or resp2.status_code >= 400:
                return "MORTO"
        return "SI"
    except Exception:
        return "MORTO"


def _update_ha_sito(osm_url: str, value: str, db_path: Path) -> None:
    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE attivita SET ha_sito = ?, aggiornato_il = ? WHERE osm_url = ?",
        (value, datetime.now().isoformat(), osm_url),
    )
    conn.commit()
    conn.close()


def check_sites_batch(
    dataset_id: str | None = None,
    db_path: Path = DB_PATH,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict:
    import sqlite3
    from .db import _resolve_dataset_id, init_db

    init_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    resolved = _resolve_dataset_id(conn, dataset_id)
    if not resolved:
        conn.close()
        return {"checked": 0, "dead": 0, "total": 0}

    rows = conn.execute(
        """
        SELECT osm_url, sito FROM attivita
        WHERE dataset_id = ? AND ha_sito = 'SI'
          AND sito IS NOT NULL AND sito != '' AND sito != 'N/D'
        """,
        (resolved,),
    ).fetchall()
    conn.close()

    candidates = [dict(r) for r in rows]
    total = len(candidates)
    if total == 0:
        return {"checked": 0, "dead": 0, "total": 0}

    checked = 0
    dead = 0
    lock = threading.Lock()

    def process(row: dict) -> None:
        nonlocal checked, dead
        result = _check_url(row["sito"])
        with lock:
            checked += 1
            if result == "MORTO":
                dead += 1
                _update_ha_sito(row["osm_url"], "MORTO", db_path)
            if progress_callback:
                progress_callback({
                    "progress": int(checked / total * 100),
                    "stage": "checking",
                    "message": f"Verificati {checked}/{total} · {dead} non raggiungibili",
                })

    with concurrent.futures.ThreadPoolExecutor(max_workers=_WORKERS) as pool:
        pool.map(process, candidates)

    return {"checked": checked, "dead": dead, "total": total}
