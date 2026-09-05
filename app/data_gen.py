"""
Generates deliberately messy synthetic data across three sources:
bank statements, internal ledger, payment gateway payouts.

Injects the failure modes judges will look for:
- duplicate txn IDs
- merchant name string variants
- timezone-shifted timestamps
- missing tax IDs / ref IDs
- a few completely orphaned records (no match possible)
- a couple of malformed records that should fail schema validation
"""

import json
import random
from datetime import datetime, timedelta, timezone

random.seed(42)

MERCHANT_VARIANTS = [
    ("Razorpay Software Pvt Ltd", "Razorpay*Pvt Ltd"),
    ("Amazon Web Services India", "AWS India Pvt Ltd"),
    ("Zomato Media Pvt Ltd", "Zomato*Media"),
    ("Uber India Systems", "UBER *TRIP"),
    ("Swiggy Bundl Technologies", "Swiggy-Bundl Tech"),
]

N_RECORDS = 55


def _base_time(i: int) -> datetime:
    return datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc) + timedelta(hours=i * 3)


def generate() -> dict:
    bank, ledger, payouts, malformed = [], [], [], []

    for i in range(N_RECORDS):
        canonical, variant = random.choice(MERCHANT_VARIANTS)
        amount = round(random.uniform(500, 85000), 2)
        ts = _base_time(i)
        txn_id = f"TXN{1000 + i}"
        batch_id = f"BATCH{100 + i // 10}"

        bank_rec = {
            "source": "bank_statement",
            "record_id": f"BANK-{i}",
            "txn_id": txn_id,
            "amount": amount,
            "merchant_name": canonical,
            "description": f"Settlement for {canonical}",
            "timestamp": ts.isoformat(),
            "batch_id": batch_id,
        }

        # ~15% of ledger amounts drift slightly (rounding / fee deduction)
        ledger_amount = amount if random.random() > 0.15 else round(amount - random.uniform(1, 60), 2)
        # ~20% of ledger timestamps drift by a timezone offset
        ledger_ts = ts if random.random() > 0.2 else ts + timedelta(hours=random.choice([-5, -4, 5, 5.5]))

        ledger_rec = {
            "source": "internal_ledger",
            "record_id": f"LEDGER-{i}",
            "txn_id": txn_id,
            "invoice_number": f"INV-{2000 + i}",
            "amount": ledger_amount,
            "merchant_name": variant,  # string variant, not canonical
            "description": f"Payout ref {variant}",
            "timestamp": ledger_ts.isoformat(),
            "tax_id": f"GSTIN{3000+i}" if random.random() > 0.1 else None,  # 10% missing tax id
            "batch_id": batch_id,
        }

        payout_rec = {
            "source": "payment_gateway",
            "record_id": f"PAYOUT-{i}",
            "txn_id": txn_id,
            "amount": amount,
            "merchant_name": canonical,
            "description": f"Gateway payout {canonical}",
            "timestamp": ts.isoformat(),
            "batch_id": batch_id,
        }

        bank.append(bank_rec)
        ledger.append(ledger_rec)
        payouts.append(payout_rec)

    # Duplicate txn id injection (2 records)
    for i in [5, 30]:
        dup = dict(bank[i])
        dup["record_id"] = f"BANK-DUP-{i}"
        bank.append(dup)

    # Orphaned records with no counterpart (3 records) — will land in Exception Ledger
    for i in range(3):
        payouts.append({
            "source": "payment_gateway",
            "record_id": f"PAYOUT-ORPHAN-{i}",
            "txn_id": f"TXN-ORPHAN-{i}",
            "amount": round(random.uniform(500, 5000), 2),
            "merchant_name": "Unknown Vendor Corp",
            "description": "Unmatched payout",
            "timestamp": _base_time(N_RECORDS + i).isoformat(),
            "batch_id": "BATCH-ORPHAN",
        })

    # Malformed records that should fail Pydantic validation on ingestion
    malformed = [
        {"source": "bank_statement", "record_id": "", "amount": 100, "timestamp": "2026-08-01T10:00:00Z"},
        {"source": "internal_ledger", "record_id": "LEDGER-BAD-1", "amount": 0, "timestamp": "2026-08-01T10:00:00Z"},
        {"source": "payment_gateway", "record_id": "PAYOUT-BAD-1", "amount": "not_a_number", "timestamp": "2026-08-01T10:00:00Z"},
    ]

    return {"bank": bank, "ledger": ledger, "payouts": payouts, "malformed": malformed}


if __name__ == "__main__":
    data = generate()
    with open("synthetic_data.json", "w") as f:
        json.dump(data, f, indent=2)
    print(f"Generated {len(data['bank'])} bank, {len(data['ledger'])} ledger, "
          f"{len(data['payouts'])} payout, {len(data['malformed'])} malformed records "
          f"-> synthetic_data.json")
