from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..db.supabase_client import supabase
from .auth import optional_user

router = APIRouter(prefix="/api/content", tags=["content"])


@router.get("")
def list_content(
    status: str | None = Query(None, description="Comma-separated statuses"),
    pillar: str | None = None,
    platform: str | None = None,
    limit: int = 100,
    _user=Depends(optional_user),
):
    q = supabase().table("generated_content").select("*").order("created_at", desc=True).limit(limit)
    if status:
        statuses = [s.strip() for s in status.split(",") if s.strip()]
        q = q.in_("status", statuses)
    if pillar:
        q = q.eq("pillar", pillar)
    if platform:
        q = q.eq("platform", platform)
    return {"items": q.execute().data or []}


@router.get("/{content_id}")
def get_one(content_id: str, _user=Depends(optional_user)):
    rows = supabase().table("generated_content").select("*").eq("id", content_id).limit(1).execute().data
    if not rows:
        raise HTTPException(404, "Not found")
    return rows[0]


class PatchBody(BaseModel):
    status: str | None = None
    topic: str | None = None
    pillar: str | None = None
    platform: str | None = None
    duration: str | None = None
    hook: str | None = None
    script: str | None = None
    on_screen: str | None = None
    production_brief: str | None = None
    caption: str | None = None
    caption_tiktok: str | None = None
    caption_instagram: str | None = None
    caption_linkedin: str | None = None
    caption_facebook: str | None = None
    caption_x: str | None = None
    cta: str | None = None
    dm_keyword: str | None = None
    deliverable: str | None = None
    hashtags: list[str] | None = None
    scheduled_for: str | None = None
    scheduled_time: str | None = None


@router.patch("/{content_id}")
def patch(content_id: str, body: PatchBody, _user=Depends(optional_user)):
    payload = {k: v for k, v in body.model_dump().items() if v is not None}
    payload["updated_at"] = "now()"
    res = supabase().table("generated_content").update(payload).eq("id", content_id).execute()
    if not res.data:
        raise HTTPException(404, "Not found")
    return res.data[0]


@router.delete("/{content_id}")
def delete(content_id: str, _user=Depends(optional_user)):
    supabase().table("generated_content").delete().eq("id", content_id).execute()
    return {"ok": True}
