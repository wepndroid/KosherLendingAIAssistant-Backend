"""Document ingestion: parse → chunk → embed → store. Handles DOCX, PDF, TXT, MD."""
from __future__ import annotations
import io
import re
from pathlib import Path
from docx import Document as DocxDocument
from pypdf import PdfReader
from ..db.supabase_client import supabase
from ..integrations.openai_client import embed
from ..integrations.claude_client import summarize


CHUNK_SIZE = 800
CHUNK_OVERLAP = 100


def parse_text(filename: str, data: bytes) -> str:
    ext = Path(filename).suffix.lower()
    if ext == ".docx":
        return _parse_docx(data)
    if ext == ".pdf":
        return _parse_pdf(data)
    if ext in {".txt", ".md"}:
        return data.decode("utf-8", errors="ignore")
    raise ValueError(f"Unsupported file type: {ext}")


def _parse_docx(data: bytes) -> str:
    doc = DocxDocument(io.BytesIO(data))
    parts: list[str] = []
    for p in doc.paragraphs:
        if p.text and p.text.strip():
            parts.append(p.text)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                if cell.text and cell.text.strip():
                    parts.append(cell.text)
    return "\n".join(parts)


def _parse_pdf(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    out: list[str] = []
    for page in reader.pages:
        try:
            out.append(page.extract_text() or "")
        except Exception:
            out.append("")
    return "\n".join(out)


def chunk(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Word-based chunking with overlap. Cheap and good enough for this corpus."""
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    words = text.split()
    chunks: list[str] = []
    i = 0
    while i < len(words):
        end = min(i + size, len(words))
        chunks.append(" ".join(words[i:end]))
        if end >= len(words):
            break
        i = end - overlap
    return chunks


def ingest_document(*, document_id: str, filename: str, data: bytes) -> dict:
    """Run the full pipeline for a single document. Updates Supabase rows in place."""
    db = supabase()
    db.table("knowledge_documents").update({"status": "Processing"}).eq("id", document_id).execute()

    text = parse_text(filename, data)
    pieces = chunk(text)
    if not pieces:
        db.table("knowledge_documents").update({"status": "Failed"}).eq("id", document_id).execute()
        return {"status": "Failed", "reason": "No text extracted"}

    # Embed in batches
    vectors = embed(pieces)
    rows = [
        {
            "document_id": document_id,
            "chunk_index": i,
            "chunk_text": p,
            "embedding": v,
            "metadata": {"source": filename},
        }
        for i, (p, v) in enumerate(zip(pieces, vectors))
    ]
    # Insert in batches of 100 to keep payloads manageable
    for i in range(0, len(rows), 100):
        db.table("knowledge_chunks").insert(rows[i : i + 100]).execute()

    summary = ""
    try:
        summary = summarize(text[:30000])
    except Exception:
        pass

    db.table("knowledge_documents").update(
        {
            "status": "Indexed",
            "total_chunks": len(rows),
            "summary": summary,
            "indexed_at": "now()",
        }
    ).eq("id", document_id).execute()

    db.table("activity_log").insert(
        {"text": f"{filename} indexed ({len(rows)} chunks)", "icon": "check"}
    ).execute()

    return {"status": "Indexed", "chunks": len(rows), "summary": summary}
