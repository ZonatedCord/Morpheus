from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib import error, request

from .db import fetch_scoring_candidates, update_rilevanza_score
from .paths import DB_PATH

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_GENERATE_URL = f"{OLLAMA_BASE_URL}/api/generate"
OLLAMA_TAGS_URL = f"{OLLAMA_BASE_URL}/api/tags"
DEFAULT_MODELS = ("qwen2.5:3b", "gemma2:2b")

_SCORE_RE = re.compile(r"(?<!\d)(10|[0-9])(?!\d)")


@lru_cache(maxsize=1)
def _available_models() -> tuple[str, ...]:
    try:
        req = request.Request(OLLAMA_TAGS_URL, method="GET")
        with request.urlopen(req, timeout=5) as response:
            data = json.load(response)
    except (error.URLError, OSError, ValueError, json.JSONDecodeError):
        return ()

    return tuple(
        model.get("name", "")
        for model in data.get("models", [])
        if model.get("name")
    )


def _resolve_model(requested: str | None = None) -> str | None:
    explicit = (requested or os.environ.get("OLLAMA_MODEL", "")).strip()
    if explicit:
        return explicit

    available = _available_models()
    for candidate in DEFAULT_MODELS:
        if candidate in available:
            return candidate
    return available[0] if available else None


def _build_prompt(lead: dict[str, Any], servizio: str) -> str:
    return (
        f"Attivita: {lead.get('nome', '')}, categoria: {lead.get('categoria', '')}, "
        f"comune: {lead.get('comune', '')}, ha sito: {lead.get('ha_sito', '')}. "
        f"Quanto e rilevante per vendere '{servizio}'? "
        "Rispondi solo con un numero da 0 a 10 nella prima riga e una sola riga di motivazione nella seconda."
    )


def _parse_response(text: str) -> tuple[int | None, str]:
    if not text:
        return None, ""

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    first_line = lines[0] if lines else text.strip()
    match = _SCORE_RE.search(first_line) or _SCORE_RE.search(text)
    score = int(match.group(1)) if match else None

    motivazione = ""
    if len(lines) >= 2:
        motivazione = lines[1]
    elif score is not None and match:
        motivazione = first_line[match.end():].strip(" -:;,")

    return score, motivazione


def score_lead(
    lead: dict[str, Any],
    servizio: str,
    model: str | None = None,
    base_url: str = OLLAMA_GENERATE_URL,
    timeout: int = 60,
) -> dict[str, Any]:
    resolved_model = _resolve_model(model)
    if not resolved_model:
        return {"score": None, "motivazione": ""}

    payload = {
        "model": resolved_model,
        "prompt": _build_prompt(lead, servizio),
        "stream": False,
    }

    try:
        req = request.Request(
            base_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=timeout) as response:
            raw_text = (json.load(response).get("response") or "").strip()
    except (error.URLError, OSError, ValueError, json.JSONDecodeError):
        return {"score": None, "motivazione": ""}

    score, motivazione = _parse_response(raw_text)
    return {"score": score, "motivazione": motivazione}


def score_batch(
    servizio: str,
    limit: int = 100,
    model: str | None = None,
    db_path: Path = DB_PATH,
) -> list[dict[str, Any]]:
    leads = fetch_scoring_candidates(limit=limit, db_path=db_path)
    resolved_model = _resolve_model(model)
    scored: list[dict[str, Any]] = []

    if not resolved_model:
        return [{**lead, "score": None, "motivazione": ""} for lead in leads]

    for lead in leads:
        result = score_lead(lead, servizio=servizio, model=resolved_model)
        score = result["score"]
        motivazione = result["motivazione"]

        scored.append({
            **lead,
            "score": score,
            "motivazione": motivazione,
        })
        if score is not None:
            update_rilevanza_score(
                lead["osm_url"],
                score=score,
                motivazione=motivazione,
                db_path=db_path,
            )

    scored.sort(
        key=lambda lead: (
            -(lead["score"] if lead["score"] is not None else -1),
            lead.get("distanza_km") if lead.get("distanza_km") is not None else 9999,
            lead.get("nome", ""),
        )
    )
    return scored
