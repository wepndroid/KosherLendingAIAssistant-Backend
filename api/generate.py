from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core import generator
from .auth import optional_user

router = APIRouter(prefix="/api/generate", tags=["generate"])


class GenerateRequest(BaseModel):
    pillar: str
    platform: str
    duration: str = "45 seconds"
    topic: str | None = None
    goal: str | None = None
    source_strategy: str | None = None
    dm_keyword: str | None = None
    source_books: list[str] = Field(default_factory=list)
    use_perplexity: bool = False
    variations: int = 1
    block_on_duplicate: bool = True


@router.post("")
async def generate(req: GenerateRequest, _user=Depends(optional_user)):
    n = max(1, min(req.variations, 5))
    results = []
    blocked: list[dict] = []
    for _ in range(n):
        try:
            results.append(
                await generator.generate_one(
                    pillar=req.pillar,
                    platform=req.platform,
                    duration=req.duration,
                    topic=req.topic,
                    goal=req.goal,
                    source_strategy=req.source_strategy,
                    dm_keyword=req.dm_keyword,
                    source_books=req.source_books or None,
                    use_perplexity=req.use_perplexity,
                    block_on_duplicate=req.block_on_duplicate,
                )
            )
        except (generator.DuplicateAngleError, generator.DuplicateComboError) as e:
            reason = "duplicate_combo" if isinstance(e, generator.DuplicateComboError) else "duplicate_angle"
            blocked.append({"reason": reason, "conflicts": e.conflicts})
    if not results and blocked:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "duplicate_angle_blocked",
                "message": "All variations were too similar to recent posts. Try a different angle, framework, or pillar.",
                "blocked": blocked,
            },
        )
    return {"results": results, "blocked": blocked}
