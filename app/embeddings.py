import logging

import httpx

from .config import settings

log = logging.getLogger("embeddings")
BATCH = 32


def embed(texts: list[str]) -> list[list[float]] | None:
    """Return embeddings, or None if embeddings are disabled/unavailable.
    Callers fall back to keyword search, so the server still works without a model."""
    if not texts or settings.embed_provider == "none":
        return None
    out: list[list[float]] = []
    try:
        for i in range(0, len(texts), BATCH):
            r = httpx.post(
                f"{settings.ollama_url}/api/embed",
                json={"model": settings.embed_model, "input": texts[i:i + BATCH]},
                timeout=120,
            )
            r.raise_for_status()
            out.extend(r.json()["embeddings"])
        if out and len(out[0]) != settings.embed_dim:
            raise ValueError(f"model returned dim {len(out[0])}, EMBED_DIM={settings.embed_dim}")
        return out
    except Exception as e:  # noqa: BLE001
        log.warning("embedding unavailable: %s", e)
        return None
