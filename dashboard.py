"""
Split-screen control room UI.
  Left  -> match rate, volume, downloadable exception ledger
  Right -> Settlement Q&A chat

Run the FastAPI backend first (uvicorn app.main:app), then:
  streamlit run dashboard.py
"""

import pandas as pd
import requests
import streamlit as st

API_BASE = "http://localhost:8000"

st.set_page_config(page_title="AI Finance Controller", layout="wide")
st.title("AI Finance Controller — Control Room")

if st.button("Run ingestion + reconciliation on synthetic batch"):
    resp = requests.post(f"{API_BASE}/ingest/run-synthetic")
    st.session_state["last_run"] = resp.json()

left, right = st.columns([5, 3])

with left:
    st.subheader("Evaluation — \"The Bar\"")
    summary = requests.get(f"{API_BASE}/summary").json()
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Match Rate", f"{summary['match_rate_pct']}%")
    c2.metric("Reconciled", summary["reconciled_count"])
    c3.metric("Exceptions", summary["exception_count"])
    c4.metric("Rejected on Ingest", summary["rejected_count"])
    c5.metric("Name-Match Engine", summary.get("name_match_engine", "n/a"))

    throughput = summary.get("throughput")
    if throughput:
        t1, t2, t3 = st.columns(3)
        t1.metric("Records Ingested", throughput["total_records_ingested"])
        t2.metric("Processing Time", f"{throughput['processing_time_seconds']}s")
        t3.metric("Throughput", f"{throughput['records_per_second']} rec/s" if throughput["records_per_second"] else "n/a")
        st.caption("Throughput measured end-to-end: ingestion + validation + full two-pass reconciliation.")

    st.subheader("Exception Ledger")
    exceptions = requests.get(f"{API_BASE}/exceptions").json()
    if exceptions:
        df = pd.DataFrame(exceptions)
        # exception_id is a raw UUID — noisy and not useful to scan visually, drop it from the view
        display_cols = [c for c in df.columns if c != "exception_id"]
        st.dataframe(
            df[display_cols],
            width="stretch",
            height=320,
            column_config={
                "record_id": st.column_config.TextColumn("Record", width="small"),
                "source": st.column_config.TextColumn("Source", width="small"),
                "reason_code": st.column_config.TextColumn("Reason", width="medium"),
                "reason_detail": st.column_config.TextColumn("Detail", width="large"),
                "best_candidate_id": st.column_config.TextColumn("Candidate", width="small"),
                "best_candidate_confidence": st.column_config.NumberColumn("Confidence", format="%.2f", width="small"),
                "logged_at": st.column_config.DatetimeColumn("Logged At", width="small"),
            },
        )
        st.download_button(
            "Download Exception Ledger (CSV)",
            df.to_csv(index=False),
            file_name="exception_ledger.csv",
        )
    else:
        st.info("No exceptions yet — run reconciliation above.")

    st.subheader("Cash Forecast (next 7 days)")
    forecast = requests.get(f"{API_BASE}/forecast").json()
    if "daily_projection" in forecast:
        fdf = pd.DataFrame(
            list(forecast["daily_projection"].items()), columns=["date", "projected_net_cash"]
        )
        st.line_chart(fdf.set_index("date"))
        st.caption(f"Basis: {forecast['basis']} | Trend/day: {forecast['trend_slope_per_day']}")
    else:
        st.info(forecast.get("error", "Not enough data to forecast yet."))

    st.subheader("Tax-Line Classification")
    tax = requests.get(f"{API_BASE}/tax/classify").json()
    if tax.get("results"):
        t1, t2, t3 = st.columns(3)
        t1.metric("Classified", tax["total_classified"])
        t2.metric("Needs Review", tax["needs_review_count"])
        t3.metric("Engine", tax.get("engine_used", "n/a"))

        tdf = pd.DataFrame(tax["results"])
        # sort flagged rows to the top so reviewers see what needs attention first,
        # instead of having to scroll through 55 clean rows to find the 7 that matter
        tdf["_flagged"] = tdf["needs_review"] | tdf["missing_tax_id"]
        tdf = tdf.sort_values("_flagged", ascending=False).drop(columns="_flagged").reset_index(drop=True)

        def _highlight_flagged(row):
            is_flagged = row["needs_review"] or row["missing_tax_id"]
            color = "background-color: rgba(255, 90, 90, 0.18)" if is_flagged else ""
            return [color] * len(row)

        styled = tdf.style.apply(_highlight_flagged, axis=1)
        st.dataframe(
            styled,
            width="stretch",
            height=260,
            column_config={
                "record_id": st.column_config.TextColumn("Record", width="small"),
                "tax_code": st.column_config.TextColumn("Tax Code", width="medium"),
                "category": st.column_config.TextColumn("Category", width="large"),
                "confidence": st.column_config.NumberColumn("Confidence", format="%.2f", width="small"),
                "needs_review": st.column_config.CheckboxColumn("Review?", width="small"),
                "missing_tax_id": st.column_config.CheckboxColumn("Missing Tax ID?", width="small"),
                "review_reason": st.column_config.TextColumn("Review Reason", width="large"),
            },
        )
        st.caption("Rows needing review or missing a tax ID are highlighted and sorted to the top.")

        # category distribution — shows the matcher is actually discriminating
        # between categories, not just rubber-stamping everything the same way
        cat_counts = (
            tdf[tdf["category"].notna()]["category"]
            .value_counts()
            .sort_values(ascending=False)
        )
        if not cat_counts.empty:
            st.caption("Classified transactions by tax category")
            st.bar_chart(cat_counts)
    else:
        st.info("Nothing to classify yet — run reconciliation above.")

with right:
    st.subheader("Settlement Q&A Agent")
    if "chat" not in st.session_state:
        st.session_state["chat"] = []

    for role, msg, trace in st.session_state["chat"]:
        with st.chat_message(role):
            st.write(msg)
            if trace:
                with st.expander(f"🔍 Agent reasoning trace ({len(trace)} tool call{'s' if len(trace) != 1 else ''})"):
                    for i, step in enumerate(trace, 1):
                        st.markdown(f"**Step {i}: `{step['tool']}`**")
                        if step.get("args"):
                            st.code(str(step["args"]), language="python")
                        st.caption("Result:")
                        st.json(step["result"], expanded=False)

    q = st.chat_input("Ask about a batch, exception, or forecast...")
    if q:
        st.session_state["chat"].append(("user", q, None))
        with st.chat_message("user"):
            st.write(q)
        try:
            from app.langgraph_agent import ask_with_trace
        except Exception:
            # LangGraph deps missing or failed to init — fall back to the
            # proven direct Gemini tool-calling loop rather than break the demo
            from app.qa_agent import ask_with_trace
        answer, trace = ask_with_trace(q)
        st.session_state["chat"].append(("assistant", answer, trace))
        with st.chat_message("assistant"):
            st.write(answer)
            if trace:
                with st.expander(f"🔍 Agent reasoning trace ({len(trace)} tool call{'s' if len(trace) != 1 else ''})"):
                    for i, step in enumerate(trace, 1):
                        st.markdown(f"**Step {i}: `{step['tool']}`**")
                        if step.get("args"):
                            st.code(str(step["args"]), language="python")
                        st.caption("Result:")
                        st.json(step["result"], expanded=False)
