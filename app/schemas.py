"""
Pydantic schemas for the AI Finance Controller.

Design principle: validate hard at the boundary. Anything that doesn't fit
the schema gets routed to `rejects`, not silently dropped and not allowed
to crash the pipeline.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class SourceType(str, Enum):
    BANK_STATEMENT = "bank_statement"
    INTERNAL_LEDGER = "internal_ledger"
    PAYMENT_GATEWAY = "payment_gateway"


class RawRecordIn(BaseModel):
    """What comes in over the wire from any of the three sources."""

    source: SourceType
    record_id: str
    txn_id: Optional[str] = None
    invoice_number: Optional[str] = None
    amount: float
    currency: str = "INR"
    merchant_name: Optional[str] = None
    description: Optional[str] = None
    timestamp: datetime
    tax_id: Optional[str] = None
    batch_id: Optional[str] = None

    @field_validator("amount")
    @classmethod
    def amount_must_be_reasonable(cls, v: float) -> float:
        if v == 0:
            raise ValueError("amount cannot be zero")
        return round(v, 2)

    @field_validator("record_id")
    @classmethod
    def record_id_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("record_id cannot be blank")
        return v.strip()


class RejectedRecord(BaseModel):
    """A record that failed schema validation on ingestion."""

    raw_payload: dict
    error: str
    rejected_at: datetime = Field(default_factory=datetime.utcnow)


class MatchTier(str, Enum):
    DETERMINISTIC = "deterministic"
    FUZZY = "fuzzy"


class ReconciledRecord(BaseModel):
    """A confirmed match, written to the Reconciled Ledger DB."""

    match_id: str
    bank_record_id: Optional[str] = None
    ledger_record_id: Optional[str] = None
    payout_record_id: Optional[str] = None
    amount: float
    confidence: float
    match_tier: MatchTier
    matched_at: datetime = Field(default_factory=datetime.utcnow)


class ExceptionReason(str, Enum):
    AMOUNT_MISMATCH = "AMOUNT_MISMATCH"
    MISSING_BANK_REF_ID = "MISSING_BANK_REF_ID"
    DUPLICATE_TXN_ID = "DUPLICATE_TXN_ID"
    NO_CANDIDATE_FOUND = "NO_CANDIDATE_FOUND"
    LOW_CONFIDENCE_MATCH = "LOW_CONFIDENCE_MATCH"
    TIMESTAMP_OUT_OF_WINDOW = "TIMESTAMP_OUT_OF_WINDOW"
    MISSING_TAX_ID = "MISSING_TAX_ID"


class ExceptionRecord(BaseModel):
    """An unresolved record, written to the Exception Ledger with a reason."""

    exception_id: str
    record_id: str
    source: SourceType
    reason_code: ExceptionReason
    reason_detail: str
    best_candidate_id: Optional[str] = None
    best_candidate_confidence: Optional[float] = None
    logged_at: datetime = Field(default_factory=datetime.utcnow)
