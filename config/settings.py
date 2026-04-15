"""Central configuration. Reads from env + JSON stores under config/."""
from __future__ import annotations
import json
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
CHROMA_DIR = DATA_DIR / "chroma"
LOG_DIR = DATA_DIR / "logs"
KEYWORDS_FILE = ROOT / "config" / "keywords.json"
USER_SETTINGS_FILE = ROOT / "config" / "user_settings.json"

for d in (RAW_DIR, CHROMA_DIR, LOG_DIR):
    d.mkdir(parents=True, exist_ok=True)

# ---- Verified Gemini free-tier models (April 2026) ----
MODEL_LITE = "gemini-2.5-flash-lite"   # 15 RPM · 1000 RPD
MODEL_FLASH = "gemini-2.5-flash"       # 10 RPM · 250 RPD
EMBEDDING_MODEL = "text-embedding-004"

# All source feed IDs the project knows about (id → human label).
FEED_CATALOG: dict[str, str] = {
    "arxiv_cs_ai": "arXiv cs.AI",
    "simonw": "Simon Willison's blog",
    "hf_papers": "Hugging Face daily papers",
    "hn": "Hacker News front page",
}

DEFAULT_USER_SETTINGS: dict = {
    "routing": {
        "simple_model": MODEL_LITE,
        "complex_model": MODEL_FLASH,
        "downgrade_on_429": True,
    },
    "feeds": {fid: True for fid in FEED_CATALOG},
    # per-source keyword override (empty list → use global keywords.json)
    "feed_keywords": {fid: [] for fid in FEED_CATALOG},
}


# ---------- API key ----------
def get_api_key() -> str:
    return os.getenv("GOOGLE_API_KEY", "")


# ---------- Global keywords ----------
def load_keywords() -> list[str]:
    if not KEYWORDS_FILE.exists():
        KEYWORDS_FILE.write_text(json.dumps(
            ["LLM agents", "RAG", "LangGraph", "Gemini", "fine-tuning"],
            indent=2))
    return json.loads(KEYWORDS_FILE.read_text())


def save_keywords(keywords: list[str]) -> None:
    KEYWORDS_FILE.write_text(json.dumps(keywords, indent=2, ensure_ascii=False))


# ---------- User settings (routing + feeds + per-source keywords) ----------
def load_user_settings() -> dict:
    if not USER_SETTINGS_FILE.exists():
        save_user_settings(DEFAULT_USER_SETTINGS)
        return json.loads(json.dumps(DEFAULT_USER_SETTINGS))
    try:
        data = json.loads(USER_SETTINGS_FILE.read_text())
    except Exception:
        return json.loads(json.dumps(DEFAULT_USER_SETTINGS))
    # Merge to tolerate new fields added in code
    merged = json.loads(json.dumps(DEFAULT_USER_SETTINGS))
    for section, val in (data or {}).items():
        if isinstance(val, dict) and isinstance(merged.get(section), dict):
            merged[section].update(val)
        else:
            merged[section] = val
    # Heal: ensure every known feed has entries
    for fid in FEED_CATALOG:
        merged["feeds"].setdefault(fid, True)
        merged["feed_keywords"].setdefault(fid, [])
    return merged


def save_user_settings(settings: dict) -> None:
    USER_SETTINGS_FILE.write_text(
        json.dumps(settings, indent=2, ensure_ascii=False))


def get_routing() -> dict:
    return load_user_settings().get("routing", DEFAULT_USER_SETTINGS["routing"])


def enabled_feeds() -> dict[str, bool]:
    return load_user_settings().get("feeds", {fid: True for fid in FEED_CATALOG})


def feed_keywords(feed_id: str) -> list[str]:
    return load_user_settings().get("feed_keywords", {}).get(feed_id, [])
