from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..db.supabase_client import supabase
from .auth import optional_user

router = APIRouter(prefix="/api/calendar", tags=["calendar"])


@router.get("")
def calendar(start: str | None = None, end: str | None = None, _user=Depends(optional_user)):
    q = supabase().table("generated_content").select("*").not_.is_("scheduled_for", "null")
    if start:
        q = q.gte("scheduled_for", start)
    if end:
        q = q.lte("scheduled_for", end)
    return {"items": q.execute().data or []}


class ScheduleBody(BaseModel):
    content_id: str
    scheduled_for: str  # YYYY-MM-DD
    scheduled_time: str  # HH:MM
    platforms: list[str]


@router.post("/schedule")
def schedule(body: ScheduleBody, _user=Depends(optional_user)):
    db = supabase()
    res = (
        db.table("generated_content")
        .update(
            {
                "scheduled_for": body.scheduled_for,
                "scheduled_time": body.scheduled_time,
                "status": "Scheduled",
                "platform_targets": body.platforms,
            }
        )
        .eq("id", body.content_id)
        .execute()
    )
    if not res.data:
        raise HTTPException(404, "Content not found")

    iso = f"{body.scheduled_for}T{body.scheduled_time}:00Z"
    queue_rows = [
        {"content_id": body.content_id, "platform": p, "scheduled_for": iso, "status": "Queued"}
        for p in body.platforms
    ]
    if queue_rows:
        db.table("posting_queue").insert(queue_rows).execute()
    return res.data[0]


@router.get("/queue")
def queue(_user=Depends(optional_user)):
    rows = supabase().table("posting_queue").select("*").order("scheduled_for").execute().data or []
    return {"items": rows}
