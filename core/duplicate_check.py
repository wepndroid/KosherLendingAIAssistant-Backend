"""Duplicate prevention — three layers:

1. recent_avoidance() — list of recent (topic, book, framework) tuples for the prompt
2. assess_angle_similarity() — embed the new topic+hook, query last N days for cosine sim
3. log() — record the usage in usage_log AFTER persistence

The angle layer is the new "block at the idea level" rule: if a new generation's angle
embedding is too close to a recent post, we BLOCK it (caller should regenerate)
or flag it as Needs Review.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from db.supabase_client import supabase
from integrations.openai_client import embed_one


# Tunable thresholds (could be moved to brand_config later)
BLOCK_SIMILARITY = 0.92
HIGH_SIMILARITY = 0.85
MEDIUM_SIMILARITY = 0.75
DEFAULT_WINDOW_DAYS = 90
COMBO_BLOCK_WINDOW_DAYS = 45
COMBO_WARN_WINDOW_DAYS = 180


def recent_avoidance(*, pillar: str | None = None, limit: int = 50) -> list[dict]:
    q = supabase().table("usage_log").select(
        "topic,source_book,framework,pillar,platform,state_referenced,created_at"
    ).order("created_at", desc=True).limit(limit)
    if pillar:
        q = q.eq("pillar", pillar)
    return q.execute().data or []


def log(*, content_id: str, content: dict) -> None:
    supabase().table("usage_log").insert(
        {
            "content_id": content_id,
            "topic": content.get("topic"),
            "source_book": content.get("source_book"),
            "framework": content.get("source_framework"),
            "pillar": content.get("pillar"),
            "platform": content.get("platform"),
            "state_referenced": content.get("state_referenced"),
        }
    ).execute()


def angle_text(content: dict) -> str:
    """The text we embed to represent the post's *angle*."""
    return " | ".join(
        s for s in [
            content.get("topic"),
            content.get("hook"),
            content.get("perspective_shift"),
            content.get("source_framework"),
        ] if s
    ).strip()


def embed_angle(content: dict) -> list[float] | None:
    text = angle_text(content)
    if not text:
        return None
    try:
        return embed_one(text)
    except Exception:
        return None


def assess_angle_similarity(angle_embedding: list[float] | None, *, window_days: int = DEFAULT_WINDOW_DAYS) -> dict:
    """Returns {tier, conflicts: [{id, topic, similarity}], should_block: bool}."""
    if not angle_embedding:
        return {"tier": "Low", "conflicts": [], "should_block": False}
    try:
        resp = supabase().rpc(
            "match_angle",
            {
                "query_embedding": angle_embedding,
                "window_days": window_days,
                "match_count": 5,
                "similarity_floor": MEDIUM_SIMILARITY,
            },
        ).execute()
        rows = resp.data or []
    except Exception:
        rows = []

    if not rows:
        return {"tier": "Low", "conflicts": [], "should_block": False}

    top = rows[0]
    sim = float(top.get("similarity") or 0)
    if sim >= BLOCK_SIMILARITY:
        tier = "Block"
        should_block = True
    elif sim >= HIGH_SIMILARITY:
        tier = "High"
        should_block = False
    elif sim >= MEDIUM_SIMILARITY:
        tier = "Medium"
        should_block = False
    else:
        tier = "Low"
        should_block = False

    conflicts = [
        {"id": r.get("id"), "topic": r.get("topic"), "similarity": float(r.get("similarity") or 0)}
        for r in rows
    ]
    return {"tier": tier, "conflicts": conflicts, "should_block": should_block}


def assess_risk(content: dict, avoidance: list[dict]) -> str:
    """Legacy string-match heuristic — kept as a fallback when angle embedding is unavailable."""
    book = (content.get("source_book") or "").lower()
    fw = (content.get("source_framework") or "").lower()
    topic = (content.get("topic") or "").lower()
    high = any(topic and topic == (a.get("topic") or "").lower() for a in avoidance[:30])
    if high:
        return "High"
    medium = any(
        book and book == (a.get("source_book") or "").lower()
        and fw and fw == (a.get("framework") or "").lower()
        for a in avoidance[:20]
    )
    return "Medium" if medium else "Low"


def assess_combo_reuse(
    content: dict,
    *,
    pillar: str | None = None,
    block_window_days: int = COMBO_BLOCK_WINDOW_DAYS,
    warn_window_days: int = COMBO_WARN_WINDOW_DAYS,
    limit: int = 8,
) -> dict:
    """Checks recent re-use of the same source_book + source_framework combination."""
    source_book = _norm(content.get("source_book"))
    source_framework = _norm(content.get("source_framework"))
    if not source_book or not source_framework:
        return {"tier": "Low", "conflicts": [], "should_block": False}

    since_warn = (datetime.now(timezone.utc) - timedelta(days=warn_window_days)).isoformat()
    try:
        q = (
            supabase()
            .table("usage_log")
            .select("content_id,topic,source_book,framework,pillar,created_at")
            .gte("created_at", since_warn)
            .order("created_at", desc=True)
            .limit(500)
        )
        if pillar:
            q = q.eq("pillar", pillar)
        rows = q.execute().data or []
    except Exception:
        rows = []

    matches = [
        r
        for r in rows
        if _norm(r.get("source_book")) == source_book and _norm(r.get("framework")) == source_framework
    ]
    if not matches:
        return {"tier": "Low", "conflicts": [], "should_block": False}

    since_block_dt = datetime.now(timezone.utc) - timedelta(days=block_window_days)
    match_times = [(_parse_ts(r.get("created_at")), r) for r in matches]
    should_block = any(ts and ts >= since_block_dt for ts, _ in match_times)
    tier = "Block" if should_block else "High"
    conflicts = [
        {
            "id": r.get("content_id"),
            "topic": r.get("topic"),
            "source_book": r.get("source_book"),
            "source_framework": r.get("framework"),
            "created_at": r.get("created_at"),
            "reason": "reused_book_framework_combo",
        }
        for r in matches[:limit]
    ]
    return {"tier": tier, "conflicts": conflicts, "should_block": should_block}


def _norm(v: str | None) -> str:
    return (v or "").strip().lower()


def _parse_ts(v: str | None) -> datetime | None:
    if not v:
        return None
    try:
        return datetime.fromisoformat(v.replace("Z", "+00:00"))
    except Exception:
        return None
