import streamlit as st

st.set_page_config(
    page_title="Stock Scanner Engine",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed"
)

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

# Header
st.markdown(
    '<div class="header">📊 Stock Scanner Engine</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="subtitle">NSE Stock Universe • Intraday + Swing • Dynamic Stock Selection</div>',
    unsafe_allow_html=True
)

# Two scanner sections
col1, col2 = st.columns(2, gap="large")

# Intraday
with col1:
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

# Swing
with col2:
    st.markdown("""
    <div class="section">
        <div class="section-title">📈 Swing Stocks</div>
        <div class="section-subtitle">
            Daily • Weekly | Trend & Pullback
        </div>
        <div class="list-box">
            <b>Stock List</b><br><br>
            NSE stock universe will be loaded here.
        </div>
    </div>
    """, unsafe_allow_html=True)

st.divider()

st.caption(
    "Educational Analysis • Market data and technical conditions will be added step-by-step."
)

