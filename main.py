from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import get_settings
from core import brand_context

from api import auth, generate, knowledge, content, keywords, brand, dashboard, calendar, export, integrations, batch, webhooks


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        brand_context.load()
    except Exception as e:
        print(f"[startup] brand_context.load() warning: {e}")
    yield


app = FastAPI(title="KosherLending AI Content OS", version="1.0.0", lifespan=lifespan)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _unwrap(exc: BaseException) -> BaseException:
    """Walk through tenacity RetryError / ExceptionGroup-style wrappers to the root cause."""
    seen: set[int] = set()
    cur = exc
    while id(cur) not in seen:
        seen.add(id(cur))
        # tenacity.RetryError exposes .last_attempt.exception()
        last_attempt = getattr(cur, "last_attempt", None)
        if last_attempt is not None and hasattr(last_attempt, "exception"):
            try:
                inner = last_attempt.exception()
                if inner is not None:
                    cur = inner
                    continue
            except Exception:
                pass
        cause = cur.__cause__ or cur.__context__
        if cause is not None and cause is not cur:
            cur = cause
            continue
        break
    return cur


def _cors_headers(req: Request) -> dict[str, str]:
    origin = req.headers.get("origin")
    if origin and origin in settings.origins:
        return {
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Credentials": "true",
            "Vary": "Origin",
        }
    return {}


_INTEGRATION_KEYS = ("SUPABASE", "ANTHROPIC", "OPENAI", "GHL", "PERPLEXITY")
_INTEGRATION_HINTS = (
    "invalid api key",
    "incorrect api key",
    "401 unauthorized",
    "403 forbidden",
    "could not resolve host",
    "name or service not known",
    "nodename nor servname provided",
    "supabaseexception",
    "your-project.supabase.co",
)


def _is_integration_failure(root: BaseException) -> bool:
    msg = str(root).lower()
    if isinstance(root, RuntimeError) and any(k in str(root) for k in _INTEGRATION_KEYS):
        return True
    cls = type(root).__name__.lower()
    if any(h in msg for h in _INTEGRATION_HINTS):
        return True
    if "supabase" in cls or "openai" in cls or "anthropic" in cls:
        return True
    return False


@app.exception_handler(Exception)
async def integration_error_handler(req: Request, exc: Exception):
    root = _unwrap(exc)
    msg = str(root)
    headers = _cors_headers(req)
    if _is_integration_failure(root):
        return JSONResponse(
            status_code=503,
            content={"detail": msg, "code": "integration_not_configured"},
            headers=headers,
        )
    return JSONResponse(status_code=500, content={"detail": f"{type(root).__name__}: {msg}"}, headers=headers)


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "env": settings.APP_ENV,
        "supabase_configured": bool(settings.SUPABASE_URL and settings.SUPABASE_SERVICE_ROLE_KEY),
        "anthropic_configured": bool(settings.ANTHROPIC_API_KEY),
        "openai_configured": bool(settings.OPENAI_API_KEY),
    }


for r in (auth, generate, knowledge, content, keywords, brand, dashboard, calendar, export, integrations, batch, webhooks):
    app.include_router(r.router)
