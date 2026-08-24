import os
from sentence_transformers import SentenceTransformer

_model_cache: dict[str, SentenceTransformer] = {}


def get_embedder(model_name: str | None = None) -> SentenceTransformer:
    """Load (and cache) the embedding model. Avoids reloading it on every call."""
    model_name = model_name or os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
    if model_name not in _model_cache:
        _model_cache[model_name] = SentenceTransformer(model_name)
    return _model_cache[model_name]


def embed_texts(texts: list[str], model_name: str | None = None) -> list[list[float]]:
    """Embed a batch of chunk texts (used at index-build time)."""
    model = get_embedder(model_name)
    return model.encode(texts, show_progress_bar=False).tolist()


def embed_query(text: str, model_name: str | None = None) -> list[float]:
    """Embed a single query string (used at retrieval time)."""
    model = get_embedder(model_name)
    return model.encode([text], show_progress_bar=False)[0].tolist()