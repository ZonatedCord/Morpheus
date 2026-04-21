from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = DATA_DIR / "output"
OSM_OUTPUT_DIR = OUTPUT_DIR / "osm"
OSM_RUNS_DIR = OSM_OUTPUT_DIR / "runs"
RESEARCH_OUTPUT_DIR = OUTPUT_DIR / "research"

DEFAULT_OSM_OUTPUT = OSM_OUTPUT_DIR / "morpheus_leads.csv"
DEFAULT_HOTLIST = RESEARCH_OUTPUT_DIR / "morpheus_hotlist.csv"

DB_PATH = DATA_DIR / "leads.db"


def ensure_parent_dir(path: str | Path) -> Path:
    resolved = Path(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved


def project_relative(path: str | Path) -> str:
    candidate = Path(path)
    normalized = candidate if candidate.is_absolute() else PROJECT_ROOT / candidate
    try:
        return str(normalized.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(candidate)
