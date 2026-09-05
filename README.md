# AI Finance Controller

All-in-one reconciliation, forecasting, tax-matching, and Q&A system for
finance ops. 

## What's here (working)

- **Synthetic data generator** (`app/data_gen.py`) — 55+ records across bank
  statements, internal ledger, and payment gateway payouts, deliberately
  dirty: duplicate txn IDs, merchant name string variants, amount drift,
  timezone-shifted timestamps, missing tax IDs, orphaned records, and a few
  malformed payloads that should fail validation.
- **Ingestion & validation** (`app/schemas.py`) — strict Pydantic models.
  Anything malformed is rejected at the door, not silently dropped.
- **Two-pass reconciliation engine** (`app/reconciliation.py`) — exact match
  first, then fuzzy (merchant name + amount + timestamp scoring) for the
  leftovers. 95% confidence threshold — below it, no forced match, goes to
  the Exception Ledger with a specific reason code.
- **Cash forecaster** (`app/forecaster.py`) — linear regression over
  reconciled daily net cash. Deliberately simple; upgrade to Prophet later
  if there's time.
- **Settlement Q&A Agent** (`app/qa_agent.py`) — Claude tool-calling loop
  over the FastAPI query endpoints. Answers only from tool results, never
  guesses numbers.
- **FastAPI backend** (`app/main.py`) — ties it all together.
- **Streamlit dashboard** (`dashboard.py`) — split-screen: match rate +
  exception ledger on the left, Q&A chat on the right.



- **LangGraph orchestration** — `app/langgraph_agent.py` uses LangGraph's
  `create_react_agent` as the coordinator, matching the original
  architecture doc. `app/qa_agent.py` (a direct Gemini tool-calling loop)
  is kept as an automatic fallback — if LangGraph's dependencies aren't
  installed or fail to initialize, the dashboard silently falls back to
  it rather than breaking the Q&A panel.
- **ChromaDB tax matcher** — `app/tax_matcher_chroma.py` implements the
  vector-store RAG spec literally. `app/tax_matcher.py` (TF-IDF) is the
  automatic fallback — ChromaDB's default embedding model downloads a
  ~90MB file on first use, and that download can fail on a flaky or
  sandboxed connection (confirmed while building this, not hypothetical).
  `/tax/classify` tries Chroma first and falls back on any exception; the
  response includes `"engine_used"` so you can see which one actually ran.

## Setup

```bash
pip install -r requirements.txt
export GEMINI_API_KEY=your_key_here   # only needed for the Q&A agent
```

## Run

Terminal 1 — backend:
```bash
uvicorn app.main:app --reload
```

Terminal 2 — dashboard:
```bash
streamlit run dashboard.py
```

Then in the dashboard, click **"Run ingestion + reconciliation on synthetic
batch"**. This populates everything else.

## Verify the pipeline directly (no server needed)

```bash
python3 -c "
from app.data_gen import generate
from app.reconciliation import ReconciliationEngine
data = generate()
engine = ReconciliationEngine(data['bank'], data['ledger'], data['payouts'])
reconciled, exceptions = engine.run()
print(f'{len(reconciled)} reconciled, {len(exceptions)} exceptions, '
      f'{len(reconciled)/(len(reconciled)+len(exceptions))*100:.1f}% match rate')
"
```

## API endpoints

| Endpoint | Purpose |
|---|---|
| `POST /ingest/run-synthetic` | generate + ingest + reconcile a fresh batch |
| `GET /summary` | match rate, counts — "The Bar" metrics |
| `GET /reconciled` | full reconciled ledger |
| `GET /exceptions` | full exception ledger with reason codes |
| `GET /forecast?days=7` | cash projection off reconciled data |
| `GET /query/batch/{batch_id}` | everything tied to a batch — the Q&A agent's main tool |

