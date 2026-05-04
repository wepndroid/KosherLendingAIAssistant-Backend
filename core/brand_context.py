"""Loads and caches brand_config from Supabase. Falls back to env defaults."""
from __future__ import annotations
from typing import Any
from ..config import get_settings
from ..db.supabase_client import supabase


_DEFAULT_PILLARS = [
    {"name": "Psychology & Behavioral Economics", "books": ["Kahneman","Cialdini","Ariely","Thaler","Duhigg","Gladwell"]},
    {"name": "Negotiation Tactics", "books": ["Voss","Camp","Keld Jensen","Fisher"]},
    {"name": "Jefferson Fisher Communication", "books": ["Jefferson Fisher"]},
    {"name": "Geographic Market Intelligence", "books": []},
    {"name": "Financing Strategy", "books": []},
    {"name": "Wealth & Life Philosophy", "books": ["Housel","Kiyosaki","Stanley","Clear"]},
    {"name": "Myth-Bust / Story", "books": []},
]

_DEFAULT_CTAS = [
    {"name": "DIRECT_OFFER", "pillars": ["Psychology","Negotiation"]},
    {"name": "CURIOSITY_GAP", "pillars": ["Psychology","Behavioral Econ"]},
    {"name": "CHALLENGE", "pillars": ["Financing","Myth-Bust"]},
    {"name": "COMMUNITY_ENTRY", "pillars": ["Wealth & Life"]},
    {"name": "STORY_CONTINUATION", "pillars": ["Negotiation"]},
    {"name": "DECISION_TOOL", "pillars": ["Geographic","Fisher"]},
]

_DEFAULT_WINDOWS = [
    {"slot": "06:00", "pillars": ["Psychology","Wealth"]},
    {"slot": "09:00", "pillars": ["Negotiation","Geographic"]},
    {"slot": "12:00", "pillars": ["Fisher","Financing"]},
    {"slot": "15:00", "pillars": ["Psychology","Myth-Bust"]},
    {"slot": "18:00", "pillars": ["Negotiation","Fisher"]},
    {"slot": "21:00", "pillars": ["Wealth","Financing"]},
]


_cache: dict[str, Any] | None = None


def load(force: bool = False) -> dict[str, Any]:
    global _cache
    if _cache and not force:
        return _cache
    s = get_settings()
    cfg = _from_env(s)
    try:
        rows = supabase().table("brand_config").select("*").limit(1).execute().data
        if rows:
            r = rows[0]
            cfg.update({k: v for k, v in r.items() if v is not None})
    except Exception:
        pass
    _cache = cfg
    return cfg


def upsert(updates: dict[str, Any]) -> dict[str, Any]:
    rows = supabase().table("brand_config").select("id").limit(1).execute().data
    if rows:
        supabase().table("brand_config").update(updates).eq("id", rows[0]["id"]).execute()
    else:
        supabase().table("brand_config").insert(updates).execute()
    return load(force=True)


def _from_env(s) -> dict[str, Any]:
    return {
        "brand_name": s.BRAND_NAME,
        "product_name": "AI Content OS",
        "creator_name": s.BRAND_CREATOR,
        "nmls": s.BRAND_NMLS,
        "website": s.BRAND_WEBSITE,
        "voice_description": "Authoritative, educational, direct, research-backed, practical",
        "compliance_footer": s.BRAND_COMPLIANCE,
        "excluded_states": s.excluded_states_list,
        "licensed_states": [],
        "pillars": _DEFAULT_PILLARS,
        "cta_structures": _DEFAULT_CTAS,
        "posting_windows": _DEFAULT_WINDOWS,
    }
