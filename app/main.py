"""
FastAPI entrypoint.

Endpoints:
  POST /ingest/run-synthetic   -> generates + ingests synthetic batch, runs reconciliation
  GET  /summary                -> aggregate match rate + counts ("The Bar")
  GET  /reconciled             -> full reconciled ledger
  GET  /exceptions             -> full exception ledger
  GET  /forecast?days=7        -> cash forecast off reconciled data
  GET  /query/batch/{batch_id} -> everything tied to a batch (for Q&A agent tool)
"""

import time

from fastapi import FastAPI, HTTPException
from pydantic import ValidationError

from app.data_gen import generate
from app.db import store
from app.forecaster import daily_net_cash, forecast_next_n_days
from app.reconciliation import ReconciliationEngine
from app.schemas import RawRecordIn, RejectedRecord

app = FastAPI(title="AI Finance Controller")


def _validate_batch(records: list[dict]) -> tuple[list[dict], list[RejectedRecord]]:
    good, rejected = [], []
    for rec in records:
        try:
            RawRecordIn(**rec)  # validate shape; keep original dict for matching logic
            good.append(rec)
        except ValidationError as e:
            rejected.append(RejectedRecord(raw_payload=rec, error=str(e)))
    return good, rejected


@app.post("/ingest/run-synthetic")
def run_synthetic():
    start_time = time.perf_counter()

    data = generate()

    bank, rej_bank = _validate_batch(data["bank"])
    ledger, rej_ledger = _validate_batch(data["ledger"])
    payouts, rej_payouts = _validate_batch(data["payouts"])
    _, rej_malformed = _validate_batch(data["malformed"])

    store.rejected = rej_bank + rej_ledger + rej_payouts + rej_malformed
    store.load_raw(bank, ledger, payouts)

    engine = ReconciliationEngine(bank, ledger, payouts)
    reconciled, exceptions = engine.run()
    store.save_reconciliation_results(reconciled, exceptions)
    store.name_match_engine = engine.name_match_engine

    elapsed_seconds = time.perf_counter() - start_time
    total_records = len(bank) + len(ledger) + len(payouts)
    store.throughput = {
        "total_records_ingested": total_records,
        "processing_time_seconds": round(elapsed_seconds, 3),
        "records_per_second": round(total_records / elapsed_seconds, 1) if elapsed_seconds > 0 else None,
    }

    return {
        "ingested": {"bank": len(bank), "ledger": len(ledger), "payouts": len(payouts)},
        "rejected_on_validation": len(store.rejected),
        "throughput": store.throughput,
        **store.summary(),
    }


@app.get("/summary")
def summary():
    return store.summary()


@app.get("/reconciled")
def reconciled():
    return [r.model_dump() for r in store.reconciled]


@app.get("/exceptions")
def exceptions():
    return [e.model_dump() for e in store.exceptions]


@app.get("/rejected")
def rejected():
    return [r.model_dump() for r in store.rejected]


@app.get("/forecast")
def forecast(days: int = 7):
    bank_by_id = {r["record_id"]: r for r in store.raw_bank}
    daily = daily_net_cash(store.reconciled, bank_by_id)
    return forecast_next_n_days(daily, n_days=days)


@app.get("/tax/classify")
def tax_classify():
    """Classify every ledger record's tax line against the tax rule corpus.
    Flags low-confidence matches and missing tax IDs for manual review —
    never force-classifies below the confidence threshold.

    Cached after the first call per ingestion run — this used to recompute
    from scratch on every request, which meant every Streamlit rerun (e.g.
    every keystroke in the Q&A chat box) re-ran ChromaDB embedding inference
    over the whole ledger. That's now fixed: computed once, served from
    cache until the next /ingest/run-synthetic call.

    Tries the ChromaDB vector-store matcher first (the architecture doc's
    literal spec); falls back to the TF-IDF matcher if ChromaDB fails to
    initialize or query (e.g. its embedding model couldn't download) so
    this endpoint never goes down over a dependency hiccup."""
    if store.tax_classification_cache is not None:
        return store.tax_classification_cache

    engine_used = "chromadb"
    try:
        from app.tax_matcher_chroma import classify_batch as classify_batch_chroma
        results = classify_batch_chroma(store.raw_ledger)
    except Exception:
        from app.tax_matcher import classify_batch as classify_batch_tfidf
        results = classify_batch_tfidf(store.raw_ledger)
        engine_used = "tfidf_fallback"

    needs_review = [r for r in results if r["needs_review"] or r["missing_tax_id"]]
    response = {
        "engine_used": engine_used,
        "total_classified": len(results),
        "needs_review_count": len(needs_review),
        "results": results,
    }
    store.tax_classification_cache = response
    return response


@app.get("/query/batch/{batch_id}")
def query_batch(batch_id: str):
    """Everything tied to a batch_id — reconciled matches + exceptions.
    This is the tool the Settlement Q&A Agent calls to answer batch-specific
    questions, e.g. 'why did batch #1042 have a variance?'."""

    bank_by_id = {r["record_id"]: r for r in store.raw_bank}

    matched = [
        r.model_dump() for r in store.reconciled
        if bank_by_id.get(r.bank_record_id, {}).get("batch_id") == batch_id
    ]

    all_raw_ids_in_batch = {
        r["record_id"] for r in store.raw_bank + store.raw_ledger + store.raw_payouts
        if r.get("batch_id") == batch_id
    }
    batch_exceptions = [
        e.model_dump() for e in store.exceptions
        if e.record_id in all_raw_ids_in_batch
    ]

    if not matched and not batch_exceptions:
        raise HTTPException(status_code=404, detail=f"No records found for batch_id {batch_id}")

    return {"batch_id": batch_id, "reconciled": matched, "exceptions": batch_exceptions}
