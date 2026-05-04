from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile

from ..core import ingestion, cross_analysis, synthesis
from ..db.supabase_client import supabase
from .auth import optional_user

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


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
    data = await file.read()
    pillar_list = [p.strip() for p in pillars.split(",") if p.strip()]
    row = {
        "name": file.filename,
        "category": category,
        "file_type": (file.filename or "").split(".")[-1].upper(),
        "file_size_bytes": len(data),
        "status": "Uploaded",
        "pillars": pillar_list,
    }
    inserted = supabase().table("knowledge_documents").insert(row).execute().data[0]

    bg.add_task(_run_ingest, inserted["id"], file.filename, data)
    return inserted


def _run_ingest(doc_id: str, filename: str, data: bytes):
    try:
        ingestion.ingest_document(document_id=doc_id, filename=filename, data=data)
        cross_analysis.run(doc_id)
    except Exception as e:
        supabase().table("knowledge_documents").update({"status": "Failed", "summary": f"Error: {e}"}).eq("id", doc_id).execute()


@router.delete("/{doc_id}")
def delete_doc(doc_id: str, _user=Depends(optional_user)):
    supabase().table("knowledge_documents").delete().eq("id", doc_id).execute()
    return {"ok": True}
