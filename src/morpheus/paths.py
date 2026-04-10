from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
INPUT_DIR = DATA_DIR / "input"
OUTPUT_DIR = DATA_DIR / "output"
LINKEDIN_INPUT_DIR = INPUT_DIR / "linkedin"
RESEARCH_INPUT_DIR = INPUT_DIR / "research"
OSM_OUTPUT_DIR = OUTPUT_DIR / "osm"
LINKEDIN_OUTPUT_DIR = OUTPUT_DIR / "linkedin"
OUTREACH_OUTPUT_DIR = OUTPUT_DIR / "outreach"
RESEARCH_OUTPUT_DIR = OUTPUT_DIR / "research"

DEFAULT_LINKEDIN_INPUT = LINKEDIN_INPUT_DIR / "input.txt"
DEFAULT_LINKEDIN_LINKS = LINKEDIN_INPUT_DIR / "linkedin_links.txt"
DEFAULT_OSM_OUTPUT = OSM_OUTPUT_DIR / "clienti_varesotto.csv"
DEFAULT_LINKEDIN_OUTPUT = LINKEDIN_OUTPUT_DIR / "clienti_varesotto_linkedin.csv"
DEFAULT_OUTREACH_INSIGHTS = RESEARCH_INPUT_DIR / "attivita_insights.csv"
DEFAULT_OUTREACH_OUTPUT = OUTREACH_OUTPUT_DIR / "attivita_messaggi_mirati.csv"
DEFAULT_OUTREACH_SUMMARY = OUTREACH_OUTPUT_DIR / "attivita_messaggi_mirati.md"
DEFAULT_COMPANY_RESEARCH_OUTPUT = RESEARCH_OUTPUT_DIR / "attivita_ricerca_online.csv"
DEFAULT_COMPANY_RESEARCH_SUMMARY = RESEARCH_OUTPUT_DIR / "attivita_ricerca_online.md"
DEFAULT_COMPANY_RESEARCH_MERGED_OUTPUT = RESEARCH_OUTPUT_DIR / "attivita_ricerca_online_merged.csv"
DEFAULT_DEEP_RESEARCH_SHORTLIST = RESEARCH_INPUT_DIR / "attivita_shortlist_chatgpt.csv"
DEFAULT_DEEP_RESEARCH_TEMPLATE = RESEARCH_INPUT_DIR / "attivita_shortlist_chatgpt_template.csv"
DEFAULT_DEEP_RESEARCH_SUMMARY = RESEARCH_OUTPUT_DIR / "attivita_shortlist_chatgpt.md"
DEFAULT_SHORTLIST_OUTREACH_READY = RESEARCH_OUTPUT_DIR / "attivita_shortlist_outreach_ready.csv"
DEFAULT_SHORTLIST_OUTREACH_READY_SUMMARY = RESEARCH_OUTPUT_DIR / "attivita_shortlist_outreach_ready.md"
DEFAULT_TOTAL_OUTREACH_READY = RESEARCH_OUTPUT_DIR / "clienti_varesotto_outreach_ready.csv"
DEFAULT_TOTAL_OUTREACH_READY_SUMMARY = RESEARCH_OUTPUT_DIR / "clienti_varesotto_outreach_ready.md"
DEFAULT_HOTLIST = RESEARCH_OUTPUT_DIR / "clienti_varesotto_outreach_hotlist.csv"

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
