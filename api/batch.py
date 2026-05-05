"""Batch generation: generate N days × M videos. Runs in background, reports progress in-memory."""
from __future__ import annotations
from datetime import date, timedelta
from uuid import uuid4
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from core import generator, brand_context
from .auth import optional_user

router = APIRouter(prefix="/api/batch", tags=["batch"])

_jobs: dict[str, dict] = {}


class BatchRequest(BaseModel):
    days: int = 7
    videos_per_day: int = 12
    start_date: str | None = None  # YYYY-MM-DD
    pillars: list[str] | None = None
    duration: str = "45 seconds"


@router.post("")
async def start_batch(req: BatchRequest, bg: BackgroundTasks, _user=Depends(optional_user)):
    if req.days < 1 or req.days > 365:
        raise HTTPException(400, "days must be 1-365")
    job_id = str(uuid4())
    _jobs[job_id] = {
        "id": job_id,
        "status": "Running",
        "total": req.days * req.videos_per_day,
        "completed": 0,
        "errors": 0,
        "results": [],
    }
    bg.add_task(_run, job_id, req)
    return _jobs[job_id]


@router.get("/{job_id}")
def status(job_id: str, _user=Depends(optional_user)):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return {**job, "results": job["results"][-20:]}


async def _run(job_id: str, req: BatchRequest):
    brand = brand_context.load()
    windows = brand.get("posting_windows") or []
    pillars = req.pillars or [p["name"] if isinstance(p, dict) else p for p in (brand.get("pillars") or [])]
    if not pillars:
        pillars = ["Psychology & Behavioral Economics"]

    start = date.fromisoformat(req.start_date) if req.start_date else date.today()
    job = _jobs[job_id]
    try:
        for d in range(req.days):
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
                    )
                    job["results"].append({"id": res.get("id"), "topic": res.get("topic"), "pillar": pillar, "day": day.isoformat()})
                except Exception as e:
                    job["errors"] += 1
                    job["results"].append({"error": str(e), "day": day.isoformat()})
                job["completed"] += 1
        job["status"] = "Done"
    except Exception as e:
        job["status"] = "Failed"
        job["error"] = str(e)
