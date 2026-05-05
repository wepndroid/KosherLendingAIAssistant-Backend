"""GoHighLevel CRM bridge.

Outbound: schedule social posts and DM workflows.
Inbound: handle webhook from GHL when a follower DMs a keyword (handled in api/webhooks.py).
"""
import httpx
from config import get_settings


BASE = "https://services.leadconnectorhq.com"


def _headers() -> dict[str, str]:
    s = get_settings()
    if not s.GHL_API_KEY:
        raise RuntimeError("GHL_API_KEY not set")
    return {
        "Authorization": f"Bearer {s.GHL_API_KEY}",
        "Version": "2021-07-28",
        "Content-Type": "application/json",
    }


async def schedule_post(*, content_id: str, platform: str, caption: str, scheduled_for_iso: str) -> dict:
    """Push a scheduled social post to GHL. Returns GHL response (empty dict if not configured)."""
    s = get_settings()
    if not s.GHL_API_KEY:
        return {"skipped": True, "reason": "GHL not configured"}
    payload = {
        "locationId": s.GHL_LOCATION_ID,
        "platform": platform,
        "content": caption,
        "scheduledAt": scheduled_for_iso,
        "metadata": {"content_id": content_id},
    }
    async with httpx.AsyncClient(timeout=30) as http:
        r = await http.post(f"{BASE}/social-media/posts/", headers=_headers(), json=payload)
        r.raise_for_status()
        return r.json()


async def fire_keyword_workflow(*, contact_id: str, workflow_id: str) -> dict:
    s = get_settings()
    if not s.GHL_API_KEY:
        return {"skipped": True}
    async with httpx.AsyncClient(timeout=30) as http:
        r = await http.post(
            f"{BASE}/contacts/{contact_id}/workflow/{workflow_id}",
            headers=_headers(),
        )
        r.raise_for_status()
        return r.json()
