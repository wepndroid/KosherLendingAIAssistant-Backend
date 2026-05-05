import os
import tempfile
import hashlib
import time
from pathlib import Path
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile

from core import ingestion, cross_analysis, synthesis
from db.supabase_client import supabase
from config import get_settings
from .auth import optional_user

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])

# 8 MB read window — stays well under any worker's memory budget for any file size
_UPLOAD_CHUNK = 8 * 1024 * 1024
_INGEST_MAX_RETRIES = 3
_INGEST_RETRY_BASE_SEC = 2


@router.get("/log")
def library_log(limit: int = 100, _user=Depends(optional_user)):
    """Chronological library log — what's been added and when."""
    return {"items": synthesis.library_log(limit=limit)}


@router.get("/unexplored")
def unexplored(limit: int = 10, _user=Depends(optional_user)):
    """Book pairs that have not yet been used together in any generation."""
    return {"items": synthesis.unexplored_pairs(limit=limit)}


@router.get("")
def list_docs(_user=Depends(optional_user)):
    rows = (
        supabase()
        .table("knowledge_documents")
        .select("*")
        .order("uploaded_at", desc=True)
        .execute()
        .data
        or []
    )
    return {"items": rows}


@router.get("/{doc_id}")
def get_doc(doc_id: str, _user=Depends(optional_user)):
    rows = supabase().table("knowledge_documents").select("*").eq("id", doc_id).limit(1).execute().data
    if not rows:
        raise HTTPException(404, "Not found")
    return rows[0]


@router.post("/upload")
async def upload(
    bg: BackgroundTasks,
    file: UploadFile = File(...),
    category: str = Form("Book"),
    pillars: str = Form(""),
    _user=Depends(optional_user),
):
    """Streaming upload: never loads the whole file into RAM.

    The bytes go to a local temp file in 8 MB chunks. The background task
    runs the streaming ingestion against that temp file, then uploads the
    raw file to Supabase Storage as a backup, and finally deletes the temp.
    """
    pillar_list = [p.strip() for p in pillars.split(",") if p.strip()]
    suffix = Path(file.filename or "").suffix.lower()

    # Stream to a local temp file
    fd, tmp_path = tempfile.mkstemp(suffix=suffix)
    total_bytes = 0
    sha = hashlib.sha256()
    try:
        with os.fdopen(fd, "wb") as out:
            while True:
                chunk = await file.read(_UPLOAD_CHUNK)
                if not chunk:
                    break
                out.write(chunk)
                total_bytes += len(chunk)
                sha.update(chunk)
    except Exception:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
        raise
    file_sha256 = sha.hexdigest()

    # De-duplicate by exact file fingerprint: do not re-index the same file bytes.
    existing = (
        supabase()
        .table("knowledge_documents")
        .select("*")
        .eq("file_sha256", file_sha256)
        .order("uploaded_at", desc=True)
        .limit(1)
        .execute()
        .data
        or []
    )
    if existing:
        row = existing[0]
        # If already indexed, return that row and skip re-indexing.
        if row.get("status") == "Indexed":
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
            row["deduplicated"] = True
            row["deduplicate_reason"] = "same_file_sha256"
            return row
        # If previously failed/interrupted, reuse existing row id and retry ingestion.
        updated = (
            supabase()
            .table("knowledge_documents")
            .update(
                {
                    "name": file.filename,
                    "category": category,
                    "file_type": (file.filename or "").split(".")[-1].upper(),
                    "file_size_bytes": total_bytes,
                    "status": "Uploaded",
                    "pillars": pillar_list,
                    "summary": None,
                    "indexed_at": None,
                }
            )
            .eq("id", row["id"])
            .execute()
            .data
        )
        reused = updated[0] if updated else row
        bg.add_task(_run_ingest_streaming, reused["id"], file.filename, tmp_path)
        return reused

    row = {
        "name": file.filename,
        "category": category,
        "file_type": (file.filename or "").split(".")[-1].upper(),
        "file_size_bytes": total_bytes,
        "file_sha256": file_sha256,
        "status": "Uploaded",
        "pillars": pillar_list,
    }
    inserted = supabase().table("knowledge_documents").insert(row).execute().data[0]

    bg.add_task(_run_ingest_streaming, inserted["id"], file.filename, tmp_path)
    return inserted


def _run_ingest_streaming(doc_id: str, filename: str, tmp_path: str):
    """Streaming ingestion: opens the local temp file once, parses page-by-page,
    embeds in batches. Memory stays bounded regardless of file size."""
    last_error = None
    try:
        for attempt in range(1, _INGEST_MAX_RETRIES + 1):
            try:
                supabase().table("knowledge_documents").update(
                    {"status": f"Processing ({attempt}/{_INGEST_MAX_RETRIES})"}
                ).eq("id", doc_id).execute()
                # Retry-safe/idempotent: clear any partial chunks from previous failed attempts.
                supabase().table("knowledge_chunks").delete().eq("document_id", doc_id).execute()
                with open(tmp_path, "rb") as f:
                    ingestion.ingest_streaming(document_id=doc_id, filename=filename, file_obj=f)
                cross_analysis.run(doc_id)
                _upload_to_storage(doc_id, filename, tmp_path)
                return
            except Exception as e:
                last_error = str(e)
                supabase().table("activity_log").insert(
                    {
                        "text": f"{filename} ingest attempt {attempt}/{_INGEST_MAX_RETRIES} failed",
                        "icon": "x",
                        "metadata": {"document_id": doc_id, "error": last_error[:500]},
                    }
                ).execute()
                if attempt < _INGEST_MAX_RETRIES:
                    time.sleep(_INGEST_RETRY_BASE_SEC * (2 ** (attempt - 1)))
        supabase().table("knowledge_documents").update(
            {"status": "Failed", "summary": f"Error after {_INGEST_MAX_RETRIES} attempts: {last_error}"}
        ).eq("id", doc_id).execute()
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


def _upload_to_storage(doc_id: str, filename: str, local_path: str) -> None:
    """Best-effort: copy the source file into Supabase Storage so it's preserved off the worker."""
    s = get_settings()
    bucket = s.SUPABASE_STORAGE_BUCKET
    if not bucket:
        return
    storage_path = f"docs/{doc_id}/{filename}"
    try:
        client = supabase().storage.from_(bucket)
        # supabase-py's upload reads from disk path or bytes; using the path keeps it streaming-friendly
        with open(local_path, "rb") as f:
            client.upload(path=storage_path, file=f, file_options={"upsert": "true"})
        supabase().table("knowledge_documents").update({"storage_path": storage_path}).eq("id", doc_id).execute()
    except Exception:
        # Non-fatal: ingestion already succeeded, the file just isn't archived
        pass


@router.delete("/{doc_id}")
def delete_doc(doc_id: str, _user=Depends(optional_user)):
    supabase().table("knowledge_documents").delete().eq("id", doc_id).execute()
    return {"ok": True}
