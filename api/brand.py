from fastapi import APIRouter, Depends
from pydantic import BaseModel

from core import brand_context
from .auth import optional_user

router = APIRouter(prefix="/api/brand", tags=["brand"])


@router.get("")
def get_brand(_user=Depends(optional_user)):
    return brand_context.load()


class BrandPatch(BaseModel):
    brand_name: str | None = None
    creator_name: str | None = None
    nmls: str | None = None
    website: str | None = None
    voice_description: str | None = None
    compliance_footer: str | None = None
    excluded_states: list[str] | None = None
    licensed_states: list[str] | None = None
    pillars: list | None = None
    cta_structures: list | None = None
    posting_windows: list | None = None


@router.patch("")
def patch(body: BrandPatch, _user=Depends(optional_user)):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    return brand_context.upsert(updates)
