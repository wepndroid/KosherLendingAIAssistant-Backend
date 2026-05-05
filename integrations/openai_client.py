from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential
from config import get_settings

_client: OpenAI | None = None


def client() -> OpenAI:
    global _client
    if _client is None:
        s = get_settings()
        if not s.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY not set")
        _client = OpenAI(api_key=s.OPENAI_API_KEY)
    return _client


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
def embed(texts: list[str]) -> list[list[float]]:
    """Returns one embedding per input text. Batches up to 100 per request."""
    s = get_settings()
    out: list[list[float]] = []
    for i in range(0, len(texts), 100):
        batch = texts[i : i + 100]
        resp = client().embeddings.create(model=s.OPENAI_EMBEDDING_MODEL, input=batch)
        out.extend(d.embedding for d in resp.data)
    return out


def embed_one(text: str) -> list[float]:
    return embed([text])[0]
