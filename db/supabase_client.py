from functools import lru_cache
from supabase import create_client, Client
from ..config import get_settings


@lru_cache
def supabase() -> Client:
    s = get_settings()
    if not s.SUPABASE_URL or not s.SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in .env")
    return create_client(s.SUPABASE_URL, s.SUPABASE_SERVICE_ROLE_KEY)


@lru_cache
def supabase_anon() -> Client:
    s = get_settings()
    return create_client(s.SUPABASE_URL, s.SUPABASE_ANON_KEY)
