from fastapi import APIRouter, Depends
from collections import Counter

from ..db.supabase_client import supabase
from .auth import optional_user

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("")
def stats(_user=Depends(optional_user)):
    db = supabase()
    docs = db.table("knowledge_documents").select("status").execute().data or []
    content = db.table("generated_content").select("status,pillar,platform").execute().data or []
    keywords = db.table("dm_keywords").select("usage_count,ghl_status,keyword").execute().data or []
    activity = db.table("activity_log").select("*").order("created_at", desc=True).limit(8).execute().data or []
    queue = db.table("posting_queue").select("status").execute().data or []

    docs_status = Counter(d["status"] for d in docs)
    content_status = Counter(c["status"] for c in content)
    pillars = Counter(c["pillar"] for c in content if c.get("pillar"))
    platforms = Counter(c["platform"] for c in content if c.get("platform"))
    queue_status = Counter(q["status"] for q in queue)

    return {
        "knowledge": {
            "total": len(docs),
            "indexed": docs_status.get("Indexed", 0),
            "processing": docs_status.get("Processing", 0),
            "failed": docs_status.get("Failed", 0),
        },
        "content": {
            "total": len(content),
            "by_status": dict(content_status),
            "by_pillar": dict(pillars),
            "by_platform": dict(platforms),
        },
        "keywords": {
            "total": len(keywords),
            "active": sum(1 for k in keywords if k.get("ghl_status") == "Ready"),
            "top": sorted(keywords, key=lambda k: k.get("usage_count") or 0, reverse=True)[:5],
        },
        "queue": dict(queue_status),
        "activity": activity,
    }
