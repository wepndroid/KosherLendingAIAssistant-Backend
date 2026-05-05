"""pgvector similarity retrieval for the generation pipeline."""
from db.supabase_client import supabase
from integrations.openai_client import embed_one


def retrieve(query: str, *, pillar: str | None = None, k: int = 8) -> list[dict]:
    """Returns top-k chunks as a list of dicts ready for prompt assembly."""
    if not query:
        return []
    vec = embed_one(query)
    try:
        resp = supabase().rpc(
            "match_chunks",
            {"query_embedding": vec, "match_count": k, "filter_pillar": pillar},
        ).execute()
        rows = resp.data or []
    except Exception:
        rows = []
    if not rows:
        # Fallback: keyword-ish ilike search if no chunks yet or RPC missing
        like = supabase().table("knowledge_chunks").select("id,document_id,chunk_text,metadata").ilike("chunk_text", f"%{query[:60]}%").limit(k).execute().data or []
        rows = like

    out: list[dict] = []
    for r in rows:
        meta = r.get("metadata") or {}
        if "document_name" not in meta and r.get("document_id"):
            doc = supabase().table("knowledge_documents").select("name").eq("id", r["document_id"]).limit(1).execute().data
            if doc:
                meta["document_name"] = doc[0]["name"]
        out.append(
            {
                "id": r.get("id"),
                "document_id": r.get("document_id"),
                "chunk_text": r["chunk_text"],
                "metadata": meta,
                "similarity": r.get("similarity"),
            }
        )
    return out
