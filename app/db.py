"""
In-memory store for the demo. Swap for Postgres/SQLite later without
touching the reconciliation or agent logic — everything talks to this
interface, not to raw dicts.
"""

from app.schemas import ExceptionRecord, ReconciledRecord, RejectedRecord


class Store:
    def __init__(self):
        self.reconciled: list[ReconciledRecord] = []
        self.exceptions: list[ExceptionRecord] = []
        self.rejected: list[RejectedRecord] = []
        self.raw_bank: list[dict] = []
        self.raw_ledger: list[dict] = []
        self.raw_payouts: list[dict] = []
        self.tax_classification_cache: dict | None = None  # computed once per ingestion run
        self.name_match_engine: str = "unknown"
        self.throughput: dict | None = None

    def load_raw(self, bank: list[dict], ledger: list[dict], payouts: list[dict]):
        self.raw_bank = bank
        self.raw_ledger = ledger
        self.raw_payouts = payouts
        self.tax_classification_cache = None  # invalidate — new batch needs fresh classification

    def save_reconciliation_results(self, reconciled: list[ReconciledRecord], exceptions: list[ExceptionRecord]):
        self.reconciled = reconciled
        self.exceptions = exceptions

    # ---- metrics ----
    def match_rate(self) -> float:
        total = len(self.reconciled) + len(self.exceptions)
        if total == 0:
            return 0.0
        return round(len(self.reconciled) / total * 100, 2)

    def summary(self) -> dict:
        return {
            "total_records_processed": len(self.reconciled) + len(self.exceptions),
            "reconciled_count": len(self.reconciled),
            "exception_count": len(self.exceptions),
            "rejected_count": len(self.rejected),
            "match_rate_pct": self.match_rate(),
            "name_match_engine": self.name_match_engine,
            "throughput": self.throughput,
        }


# module-level singleton for the demo — fine for a hackathon, not for prod
store = Store()
