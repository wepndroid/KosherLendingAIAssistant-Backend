"""Hybrid retrieval: pgvector + Postgres FTS via RRF, then LLM rerank."""
from db.supabase_client import supabase
from integrations.openai_client import embed_one
from integrations.reranker import rerank


def retrieve(query: str, *, pillar: str | None = None, k: int = 8, candidate_pool: int = 30) -> list[dict]:
    """Hybrid pipeline:
    1. Vector + keyword search fused by Reciprocal Rank Fusion → top-N candidates
    2. Claude Haiku reranker selects the k most relevant for the query
    3. Hydrate with document name in metadata for citation
    """
    if not query:
        return []
    vec = embed_one(query)

    rows = _hybrid_candidates(query, vec, pillar=pillar, count=candidate_pool)
    if not rows:
        rows = _vector_only(vec, pillar=pillar, k=candidate_pool)
    if not rows:
        rows = _keyword_fallback(query, k=candidate_pool)

    candidates = [_normalize(r) for r in rows]
    if not candidates:
        return []

    candidates = _hydrate_doc_names(candidates)

    # Rerank — falls back to RRF order on failure
    try:
        top_indices = rerank(query=query, candidates=candidates, top_k=k)
    except Exception:
        top_indices = list(range(min(k, len(candidates))))

    return [candidates[i] for i in top_indices]


def _hybrid_candidates(query: str, vec: list[float], *, pillar: str | None, count: int) -> list[dict]:
    try:
        resp = supabase().rpc(
            "hybrid_match_chunks",
            {
                "query_embedding": vec,
                "query_text": query,
                "match_count": count,
                "filter_pillar": pillar,
            },
        ).execute()
        return resp.data or []
    except Exception:
        return []


def _vector_only(vec: list[float], *, pillar: str | None, k: int) -> list[dict]:
    try:
        resp = supabase().rpc(
            "match_chunks",
            {"query_embedding": vec, "match_count": k, "filter_pillar": pillar},
        ).execute()
        return resp.data or []
    except Exception:
        return []


def _keyword_fallback(query: str, *, k: int) -> list[dict]:
    try:
        return (
            supabase()
            .table("knowledge_chunks")
            .select("id,document_id,chunk_text,metadata")
            .ilike("chunk_text", f"%{query[:60]}%")
            .limit(k)
            .execute()
            .data
            or []
        )
    except Exception:
        return []


def _normalize(r: dict) -> dict:
    return {
        "id": r.get("id"),
        "document_id": r.get("document_id"),
        "chunk_text": r["chunk_text"],
        "metadata": r.get("metadata") or {},
        "vector_rank": r.get("vector_rank"),
        "keyword_rank": r.get("keyword_rank"),
        "rrf_score": r.get("rrf_score"),
        "similarity": r.get("similarity"),
    }


def _hydrate_doc_names(candidates: list[dict]) -> list[dict]:
    """Attach document_name to each candidate's metadata in one round-trip."""
    needs = [c["document_id"] for c in candidates if c.get("document_id") and "document_name" not in (c.get("metadata") or {})]
    if not needs:
        return candidates
    try:
        rows = (
            supabase()
            .table("knowledge_documents")
            .select("id,name")
            .in_("id", list(set(needs)))
            .execute()
            .data
            or []
        )
        names = {r["id"]: r["name"] for r in rows}
    except Exception:
        names = {}
    for c in candidates:
        meta = c.get("metadata") or {}
        if c.get("document_id") and "document_name" not in meta:
            meta["document_name"] = names.get(c["document_id"], "Unknown source")
            c["metadata"] = meta
    return candidates
