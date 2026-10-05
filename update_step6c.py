from pathlib import Path

p = Path("app.py")
s = p.read_text(encoding="utf-8")

# Add autorefresh import
s = s.replace(
    "import pandas as pd\nfrom google import genai",
    "import pandas as pd\nfrom google import genai\nfrom streamlit_autorefresh import st_autorefresh"
)

# Add timer configuration before Gemini model
marker = 'GEMINI_MODEL = "gemini-3.5-flash-lite"'

timer_code = '''
# ============================================================
# DUAL TIMER CONFIGURATION
# ============================================================

INTRADAY_REFRESH_OPTIONS = {
    "1 Minute": 60,
    "3 Minutes": 180
}

SWING_UPDATE_TIMES = ("15:10", "19:00")

'''

if "DUAL TIMER CONFIGURATION" not in s:
    s = s.replace(marker, timer_code + marker)

# Add mode selector and intraday timer before sidebar Gemini monitor
marker2 = '''# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:
    automatic_ai_monitor()
'''

replacement2 = '''# ============================================================
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
'''

if "TRADING MODE + DUAL TIMER CONTROL" not in s:
    if marker2 not in s:
        raise SystemExit("Sidebar marker not found. No changes made.")
    s = s.replace(marker2, replacement2)

p.write_text(s, encoding="utf-8")

print("STEP 6C COMPLETE")
