import contextlib
import io
import logging
import time
from datetime import datetime

import streamlit as st
import pandas as pd

import parallel_nse_scanner as scanner
from parallel_nse_scanner import FINAL_OUTPUT_COLUMNS, scan_parallel
from nse_scanner import load_nse_universe


st.set_page_config(
    page_title="Swing & Intraday Stock Scanner Engine",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)


DISCLAIMER = (
    "This software provides educational technical analysis only. It is not "
    "investment advice. Market conditions can change rapidly. No profit or "
    "performance is guaranteed. Users are responsible for their own decisions "
    "and risk."
)


P1_P8_COLUMNS = [
    "P1_Primary_Trend",
    "P2_Short_Momentum",
    "P3_Pullback_Detection",
    "P4_Reversal_Confirmation",
    "P5_Volume_Surge",
    "P6_RSI_Filter",
    "P7_Previous_High_Trigger",
    "P8_Risk_Reward",
]


@st.cache_data(ttl=3600, show_spinner=False)
def cached_nse_universe():
    return load_nse_universe()


class RateLimitLogHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.messages = []

    def emit(self, record):
        message = self.format(record)
        lowered = message.lower()
        if (
            "429" in lowered
            or "rate-limit" in lowered
            or "rate limited" in lowered
            or "too many requests" in lowered
        ):
            self.messages.append(message)


def display_value(value):
    if value is None or pd.isna(value):
        return "N/A"
    return value


st.title("Swing & Intraday Stock Scanner Engine")
st.caption("Educational Analysis")
st.warning(DISCLAIMER)

with st.sidebar:
    st.subheader("Scanner Controls")
    scan_mode = st.radio(
        "Scan mode",
        ["NSE universe", "Test universe"],
    )
    test_count = st.number_input(
        "Number of stocks",
        min_value=1,
        max_value=2319,
        value=20,
        step=1,
        disabled=scan_mode == "NSE universe",
    )
    run_scan = st.button("Run Scanner", type="primary", use_container_width=True)
    clear_results = st.button("Clear Results", use_container_width=True)

if clear_results:
    st.session_state.pop("scan_results", None)
    st.session_state.pop("scan_summary", None)
    st.rerun()

if run_scan:
    try:
        universe = cached_nse_universe()
        symbols = universe if scan_mode == "NSE universe" else universe[:int(test_count)]

        rate_limit_handler = RateLimitLogHandler()
        root_logger = logging.getLogger()
        root_logger.addHandler(rate_limit_handler)
        scan_console = io.StringIO()
        started = time.perf_counter()
        try:
            with st.spinner(f"Scanning {len(symbols)} stocks..."):
                with contextlib.redirect_stdout(scan_console):
                    ranked = scan_parallel(symbols)
        finally:
            elapsed = time.perf_counter() - started
            root_logger.removeHandler(rate_limit_handler)

        scan_log = scan_console.getvalue()
        rate_limit_lines = [
            line for line in scan_log.splitlines()
            if "429" in line.lower()
            or "rate-limit" in line.lower()
            or "too many requests" in line.lower()
        ]
        failed_symbols = list(scanner._failed_symbols)
        st.session_state["scan_results"] = ranked
        st.session_state["scan_summary"] = {
            "stocks_tested": len(symbols),
            "candidates": len(ranked),
            "scan_time": elapsed,
            "http_429": bool(rate_limit_handler.messages or rate_limit_lines),
            "failed_rows": len(failed_symbols),
            "failed_symbols": failed_symbols,
            "timestamp": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z"),
            "log": scan_log,
            "rate_limit_messages": rate_limit_handler.messages + rate_limit_lines,
        }
    except Exception as exc:
        st.error(f"Scanner could not complete: {exc}")

scan_results = st.session_state.get("scan_results")
scan_summary = st.session_state.get("scan_summary")

if scan_results is None or scan_summary is None:
    st.info("Choose a scan mode and run the scanner to view current results.")
elif scan_results.empty:
    st.warning("The scanner returned no candidates for this run.")
else:
    st.subheader("Scan Summary")
    metrics = st.columns(6)
    metrics[0].metric("Stocks Tested", scan_summary["stocks_tested"])
    metrics[1].metric("Candidates", scan_summary["candidates"])
    metrics[2].metric("Scan Time", f"{scan_summary['scan_time']:.2f}s")
    metrics[3].metric("HTTP 429", "Detected" if scan_summary["http_429"] else "Not observed")
    metrics[4].metric("Failed Rows", scan_summary["failed_rows"])
    metrics[5].metric("Timestamp", scan_summary["timestamp"])

    if scan_summary["http_429"]:
        st.warning("HTTP 429 was reported during this scan. See the scanner log below.")

    st.subheader("Scanner Results")
    st.dataframe(
        scan_results[FINAL_OUTPUT_COLUMNS],
        width="stretch",
        hide_index=True,
    )

    ticker_options = scan_results["Ticker"].astype(str).tolist()
    selected_ticker = st.selectbox("Ticker details", ticker_options)
    selected = scan_results.loc[
        scan_results["Ticker"].astype(str) == selected_ticker
    ].iloc[0]

    if selected["Status"] == "Bullish Setup Detected":
        st.success(selected["Status"])
    else:
        st.warning(selected["Status"])

    st.subheader("Parameter Details")
    parameter_labels = [
        "P1 Primary Trend",
        "P2 Short Momentum",
        "P3 Pullback Detection",
        "P4 Reversal Confirmation",
        "P5 Volume Surge",
        "P6 RSI Filter",
        "P7 Previous High Trigger",
        "P8 Risk-to-Reward",
    ]
    st.dataframe(
        pd.DataFrame(
            [
                {"Parameter": label, "Result": selected[column]}
                for label, column in zip(parameter_labels, P1_P8_COLUMNS)
            ]
        ),
        width="stretch",
        hide_index=True,
    )

    st.subheader("Risk Information")
    risk_metrics = st.columns(5)
    for metric, column in zip(
        risk_metrics,
        ["LTP", "Stop_Loss", "Target", "Risk_Reward", "Target_Gain_Percent"],
    ):
        metric.metric(column, display_value(selected[column]))

    if scan_summary["failed_symbols"]:
        with st.expander("Failed rows"):
            st.write(scan_summary["failed_symbols"])
    if scan_summary["log"]:
        with st.expander("Scanner log"):
            st.code(scan_summary["log"])
