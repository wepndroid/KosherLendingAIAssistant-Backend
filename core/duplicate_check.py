"""Tracks which topic/book/framework combinations have been used to keep output fresh."""
from ..db.supabase_client import supabase


def recent_avoidance(*, pillar: str | None = None, limit: int = 50) -> list[dict]:
    q = supabase().table("usage_log").select("topic,source_book,framework,pillar,platform,state_referenced,created_at").order("created_at", desc=True).limit(limit)
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


def assess_risk(content: dict, avoidance: list[dict]) -> str:
    """Heuristic: same book+framework already used recently → Medium. Same topic → High."""
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
