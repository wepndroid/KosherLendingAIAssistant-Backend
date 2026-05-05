from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from db.supabase_client import supabase
from .auth import optional_user

router = APIRouter(prefix="/api/keywords", tags=["keywords"])


class KeywordIn(BaseModel):
    keyword: str
    category: str | None = None
    pillars: list[str] | None = None
    intent: str | None = None
    cta_template: str | None = None
    deliverable_id: str | None = None
    ghl_status: str | None = None
    summary: str | None = None
    status: str | None = None


@router.get("")
def list_keywords(_user=Depends(optional_user)):
    rows = supabase().table("dm_keywords").select("*").order("usage_count", desc=True).execute().data or []
    return {"items": rows}


@router.post("")
def create(body: KeywordIn, _user=Depends(optional_user)):
    payload = {k: v for k, v in body.model_dump().items() if v is not None}
    payload["keyword"] = payload["keyword"].upper()
    res = supabase().table("dm_keywords").insert(payload).execute()
    return res.data[0]


@router.patch("/{keyword}")
def patch(keyword: str, body: KeywordIn, _user=Depends(optional_user)):
    payload = {k: v for k, v in body.model_dump(exclude={"keyword"}).items() if v is not None}
    res = supabase().table("dm_keywords").update(payload).eq("keyword", keyword.upper()).execute()
    if not res.data:
        raise HTTPException(404, "Not found")
    return res.data[0]


@router.delete("/{keyword}")
def delete(keyword: str, _user=Depends(optional_user)):
    supabase().table("dm_keywords").delete().eq("keyword", keyword.upper()).execute()
    return {"ok": True}


@router.get("/deliverables")
def list_deliverables(_user=Depends(optional_user)):
    rows = supabase().table("dm_deliverables").select("*").order("created_at", desc=True).execute().data or []
    return {"items": rows}
