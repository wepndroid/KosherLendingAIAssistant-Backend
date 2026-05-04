from fastapi import APIRouter, Depends

from ..config import get_settings
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
