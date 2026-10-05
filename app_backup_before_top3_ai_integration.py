import os
from pathlib import Path
from datetime import datetime

import streamlit as st
import pandas as pd
from google import genai
from streamlit_autorefresh import st_autorefresh


st.set_page_config(
    page_title="Stock Scanner Engine",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)


# ============================================================
# DUAL TIMER CONFIGURATION
# ============================================================

INTRADAY_REFRESH_OPTIONS = {
    "1 Minute": 60,
    "3 Minutes": 180
}

SWING_UPDATE_TIMES = ("15:10", "19:00")

GEMINI_MODEL = "gemini-3.5-flash-lite"
AI_MONITOR_INTERVAL = "5m"


def run_gemini_monitor():
    api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        return {
            "status": "FAIL",
            "model": GEMINI_MODEL,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "error": "GEMINI_API_KEY environment variable not found."
        }

    try:
        client = genai.Client(api_key=api_key)

        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=(
                "You are the AI software audit monitor for a stock scanner engine. "
                "Do not provide trading recommendations. "
                "Do not modify or invent technical calculations. "
                "Check only whether the AI audit layer is operational. "
                "Reply exactly with:\n"
                "STATUS: PASS\n"
                "ROLE: AI AUDITOR\n"
                "CHECK: Gemini Monitor Connection\n"
                "MESSAGE: AI audit layer is operational"
            )
        )

        return {
            "status": "PASS",
            "model": GEMINI_MODEL,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "response": (response.text or "").strip()
        }

    except Exception as exc:
        return {
            "status": "FAIL",
            "model": GEMINI_MODEL,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "error": str(exc)
        }


# ============================================================
# AUTOMATIC GEMINI AI MONITOR
# ============================================================

@st.fragment(run_every=AI_MONITOR_INTERVAL)
def automatic_ai_monitor():

    audit = run_gemini_monitor()

    st.markdown("## 🤖 Gemini AI Monitor")
    st.caption("Automatic AI Audit & Software Guardrail Layer")

    if audit["status"] == "PASS":
        st.success("AI Monitor: PASS")
    else:
        st.error("AI Monitor: FAIL")

    st.markdown("**Current Task**")
    st.info("Automatic Gemini AI Audit")

    st.markdown("**Model**")
    st.code(audit["model"])

    st.markdown("**Last Audit**")
    st.caption(audit["timestamp"])

    if audit["status"] == "PASS":
        st.markdown("**AI Response**")
        st.code(audit["response"])
    else:
        st.markdown("**Error**")
        st.code(audit["error"])

    st.divider()

    st.markdown("### ⚙️ Automation Status")
    st.success("Automatic monitoring: ON")
    st.success("Audit interval: 5 minutes")
    st.success("Python = Calculation Source of Truth")
    st.success("Gemini = Audit / Monitor")
    st.warning("AI cannot modify scanner rules automatically.")

    st.caption(
        "Educational Analysis • AI output is an audit layer only. "
        "It does not constitute investment advice."
    )


# ============================================================
# TRADING MODE + DUAL TIMER CONTROL
# ============================================================

with st.sidebar:
    st.markdown("## ⚙️ Trading Mode")

    trade_mode = st.radio(
        "Select Mode",
        ["⚡ Intraday", "📈 Swing"],
        index=0
    )

    if trade_mode == "⚡ Intraday":
        refresh_label = st.selectbox(
            "Intraday Auto Refresh",
            list(INTRADAY_REFRESH_OPTIONS.keys()),
            index=0
        )

        refresh_seconds = INTRADAY_REFRESH_OPTIONS[refresh_label]

        st_autorefresh(
            interval=refresh_seconds * 1000,
            key="intraday_auto_refresh"
        )

        st.success(
            f"Intraday monitoring: ON • "
            f"Refresh every {refresh_label.lower()}"
        )

    else:
        st.info(
            "Swing mode: Daily 1D analysis"
        )
        st.caption(
            "Scheduled update windows: 15:10 and 19:00"
        )


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:
    automatic_ai_monitor()


# ============================================================
# MAIN DASHBOARD
# ============================================================

st.markdown("""
<style>
.stApp {
    background: #0b1220;
}

.block-container {
    max-width: 100%;
    padding: 30px 45px 40px 45px;
}

.header {
    font-size: 32px;
    font-weight: 700;
    color: #f8fafc;
    margin-bottom: 5px;
}

.subtitle {
    color: #94a3b8;
    font-size: 14px;
    margin-bottom: 25px;
}

.section {
    background: #111827;
    border: 1px solid #263244;
    border-radius: 14px;
    padding: 22px;
    margin-bottom: 20px;
}

.section-title {
    font-size: 22px;
    font-weight: 700;
    color: #f8fafc;
    margin-bottom: 5px;
}

.section-subtitle {
    color: #94a3b8;
    font-size: 13px;
    margin-bottom: 18px;
}

.list-box {
    background: #0f172a;
    border: 1px solid #263244;
    border-radius: 10px;
    padding: 18px;
    color: #cbd5e1;
}
</style>
""", unsafe_allow_html=True)


st.markdown(
    '<div class="header">📊 Stock Scanner Engine</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="subtitle">NSE Stock Universe • Intraday + Swing • Dynamic Stock Selection</div>',
    unsafe_allow_html=True
)


# ============================================================
# SWING STOCKS
# ============================================================

st.markdown("""
<div class="section">
    <div class="section-title">📈 Swing Stocks</div>
    <div class="section-subtitle">
        Daily • Weekly | Trend & Pullback
    </div>
    <div class="list-box">
        <b>Stock List</b><br><br>
        Swing stock universe will be loaded here.
    </div>
</div>
""", unsafe_allow_html=True)


# ============================================================
# INTRADAY STOCKS
# ============================================================

st.markdown("""
<div class="section">
    <div class="section-title">⚡ Intraday Stocks</div>
    <div class="section-subtitle">
        5M • 15M | Green Score & Volume Ranking
    </div>
</div>
""", unsafe_allow_html=True)

candidate_file = "intraday_ai_candidates.csv"

if Path(candidate_file).exists():

    intraday_df = pd.read_csv(candidate_file)

    display_cols = [
        "Rank",
        "Ticker",
        "LTP",
        "VWAP",
        "EMA_9",
        "EMA_21",
        "Volume_Ratio",
        "CPR_Top",
        "Score"
    ]

    st.dataframe(
        intraday_df[display_cols],
        use_container_width=True,
        hide_index=True
    )

    st.caption(
        f"Intraday candidates: {len(intraday_df)} stocks • "
        "Python technical ranking"
    )

else:
    st.info("Intraday candidate list is not available yet.")

st.divider()

st.caption(
    "Educational Analysis • Market data and technical conditions will be added step-by-step. "
    "Investment in securities market involves market risks."
)
