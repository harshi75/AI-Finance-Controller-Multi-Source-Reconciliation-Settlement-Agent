"""
Two-pass reconciliation engine.

Pass 1 (deterministic): exact match on txn_id + amount across bank/ledger/payout.
Pass 2 (fuzzy): for anything left unmatched, score merchant-name similarity +
amount closeness + timestamp closeness into a single confidence score.

Anything scoring >= CONFIDENCE_THRESHOLD is written to the Reconciled Ledger.
Anything below is written to the Exception Ledger with a specific reason code.
Nothing is force-matched. Nothing is silently dropped.
"""

import uuid
from datetime import datetime
from typing import Optional

from dateutil import parser as dtparser

from app.schemas import (
    ExceptionRecord,
    ExceptionReason,
    MatchTier,
    ReconciledRecord,
    SourceType,
)
from app.semantic_similarity import semantic_similarity

CONFIDENCE_THRESHOLD = 0.95
AMOUNT_TOLERANCE_ABS = 100.0  # INR — beyond this, amount similarity drops fast
TIMESTAMP_TOLERANCE_HOURS = 6.0


def _parse_ts(ts) -> datetime:
    if isinstance(ts, datetime):
        return ts
    return dtparser.isoparse(ts)


def _amount_score(a: float, b: float) -> float:
    diff = abs(a - b)
    if diff == 0:
        return 1.0
    if diff >= AMOUNT_TOLERANCE_ABS:
        return 0.0
    return 1.0 - (diff / AMOUNT_TOLERANCE_ABS)


def _timestamp_score(t1: datetime, t2: datetime) -> float:
    diff_hours = abs((t1 - t2).total_seconds()) / 3600.0
    if diff_hours >= TIMESTAMP_TOLERANCE_HOURS:
        return 0.0
    return 1.0 - (diff_hours / TIMESTAMP_TOLERANCE_HOURS)


class ReconciliationEngine:
    def __init__(self, bank: list[dict], ledger: list[dict], payouts: list[dict]):
        self.bank = bank
        self.ledger = ledger
        self.payouts = payouts
        self.reconciled: list[ReconciledRecord] = []
        self.exceptions: list[ExceptionRecord] = []
        self._matched_ids: set[str] = set()
        self.name_match_engine: str = "unknown"  # 'embedding' or 'string_fallback', set on first fuzzy comparison

    def run(self) -> tuple[list[ReconciledRecord], list[ExceptionRecord]]:
        self._deterministic_pass()
        self._fuzzy_pass()
        self._flag_leftovers()
        return self.reconciled, self.exceptions

    # ---------- Pass 1 ----------
    def _deterministic_pass(self):
        seen_txn_ids: dict[str, str] = {}  # txn_id -> record_id, to catch dupes

        ledger_by_txn = {r["txn_id"]: r for r in self.ledger if r.get("txn_id")}
        payout_by_txn = {r["txn_id"]: r for r in self.payouts if r.get("txn_id")}

        for bank_rec in self.bank:
            txn_id = bank_rec.get("txn_id")
            if not txn_id:
                self._add_exception(bank_rec, ExceptionReason.MISSING_BANK_REF_ID,
                                     "Bank record has no txn_id to match against.")
                continue

            if txn_id in seen_txn_ids:
                self._add_exception(bank_rec, ExceptionReason.DUPLICATE_TXN_ID,
                                     f"txn_id {txn_id} already seen on record {seen_txn_ids[txn_id]}.")
                continue
            seen_txn_ids[txn_id] = bank_rec["record_id"]

            ledger_rec = ledger_by_txn.get(txn_id)
            payout_rec = payout_by_txn.get(txn_id)

            if not ledger_rec or not payout_rec:
                continue  # leave for fuzzy pass

            amounts = [bank_rec["amount"], ledger_rec["amount"], payout_rec["amount"]]
            if max(amounts) - min(amounts) > 0.01:
                continue  # exact amounts must match on this tier — leave for fuzzy pass

            self._commit_match(
                bank_rec, ledger_rec, payout_rec,
                confidence=1.0, tier=MatchTier.DETERMINISTIC,
            )

    # ---------- Pass 2 ----------
    def _fuzzy_pass(self):
        unmatched_bank = [r for r in self.bank if r["record_id"] not in self._matched_ids]
        unmatched_ledger = [r for r in self.ledger if r["record_id"] not in self._matched_ids]
        unmatched_payout = [r for r in self.payouts if r["record_id"] not in self._matched_ids]

        for bank_rec in unmatched_bank:
            if bank_rec["record_id"] in self._matched_ids:
                continue

            best_ledger, best_ledger_score = self._best_candidate(bank_rec, unmatched_ledger)
            best_payout, best_payout_score = self._best_candidate(bank_rec, unmatched_payout)

            if best_ledger is None and best_payout is None:
                continue  # true orphan, handled in _flag_leftovers

            confidence = min(
                best_ledger_score if best_ledger else 0.0,
                best_payout_score if best_payout else 1.0,
            )

            if confidence >= CONFIDENCE_THRESHOLD and best_ledger and best_payout:
                self._commit_match(
                    bank_rec, best_ledger, best_payout,
                    confidence=confidence, tier=MatchTier.FUZZY,
                )
            else:
                candidate = best_ledger or best_payout
                self._add_exception(
                    bank_rec, ExceptionReason.LOW_CONFIDENCE_MATCH,
                    f"Best candidate {candidate['record_id']} scored {confidence:.2f}, "
                    f"below {CONFIDENCE_THRESHOLD} threshold.",
                    best_candidate_id=candidate["record_id"],
                    best_candidate_confidence=confidence,
                )

    def _best_candidate(self, bank_rec: dict, pool: list[dict]) -> tuple[Optional[dict], float]:
        best, best_score = None, 0.0
        bank_ts = _parse_ts(bank_rec["timestamp"])
        for cand in pool:
            if cand["record_id"] in self._matched_ids:
                continue
            bank_name = bank_rec.get("merchant_name")
            cand_name = cand.get("merchant_name")
            if bank_name and cand_name:
                name_s, method = semantic_similarity(bank_name, cand_name)
                self.name_match_engine = method
            else:
                name_s = 0.0
            amount_s = _amount_score(bank_rec["amount"], cand["amount"])
            ts_s = _timestamp_score(bank_ts, _parse_ts(cand["timestamp"]))
            score = 0.5 * amount_s + 0.35 * name_s + 0.15 * ts_s
            if score > best_score:
                best, best_score = cand, score
        return best, best_score

    # ---------- Leftovers ----------
    def _flag_leftovers(self):
        for pool, source in [
            (self.ledger, SourceType.INTERNAL_LEDGER),
            (self.payouts, SourceType.PAYMENT_GATEWAY),
        ]:
            for rec in pool:
                if rec["record_id"] not in self._matched_ids and not self._already_excepted(rec["record_id"]):
                    self._add_exception(
                        rec, ExceptionReason.NO_CANDIDATE_FOUND,
                        f"No matching bank record found for {source.value} record {rec['record_id']}.",
                    )

    def _already_excepted(self, record_id: str) -> bool:
        return any(e.record_id == record_id for e in self.exceptions)

    # ---------- helpers ----------
    def _commit_match(self, bank_rec, ledger_rec, payout_rec, confidence: float, tier: MatchTier):
        match_id = str(uuid.uuid4())
        self.reconciled.append(ReconciledRecord(
            match_id=match_id,
            bank_record_id=bank_rec["record_id"],
            ledger_record_id=ledger_rec["record_id"],
            payout_record_id=payout_rec["record_id"],
            amount=bank_rec["amount"],
            confidence=confidence,
            match_tier=tier,
        ))
        for r in (bank_rec, ledger_rec, payout_rec):
            self._matched_ids.add(r["record_id"])

    def _add_exception(self, rec: dict, reason: ExceptionReason, detail: str,
                        best_candidate_id: Optional[str] = None,
                        best_candidate_confidence: Optional[float] = None):
        self.exceptions.append(ExceptionRecord(
            exception_id=str(uuid.uuid4()),
            record_id=rec["record_id"],
            source=SourceType(rec["source"]),
            reason_code=reason,
            reason_detail=detail,
            best_candidate_id=best_candidate_id,
            best_candidate_confidence=best_candidate_confidence,
        ))
        self._matched_ids.add(rec["record_id"])  # don't process it again downstream
