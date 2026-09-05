"""
Forward Cash Forecaster.

Uses Holt's linear exponential smoothing (double exponential smoothing with
trend) via statsmodels — a genuine time-series method, not just a straight
line fit. Chosen over full seasonal ARIMA/SARIMA because the reconciled
history here spans about a week; ARIMA's seasonal component needs multiple
full cycles of history to mean anything, and claiming a seasonal model on
data that can't support one would be the same kind of overclaim this whole
system is built to avoid. Holt's method still captures level + trend
properly, weighting recent observations more than a plain least-squares
line does.

Falls back to plain linear regression when there isn't enough history for
smoothing to fit meaningfully (fewer than 4 points) or if statsmodels
raises for any reason — same fallback-with-visibility pattern as the tax
matcher and reconciliation name-scoring elsewhere in this app.
"""

from collections import defaultdict
from datetime import datetime, timedelta

import numpy as np

from app.schemas import ReconciledRecord

MIN_POINTS_FOR_SMOOTHING = 4


def daily_net_cash(reconciled: list[ReconciledRecord], bank_by_id: dict) -> dict[str, float]:
    daily = defaultdict(float)
    for r in reconciled:
        bank_rec = bank_by_id.get(r.bank_record_id)
        if not bank_rec:
            continue
        day = bank_rec["timestamp"][:10]  # YYYY-MM-DD
        daily[day] += r.amount
    return dict(sorted(daily.items()))


def _forecast_linear(values: np.ndarray, n_days: int) -> tuple[np.ndarray, float]:
    x = np.arange(len(values))
    coeffs = np.polyfit(x, values, 1)
    slope, intercept = coeffs[0], coeffs[1]
    future_x = np.arange(len(values), len(values) + n_days)
    return slope * future_x + intercept, float(slope)


def _forecast_holt(values: np.ndarray, n_days: int) -> tuple[np.ndarray, float, str]:
    from statsmodels.tsa.holtwinters import ExponentialSmoothing

    model = ExponentialSmoothing(values, trend="add", damped_trend=True, seasonal=None)
    fit = model.fit(optimized=True)
    future_values = fit.forecast(n_days)
    # approximate slope for the trend/day field: difference between first and last
    # forecast point, spread across the horizon — informational, not the fit itself
    slope = float((future_values[-1] - future_values[0]) / max(n_days - 1, 1))
    return np.array(future_values), slope, "holt_exponential_smoothing"


def forecast_next_n_days(daily: dict[str, float], n_days: int = 7) -> dict:
    if len(daily) < 2:
        return {"error": "Not enough reconciled history to forecast."}

    dates = list(daily.keys())
    values = np.array(list(daily.values()))
    last_date = datetime.fromisoformat(dates[-1])

    basis = "linear regression over reconciled daily net cash movement (fallback)"
    if len(values) >= MIN_POINTS_FOR_SMOOTHING:
        try:
            future_values, slope, method = _forecast_holt(values, n_days)
            basis = "Holt's linear exponential smoothing (trend, damped) over reconciled daily net cash movement"
        except Exception:
            future_values, slope = _forecast_linear(values, n_days)
    else:
        future_values, slope = _forecast_linear(values, n_days)

    projection = {
        (last_date + timedelta(days=i + 1)).strftime("%Y-%m-%d"): round(float(v), 2)
        for i, v in enumerate(future_values)
    }

    cumulative_runway = round(float(np.sum(future_values)), 2)

    return {
        "daily_projection": projection,
        "projected_cumulative_next_n_days": cumulative_runway,
        "trend_slope_per_day": round(slope, 2),
        "basis": basis,
        "days_of_history_used": len(daily),
    }
