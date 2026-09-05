"""
Tax-Line Matcher — ChromaDB version.

This is the literal vector-store implementation from the original
architecture doc (ChromaDB/FAISS RAG over tax codes), as opposed to the
TF-IDF fallback in app/tax_matcher.py.

Known risk: ChromaDB's default embedding function downloads a small ONNX
model (~90MB) from the internet on first use. On a flaky connection or a
sandboxed/offline environment this download can fail or come back
corrupted — confirmed while building this, not hypothetical. If that
happens here, `app/main.py` catches it and falls back to the TF-IDF
matcher automatically, so the tax endpoint stays up either way.

Same confidence-gate contract as the TF-IDF version: below threshold,
flag for review, never force a classification.
"""

import chromadb

from app.tax_rules import TAX_RULES

CLASSIFICATION_THRESHOLD = 0.35  # Chroma similarity scores run differently than TF-IDF cosine

_client = chromadb.Client()
_collection = _client.get_or_create_collection(name="tax_rules")

if _collection.count() == 0:
    _collection.add(
        ids=[r["tax_code"] for r in TAX_RULES],
        documents=[f"{r['category']}. {r['description']}" for r in TAX_RULES],
        metadatas=[{"category": r["category"]} for r in TAX_RULES],
    )

_rules_by_code = {r["tax_code"]: r for r in TAX_RULES}


def classify_transaction(description: str, merchant_name: str = "") -> dict:
    """Classify a single transaction's tax line via ChromaDB vector similarity."""
    query = f"{merchant_name} {description}".strip()
    if not query:
        return {
            "tax_code": None,
            "category": None,
            "confidence": 0.0,
            "needs_review": True,
            "review_reason": "No description or merchant name to classify against.",
        }

    results = _collection.query(query_texts=[query], n_results=1)
    if not results["ids"][0]:
        return {
            "tax_code": None,
            "category": None,
            "confidence": 0.0,
            "needs_review": True,
            "review_reason": "No candidates returned from vector store.",
        }

    best_id = results["ids"][0][0]
    distance = results["distances"][0][0]
    # Chroma returns a distance (lower = closer); convert to a 0-1-ish similarity
    similarity = 1.0 / (1.0 + distance)

    if similarity < CLASSIFICATION_THRESHOLD:
        return {
            "tax_code": None,
            "category": None,
            "confidence": round(similarity, 3),
            "needs_review": True,
            "review_reason": f"Best match scored {similarity:.3f}, below "
                              f"{CLASSIFICATION_THRESHOLD} threshold — no confident category found.",
        }

    rule = _rules_by_code[best_id]
    return {
        "tax_code": rule["tax_code"],
        "category": rule["category"],
        "confidence": round(similarity, 3),
        "needs_review": False,
        "review_reason": None,
    }


def classify_batch(records: list[dict]) -> list[dict]:
    """Classify a batch of ledger records via the ChromaDB vector store."""
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
