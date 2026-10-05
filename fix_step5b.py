from pathlib import Path

p = Path("app.py")
s = p.read_text(encoding="utf-8")

# Fix missing Path import
s = s.replace(
    "import os\nfrom datetime import datetime",
    "import os\nfrom pathlib import Path\nfrom datetime import datetime"
)

# Replace two-column stock layout with vertical layout
start = s.index("col1, col2 = st.columns(2, gap=\"large\")")
end = s.index("\nst.divider()", start)

new_layout = '''# ============================================================
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
'''

s = s[:start] + new_layout + s[end:]

p.write_text(s, encoding="utf-8")

print("STEP 5B COMPLETE")
