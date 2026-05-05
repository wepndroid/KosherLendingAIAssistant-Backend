"""JWT auth — register, login, current user dependency."""
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr
import jwt
from passlib.context import CryptContext

from config import get_settings
from db.supabase_client import supabase

router = APIRouter(prefix="/api/auth", tags=["auth"])
bearer = HTTPBearer(auto_error=False)
_pw = CryptContext(schemes=["bcrypt"], deprecated="auto")


class Credentials(BaseModel):
    email: EmailStr
    password: str
    name: str | None = None


class TokenOut(BaseModel):
    token: str
    user: dict


def _make_token(user: dict) -> str:
    s = get_settings()
    payload = {
        "sub": user["id"],
        "email": user["email"],
        "role": user.get("role", "admin"),
        "exp": datetime.now(timezone.utc) + timedelta(hours=s.JWT_TTL_HOURS),
    }
    return jwt.encode(payload, s.JWT_SECRET, algorithm=s.JWT_ALG)


@router.post("/register", response_model=TokenOut)
def register(body: Credentials):
    db = supabase()
    existing = db.table("users").select("id").eq("email", body.email).limit(1).execute().data
    if existing:
        raise HTTPException(409, "Email already registered")
    row = {
        "email": body.email,
        "password_hash": _pw.hash(body.password),
        "name": body.name,
        "role": "admin",
    }
    res = db.table("users").insert(row).execute().data[0]
    return TokenOut(token=_make_token(res), user={"id": res["id"], "email": res["email"], "name": res.get("name"), "role": res["role"]})


@router.post("/login", response_model=TokenOut)
def login(body: Credentials):
    db = supabase()
    rows = db.table("users").select("*").eq("email", body.email).limit(1).execute().data
    if not rows or not _pw.verify(body.password, rows[0]["password_hash"]):
        raise HTTPException(401, "Invalid credentials")
    user = rows[0]
    db.table("users").update({"last_login": "now()"}).eq("id", user["id"]).execute()
    return TokenOut(token=_make_token(user), user={"id": user["id"], "email": user["email"], "name": user.get("name"), "role": user["role"]})


def current_user(creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> dict:
    if not creds:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing token")
    s = get_settings()
    try:
        payload = jwt.decode(creds.credentials, s.JWT_SECRET, algorithms=[s.JWT_ALG])
    except jwt.PyJWTError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Invalid token: {e}")
    return payload


def optional_user(creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> dict | None:
    if not creds:
        return None
    try:
        return current_user(creds)
    except HTTPException:
        return None


@router.get("/me")
def me(user: dict = Depends(current_user)):
    return user
