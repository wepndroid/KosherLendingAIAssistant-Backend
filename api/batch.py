"""Batch generation: generate N days × M videos.

Persisted to `batch_jobs` so a 3-year run survives a server restart.
Estimate endpoint returns expected token spend / wallclock / dollars before kicking off.
"""
from __future__ import annotations
import base64
from datetime import date, timedelta
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from core import generator, brand_context
from db.supabase_client import supabase
from integrations import word_export
from .auth import optional_user

router = APIRouter(prefix="/api/batch", tags=["batch"])

# Days cap — Jeffrey wants 2-3 years, so we allow up to 3 years.
MAX_DAYS = 1095

# Cost model (rough, USD per single content package). These match the Sonnet-4.6
# generation pipeline plus the Haiku reranker plus 1 OpenAI embedding for dedup.
PER_POST_INPUT_TOKENS = 4_500
PER_POST_OUTPUT_TOKENS = 1_400
SONNET_INPUT_PER_M = 3.00
SONNET_OUTPUT_PER_M = 15.00
HAIKU_RERANK_PER_POST = 0.001
EMBEDDING_PER_POST = 0.00002

# Wallclock per post in seconds (real measured ~6-10s, use 8 as a planning number)
SEC_PER_POST = 8


class BatchRequest(BaseModel):
    days: int = 7
    videos_per_day: int = 12
    start_date: str | None = None  # YYYY-MM-DD
    pillars: list[str] | None = None
    duration: str = "45 seconds"


@router.post("/estimate")
def estimate(req: BatchRequest, _user=Depends(optional_user)):
    if req.days < 1 or req.days > MAX_DAYS:
        raise HTTPException(400, f"days must be 1-{MAX_DAYS}")
    total = req.days * req.videos_per_day
    input_dollars = total * PER_POST_INPUT_TOKENS / 1_000_000 * SONNET_INPUT_PER_M
    output_dollars = total * PER_POST_OUTPUT_TOKENS / 1_000_000 * SONNET_OUTPUT_PER_M
    rerank_dollars = total * HAIKU_RERANK_PER_POST
    embed_dollars = total * EMBEDDING_PER_POST
    dollars = round(input_dollars + output_dollars + rerank_dollars + embed_dollars, 2)
    return {
        "total_posts": total,
        "input_tokens": total * PER_POST_INPUT_TOKENS,
        "output_tokens": total * PER_POST_OUTPUT_TOKENS,
        "wallclock_seconds": total * SEC_PER_POST,
        "wallclock_human": _human_seconds(total * SEC_PER_POST),
        "dollars_estimate": dollars,
        "breakdown": {
            "claude_input": round(input_dollars, 2),
            "claude_output": round(output_dollars, 2),
            "haiku_rerank": round(rerank_dollars, 2),
            "openai_embed": round(embed_dollars, 4),
        },
    }


@router.post("")
async def start_batch(req: BatchRequest, bg: BackgroundTasks, _user=Depends(optional_user)):
    if req.days < 1 or req.days > MAX_DAYS:
        raise HTTPException(400, f"days must be 1-{MAX_DAYS}")
    cost = estimate(req, _user=None)
    total = cost["total_posts"]

    job_row = supabase().table("batch_jobs").insert(
        {
            "status": "Running",
            "total": total,
            "completed": 0,
            "errors": 0,
            "request": req.model_dump(),
            "cost_estimate": cost,
            "results": [],
        }
    ).execute().data[0]

    bg.add_task(_run, job_row["id"], req)
    return job_row


@router.get("/{job_id}")
def status(job_id: str, _user=Depends(optional_user)):
    rows = supabase().table("batch_jobs").select("*").eq("id", job_id).limit(1).execute().data
    if not rows:
        raise HTTPException(404, "Job not found")
    job = rows[0]
    # Trim results to last 20 to keep payload small for polling
    results = job.get("results") or []
    job["results"] = results[-20:]
    return job


@router.get("")
def list_jobs(_user=Depends(optional_user)):
    rows = supabase().table("batch_jobs").select(
        "id,status,total,completed,errors,created_at,completed_at,cost_estimate"
    ).order("created_at", desc=True).limit(20).execute().data or []
    return {"items": rows}


@router.post("/{job_id}/cancel")
def cancel(job_id: str, _user=Depends(optional_user)):
    res = supabase().table("batch_jobs").update({"status": "Cancelled"}).eq("id", job_id).execute()
    if not res.data:
        raise HTTPException(404, "Job not found")
    return res.data[0]


@router.get("/{job_id}/export/word")
def export_batch_word(job_id: str, max_posts: int = 1000, _user=Depends(optional_user)):
    rows = supabase().table("batch_jobs").select("*").eq("id", job_id).limit(1).execute().data
    if not rows:
        raise HTTPException(404, "Job not found")
    job = rows[0]
    raw = job.get("results") or []
    ids = _extract_content_ids(raw)
    if max_posts > 0:
        ids = ids[:max_posts]
    if not ids:
        raise HTTPException(400, "No generated content is available for export in this batch job yet")

    posts = _fetch_content_by_ids(ids)
    if not posts:
        raise HTTPException(404, "No generated content rows found for batch export")

    brand = brand_context.load()
    footer = brand.get("compliance_footer", "")
    blob = word_export.render_content_pack(posts, f"Batch Export {job_id}", footer)
    b64 = base64.b64encode(blob).decode("ascii")
    return {
        "job_id": job_id,
        "posts": len(posts),
        "download_inline": f"data:application/vnd.openxmlformats-officedocument.wordprocessingml.document;base64,{b64}",
    }


async def _run(job_id: str, req: BatchRequest):
    db = supabase()
    brand = brand_context.load()
    pillars = req.pillars or [
        p["name"] if isinstance(p, dict) else p for p in (brand.get("pillars") or [])
    ]
    if not pillars:
        pillars = ["Psychology & Behavioral Economics"]

    start = date.fromisoformat(req.start_date) if req.start_date else date.today()
    completed = 0
    errors = 0
    recent_results: list[dict] = []
    all_content_ids: list[str] = []

    try:
        for d in range(req.days):
            # Cooperative cancel: re-read status each day
            cur = db.table("batch_jobs").select("status").eq("id", job_id).limit(1).execute().data
            if cur and cur[0].get("status") == "Cancelled":
                break

            day = start + timedelta(days=d)
            for slot in range(req.videos_per_day):
                pillar = pillars[(d + slot) % len(pillars)]
                platform = ["TikTok", "Instagram Reels", "YouTube Shorts", "Facebook Reels", "LinkedIn", "X/Twitter"][slot % 6]
                topic = f"{pillar} insight for {day.isoformat()} slot {slot+1}"
                try:
                    res = await generator.generate_one(
                        pillar=pillar,
                        platform=platform,
                        duration=req.duration,
                        topic=topic,
                        block_on_duplicate=False,  # batch mode flags but doesn't block
                    )
                    if res.get("id"):
                        all_content_ids.append(res["id"])
                    recent_results.append({
                        "id": res.get("id"),
                        "topic": res.get("topic"),
                        "pillar": pillar,
                        "day": day.isoformat(),
                    })
                except Exception as e:
                    errors += 1
                    recent_results.append({"error": str(e)[:200], "day": day.isoformat()})
                completed += 1

                # Persist progress every 10 posts to avoid hammering the DB
                if completed % 10 == 0 or completed == req.days * req.videos_per_day:
                    db.table("batch_jobs").update(
                        {
                            "completed": completed,
                            "errors": errors,
                            "results": recent_results[-50:],
                            "updated_at": "now()",
                        }
                    ).eq("id", job_id).execute()

        db.table("batch_jobs").update(
            {
                "status": "Done",
                "completed": completed,
                "errors": errors,
                "results": all_content_ids or recent_results[-50:],
                "completed_at": "now()",
            }
        ).eq("id", job_id).execute()
    except Exception as e:
        db.table("batch_jobs").update(
            {"status": "Failed", "error": str(e)[:500], "completed": completed, "errors": errors}
        ).eq("id", job_id).execute()


def _human_seconds(s: int) -> str:
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h}h {m}m"
    if m:
        return f"{m}m {sec}s"
    return f"{sec}s"


def _extract_content_ids(raw_results: list) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for r in raw_results:
        cid = None
        if isinstance(r, str):
            cid = r
        elif isinstance(r, dict):
            cid = r.get("id")
        if not cid or cid in seen:
            continue
        seen.add(cid)
        out.append(cid)
    return out


def _fetch_content_by_ids(ids: list[str]) -> list[dict]:
    by_id: dict[str, dict] = {}
    for i in range(0, len(ids), 200):
        chunk = ids[i : i + 200]
        rows = (
            supabase()
            .table("generated_content")
            .select("*")
            .in_("id", chunk)
            .execute()
            .data
            or []
        )
        for r in rows:
            by_id[r["id"]] = r
    # preserve generation order
    return [by_id[cid] for cid in ids if cid in by_id]
