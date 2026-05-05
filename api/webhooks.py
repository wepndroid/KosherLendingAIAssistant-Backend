"""Webhook receivers — primarily GHL DM keyword triggers."""
import hmac
import hashlib
from fastapi import APIRouter, Header, HTTPException, Request

from config import get_settings
from db.supabase_client import supabase

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


@router.post("/ghl")
async def ghl_inbound(request: Request, x_signature: str | None = Header(default=None)):
    body = await request.body()
    s = get_settings()
    if s.GHL_WEBHOOK_SECRET:
        expected = hmac.new(s.GHL_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
        if not x_signature or not hmac.compare_digest(expected, x_signature):
            raise HTTPException(401, "Bad signature")

    payload = await request.json()
    keyword = (payload.get("keyword") or payload.get("message") or "").strip().upper()
    contact_id = payload.get("contact_id") or payload.get("contactId")
    if not keyword:
        return {"ok": False, "reason": "no keyword"}

    db = supabase()
    rows = db.table("dm_keywords").select("*,dm_deliverables(*)").eq("keyword", keyword).limit(1).execute().data
    if not rows:
        return {"ok": False, "reason": f"unknown keyword {keyword}"}

    kw = rows[0]
    db.table("dm_keywords").update(
        {"usage_count": (kw.get("usage_count") or 0) + 1, "last_used": "now()"}
    ).eq("keyword", keyword).execute()
    db.table("activity_log").insert({"text": f"DM keyword fired: {keyword}", "icon": "key"}).execute()

    deliverable = (kw.get("dm_deliverables") or {}) if isinstance(kw.get("dm_deliverables"), dict) else None
    return {
        "ok": True,
        "keyword": keyword,
        "contact_id": contact_id,
        "deliverable": deliverable or {"keyword": keyword},
    }
