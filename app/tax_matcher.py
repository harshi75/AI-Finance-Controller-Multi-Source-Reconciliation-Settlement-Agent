"""
Tax-Line Matcher.

RAG-style retrieval over a small tax rule corpus: embed the corpus with
TF-IDF, embed each transaction description the same way, retrieve the
closest tax rule by cosine similarity. This is deliberately TF-IDF instead
of a vector DB (ChromaDB/FAISS) + embedding API — same retrieval pattern,
but zero extra install risk and zero API cost, which matters more than the
embedding quality for a hackathon demo. Swappable for ChromaDB later
without changing the calling code (see `classify_transaction`'s signature).

Confidence gate mirrors the reconciliation engine: below threshold, don't
force a classification — flag for manual review instead.
"""

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.tax_rules import TAX_RULES

CLASSIFICATION_THRESHOLD = 0.15  # TF-IDF cosine scores run lower than embedding scores

_corpus_texts = [f"{r['category']}. {r['description']}" for r in TAX_RULES]
_vectorizer = TfidfVectorizer(stop_words="english")
_corpus_matrix = _vectorizer.fit_transform(_corpus_texts)


def classify_transaction(description: str, merchant_name: str = "") -> dict:
    """Classify a single transaction's tax line against the rule corpus.

    Returns the best-matching tax code + confidence, or a flag for manual
    review if nothing clears the threshold.
    """
    query = f"{merchant_name} {description}".strip()
    if not query:
        return {
            "tax_code": None,
            "category": None,
            "confidence": 0.0,
            "needs_review": True,
            "review_reason": "No description or merchant name to classify against.",
        }

    query_vec = _vectorizer.transform([query])
    scores = cosine_similarity(query_vec, _corpus_matrix)[0]
    best_idx = scores.argmax()
    best_score = float(scores[best_idx])

    if best_score < CLASSIFICATION_THRESHOLD:
        return {
            "tax_code": None,
            "category": None,
            "confidence": round(best_score, 3),
            "needs_review": True,
            "review_reason": f"Best match scored {best_score:.3f}, below "
                              f"{CLASSIFICATION_THRESHOLD} threshold — no confident category found.",
        }

    rule = TAX_RULES[best_idx]
    return {
        "tax_code": rule["tax_code"],
        "category": rule["category"],
        "confidence": round(best_score, 3),
        "needs_review": False,
        "review_reason": None,
    }


def classify_batch(records: list[dict]) -> list[dict]:
    """Classify a batch of reconciled/ledger records. Each record should have
    'record_id', 'description' (or 'merchant_name'), and optionally 'tax_id'.

    Also flags records with a missing tax_id, independent of classification
    confidence — a present tax_id doesn't excuse a low-confidence category
    match, and vice versa.
    """
    results = []
    for rec in records:
        classification = classify_transaction(
            description=rec.get("description", ""),
            merchant_name=rec.get("merchant_name", ""),
        )
        missing_tax_id = not rec.get("tax_id")
        results.append({
            "record_id": rec.get("record_id"),
            **classification,
            "missing_tax_id": missing_tax_id,
        })
    return results
