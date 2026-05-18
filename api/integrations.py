import time
from typing import Any

from fastapi import APIRouter, Depends

from config import get_settings
from .auth import optional_user

router = APIRouter(prefix="/api/integrations", tags=["integrations"])


@router.get("")
def status(_user=Depends(optional_user)):
    s = get_settings()
    def stat(key: str) -> str:
        return "Connected" if bool(getattr(s, key, "")) else "Not Connected"
    return {
        "items": [
            {"name": "Supabase database", "category": "Database", "status": stat("SUPABASE_URL")},
            {"name": "Vector database (pgvector)", "category": "Database", "status": stat("SUPABASE_URL")},
            {"name": "Claude API", "category": "AI", "status": stat("ANTHROPIC_API_KEY")},
            {"name": "OpenAI Embeddings", "category": "AI", "status": stat("OPENAI_API_KEY")},
            {"name": "Perplexity API", "category": "AI", "status": stat("PERPLEXITY_API_KEY")},
            {"name": "Google Docs export", "category": "Workflow", "status": "Markdown stub"},
            {"name": "GoHighLevel", "category": "CRM", "status": stat("GHL_API_KEY")},
            {"name": "Social media posting", "category": "Distribution", "status": "Via GoHighLevel"},
        ]
    }


def _extract_provider_error(exc: BaseException) -> dict[str, Any]:
    """Pull `status_code` and structured `error` info from OpenAI/Anthropic SDK exceptions.
    Falls back to a generic message for non-HTTP exceptions.
    """
    out: dict[str, Any] = {
        "status_code": getattr(exc, "status_code", None),
        "exception_type": type(exc).__name__,
        "message": str(exc)[:600],
    }
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            out["error_type"] = err.get("type")
            out["error_code"] = err.get("code")
            out["error_message"] = err.get("message") or out["message"]
    response = getattr(exc, "response", None)
    if response is not None and "status_code" not in out:
        out["status_code"] = getattr(response, "status_code", None)
    return out


def _probe_openai(s) -> dict[str, Any]:
    started = time.perf_counter()
    if not s.OPENAI_API_KEY:
        return {
            "provider": "openai",
            "ok": False,
            "configured": False,
            "model": s.OPENAI_EMBEDDING_MODEL,
            "message": "OPENAI_API_KEY not set on server.",
            "elapsed_ms": 0,
        }
    try:
        from openai import OpenAI
        client = OpenAI(api_key=s.OPENAI_API_KEY, max_retries=0, timeout=20.0)
        resp = client.embeddings.create(model=s.OPENAI_EMBEDDING_MODEL, input=["probe"])
        return {
            "provider": "openai",
            "ok": True,
            "configured": True,
            "model": s.OPENAI_EMBEDDING_MODEL,
            "status_code": 200,
            "dimensions": len(resp.data[0].embedding),
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
        }
    except Exception as e:
        detail = _extract_provider_error(e)
        return {
            "provider": "openai",
            "ok": False,
            "configured": True,
            "model": s.OPENAI_EMBEDDING_MODEL,
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
            **detail,
        }


def _probe_anthropic(s) -> dict[str, Any]:
    started = time.perf_counter()
    if not s.ANTHROPIC_API_KEY:
        return {
            "provider": "anthropic",
            "ok": False,
            "configured": False,
            "model": s.ANTHROPIC_MODEL,
            "message": "ANTHROPIC_API_KEY not set on server.",
            "elapsed_ms": 0,
        }
    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=s.ANTHROPIC_API_KEY, max_retries=0, timeout=20.0)
        msg = client.messages.create(
            model=s.ANTHROPIC_MODEL,
            max_tokens=8,
            messages=[{"role": "user", "content": "Reply with exactly: ok"}],
        )
        text = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text").strip()
        return {
            "provider": "anthropic",
            "ok": True,
            "configured": True,
            "model": s.ANTHROPIC_MODEL,
            "status_code": 200,
            "reply": text[:50],
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
        }
    except Exception as e:
        detail = _extract_provider_error(e)
        return {
            "provider": "anthropic",
            "ok": False,
            "configured": True,
            "model": s.ANTHROPIC_MODEL,
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
            **detail,
        }


@router.post("/probe")
def probe(_user=Depends(optional_user)):
    """Diagnostic: make ONE real API call to each provider (no retries) and
    return the raw status code + provider error code/message. Use this to
    distinguish e.g. `insufficient_quota` (429) vs `rate_limit_exceeded` (429)
    vs `invalid_api_key` (401) on the live server.
    """
    s = get_settings()
    return {
        "openai": _probe_openai(s),
        "anthropic": _probe_anthropic(s),
    }
