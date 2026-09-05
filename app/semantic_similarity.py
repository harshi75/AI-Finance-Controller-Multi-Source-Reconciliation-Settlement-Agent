"""
Semantic similarity for merchant-name matching in reconciliation.

Uses ChromaDB's embedding function (the same all-MiniLM-L6-v2 model already
a dependency via tax_matcher_chroma.py) to compute real semantic similarity
between merchant name strings — e.g. "Razorpay*Pvt Ltd" and "Razorpay
Software" are close in embedding space even where a plain string-distance
metric would only partially credit them for shared characters.

This replaces rapidfuzz's pure string-edit-distance scoring in
reconciliation.py's fuzzy pass with genuine embedding similarity, when
available. Falls back to rapidfuzz automatically if the embedding model
isn't available (no internet on first run, dependency missing, etc.) —
same fallback pattern used for the tax matcher, for the same reason.
"""

import numpy as np
from rapidfuzz import fuzz

_embedding_fn = None
_embedding_cache: dict[str, np.ndarray] = {}
_chroma_available = None  # None = not yet checked, True/False once determined


def _get_embedding_fn():
    global _embedding_fn, _chroma_available
    if _chroma_available is False:
        return None
    if _embedding_fn is not None:
        return _embedding_fn
    try:
        from chromadb.utils import embedding_functions
        _embedding_fn = embedding_functions.DefaultEmbeddingFunction()
        # smoke-test it immediately — if the model can't download, fail fast
        # and fall back, rather than failing later mid-reconciliation
        _embedding_fn(["smoke test"])
        _chroma_available = True
        return _embedding_fn
    except Exception:
        _chroma_available = False
        return None


def _embed(text: str) -> np.ndarray | None:
    if text in _embedding_cache:
        return _embedding_cache[text]
    fn = _get_embedding_fn()
    if fn is None:
        return None
    vec = np.array(fn([text])[0])
    _embedding_cache[text] = vec
    return vec


def semantic_similarity(a: str, b: str) -> tuple[float, str]:
    """Returns (similarity_score in [0,1], method_used).

    method_used is 'embedding' or 'string_fallback' — surfaced so callers
    (and the dashboard) can show which one actually ran, same transparency
    principle as the tax matcher's engine_used field.
    """
    if not a or not b:
        return 0.0, "string_fallback"

    vec_a = _embed(a)
    vec_b = _embed(b)
    if vec_a is not None and vec_b is not None:
        cosine = float(np.dot(vec_a, vec_b) / (np.linalg.norm(vec_a) * np.linalg.norm(vec_b) + 1e-10))
        # cosine similarity for sentence embeddings is typically 0.3-1.0 for
        # related text; clip and rescale so it plays nicely with the existing
        # 0-1 confidence blending in reconciliation.py
        similarity = max(0.0, min(1.0, cosine))
        return similarity, "embedding"

    # fallback: plain string similarity, same as the original rapidfuzz-only approach
    return fuzz.token_sort_ratio(a, b) / 100.0, "string_fallback"
