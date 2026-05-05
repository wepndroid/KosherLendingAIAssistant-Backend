import httpx
from config import get_settings


async def research(query: str) -> str | None:
    """Returns short, current market context. Returns None if not configured or on error."""
    s = get_settings()
    if not s.PERPLEXITY_API_KEY:
        return None
    headers = {"Authorization": f"Bearer {s.PERPLEXITY_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": s.PERPLEXITY_MODEL,
        "messages": [
            {"role": "system", "content": "You are a real-time mortgage and real-estate market researcher. Reply with 3-5 sentences of CURRENT facts only — no advice, no fluff."},
            {"role": "user", "content": query},
        ],
        "max_tokens": 400,
    }
    try:
        async with httpx.AsyncClient(timeout=20) as http:
            r = await http.post("https://api.perplexity.ai/chat/completions", headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()
            return data["choices"][0]["message"]["content"].strip()
    except Exception:
        return None
