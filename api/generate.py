from fastapi import APIRouter, Depends
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


@router.post("")
async def generate(req: GenerateRequest, _user=Depends(optional_user)):
    n = max(1, min(req.variations, 5))
    results = []
    for _ in range(n):
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
            )
        )
    return {"results": results}
