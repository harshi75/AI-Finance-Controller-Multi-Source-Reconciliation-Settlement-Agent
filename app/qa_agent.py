"""
Settlement Q&A Agent — Gemini version, using Google's current `google-genai` SDK.

(The old `google-generativeai` package is deprecated/EOL as of 2026 — this
uses its replacement.)

Requires GEMINI_API_KEY in the environment (free key from
https://aistudio.google.com/apikey).
"""

import os
import time

import requests
from google import genai
from google.genai import errors as genai_errors
from google.genai import types

API_BASE = "http://localhost:8000"

client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

SYSTEM_PROMPT = (
    "You are the Settlement Q&A Agent for a finance reconciliation system. "
    "Answer using ONLY data returned by your tools — never estimate or guess numbers. "
    "If a tool returns no data for a query, say so plainly rather than filling in a "
    "plausible-sounding answer. Keep answers concise and cite specific reason codes / "
    "record IDs when explaining exceptions."
)


import functools

_call_log: list[dict] = []


def _traced(fn):
    """Wraps a tool function to record its calls into _call_log, so the
    fallback agent can expose the same tool-call trace as the LangGraph
    version — proof of real tool use regardless of which orchestration
    path actually ran."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        result = fn(*args, **kwargs)
        _call_log.append({"tool": fn.__name__, "args": kwargs or dict(zip(fn.__code__.co_varnames, args)), "result": result})
        return result
    return wrapper


@_traced
def get_summary() -> dict:
    """Get aggregate match rate and record counts across the whole reconciliation run."""
    return requests.get(f"{API_BASE}/summary", timeout=10).json()


@_traced
def query_batch(batch_id: str) -> dict:
    """Get all reconciled matches and exceptions for a specific batch_id.
    Use this for questions about why a specific batch had variance or issues.

    Args:
        batch_id: The batch identifier, e.g. BATCH100
    """
    resp = requests.get(f"{API_BASE}/query/batch/{batch_id}", timeout=10)
    return resp.json() if resp.ok else {"error": resp.json().get("detail", "not found")}


@_traced
def get_forecast(days: int = 7) -> dict:
    """Get the projected cash position for the next N days, based on reconciled ledger data.

    Args:
        days: How many days to project. Default 7.
    """
    return requests.get(f"{API_BASE}/forecast", params={"days": days}, timeout=10).json()


@_traced
def list_exceptions() -> list:
    """Get the full exception ledger — every record that failed reconciliation, with reason codes."""
    return requests.get(f"{API_BASE}/exceptions", timeout=10).json()


@_traced
def get_tax_classifications() -> dict:
    """Get tax code classifications for every ledger transaction, including which
    ones need manual review due to low confidence or a missing tax ID."""
    return requests.get(f"{API_BASE}/tax/classify", timeout=10).json()


TOOL_FUNCTIONS = [get_summary, query_batch, get_forecast, list_exceptions, get_tax_classifications]


def ask(question: str, max_retries: int = 3) -> str:
    answer, _trace = ask_with_trace(question, max_retries=max_retries)
    return answer


def ask_with_trace(question: str, max_retries: int = 3) -> tuple[str, list[dict]]:
    _call_log.clear()
    chat = client.chats.create(
        model="gemini-3.6-flash",
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            tools=TOOL_FUNCTIONS,  # google-genai auto-calls plain python functions
        ),
    )

    last_error = None
    for attempt in range(max_retries):
        try:
            response = chat.send_message(question)
            return response.text, list(_call_log)
        except genai_errors.ClientError as e:
            last_error = e
            is_rate_limit = getattr(e, "code", None) == 429 or "RESOURCE_EXHAUSTED" in str(e)
            if is_rate_limit and attempt < max_retries - 1:
                wait = 2 ** (attempt + 2)  # 4s, 8s, 16s
                time.sleep(wait)
                continue
            break

    if last_error is not None and (
        getattr(last_error, "code", None) == 429 or "RESOURCE_EXHAUSTED" in str(last_error)
    ):
        return (
            "Gemini's free-tier rate limit is hit right now — this is a quota issue, "
            "not a system failure. The underlying data (match rate, exceptions, forecast, "
            "tax classifications) is all still correct and viewable on the dashboard; "
            "give it a minute and ask again."
        ), []
    return f"Something went wrong calling the model: {last_error}", []


if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) or "What's our current match rate and top exception reasons?"
    print(ask(q))
