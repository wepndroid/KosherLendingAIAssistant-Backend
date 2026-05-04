import base64
import csv
import io
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..db.supabase_client import supabase
from ..core import brand_context
from ..integrations import word_export, google_docs
from .auth import optional_user

router = APIRouter(prefix="/api/export", tags=["export"])


class ExportRequest(BaseModel):
    name: str
    format: str  # word | gdocs | csv | ghl_map
    content_ids: list[str] | None = None
    filter_status: list[str] | None = None
    filter_pillar: str | None = None


@router.get("")
def list_exports(_user=Depends(optional_user)):
    rows = supabase().table("exports").select("*").order("created_at", desc=True).execute().data or []
    return {"items": rows}


@router.post("")
def create_export(req: ExportRequest, _user=Depends(optional_user)):
    items = _resolve_items(req)
    if not items and req.format != "ghl_map":
        raise HTTPException(400, "No content matched the filters")

    brand = brand_context.load()
    footer = brand.get("compliance_footer", "")

    if req.format == "word":
        blob = word_export.render_content_pack(items, req.name, footer)
        b64 = base64.b64encode(blob).decode("ascii")
        export_row = _save_export(req, len(items), inline=f"data:application/vnd.openxmlformats-officedocument.wordprocessingml.document;base64,{b64}")
        return {"export": export_row, "download_inline": export_row["download_url"]}

    if req.format == "gdocs":
        md = google_docs.export_markdown(items, req.name, footer)
        b64 = base64.b64encode(md.encode("utf-8")).decode("ascii")
        export_row = _save_export(req, len(items), inline=f"data:text/markdown;base64,{b64}")
        return {"export": export_row, "markdown": md}

    if req.format == "csv":
        buf = io.StringIO()
        cols = [
            "topic","pillar","platform","duration","hook","script","on_screen",
            "production_brief","caption_tiktok","caption_instagram","caption_linkedin",
            "caption_facebook","caption_x","cta","dm_keyword","deliverable","hashtags",
            "source_book","source_framework",
        ]
        w = csv.writer(buf)
        w.writerow(cols)
        for item in items:
            w.writerow([_csv_value(item.get(c)) for c in cols])
        b64 = base64.b64encode(buf.getvalue().encode("utf-8")).decode("ascii")
        export_row = _save_export(req, len(items), inline=f"data:text/csv;base64,{b64}")
        return {"export": export_row}

    if req.format == "ghl_map":
        kws = supabase().table("dm_keywords").select("*").execute().data or []
        delivs = supabase().table("dm_deliverables").select("id,title,keyword,content_markdown").execute().data or []
        delivs_by_id = {d["id"]: d for d in delivs}
        mapping = []
        for k in kws:
            d = delivs_by_id.get(k.get("deliverable_id"))
            mapping.append(
                {
                    "keyword": k["keyword"],
                    "category": k.get("category"),
                    "intent": k.get("intent"),
                    "deliverable_title": (d or {}).get("title"),
                    "ghl_workflow_id": (d or {}).get("ghl_workflow_id"),
                    "ghl_status": k.get("ghl_status"),
                }
            )
        import json
        b64 = base64.b64encode(json.dumps(mapping, indent=2).encode("utf-8")).decode("ascii")
        export_row = _save_export(req, len(mapping), inline=f"data:application/json;base64,{b64}")
        return {"export": export_row, "mapping": mapping}

    raise HTTPException(400, f"Unknown format: {req.format}")


def _resolve_items(req: ExportRequest) -> list[dict]:
    db = supabase()
    if req.content_ids:
        return db.table("generated_content").select("*").in_("id", req.content_ids).execute().data or []
    q = db.table("generated_content").select("*")
    if req.filter_status:
        q = q.in_("status", req.filter_status)
    if req.filter_pillar:
        q = q.eq("pillar", req.filter_pillar)
    return q.execute().data or []


def _save_export(req: ExportRequest, count: int, *, inline: str) -> dict:
    row = {
        "name": req.name,
        "format": req.format,
        "posts": count,
        "status": "Ready",
        "download_url": inline,
        "filters": req.model_dump(exclude={"name", "format"}),
    }
    res = supabase().table("exports").insert(row).execute()
    return res.data[0] if res.data else row


def _csv_value(v):
    if isinstance(v, list):
        return " ".join(str(x) for x in v)
    if v is None:
        return ""
    return str(v)
