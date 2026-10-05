from pathlib import Path

p = Path("app.py")
s = p.read_text(encoding="utf-8")

s = s.replace(
    "import streamlit as st\nfrom google import genai",
    "import streamlit as st\nimport pandas as pd\nfrom google import genai"
)

old = '''with col1:
    st.markdown("""
    <div class="section">
        <div class="section-title">⚡ Intraday Stocks</div>
        <div class="section-subtitle">
            1M • 5M • 15M | Fast Momentum & Volume
        </div>
        <div class="list-box">
            <b>Stock List</b><br><br>
            NSE stock universe will be loaded here.
        </div>
    </div>
    """, unsafe_allow_html=True)
'''

new = '''with col1:
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
            "Rank", "Ticker", "LTP", "VWAP",
            "EMA_9", "EMA_21", "Volume_Ratio",
            "CPR_Top", "Score"
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
'''

if old not in s:
    raise SystemExit("Target Intraday section not found. No changes made.")

s = s.replace(old, new)

p.write_text(s, encoding="utf-8")
print("STEP 5A COMPLETE")
