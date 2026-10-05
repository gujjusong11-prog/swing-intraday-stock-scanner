import yfinance as yf
import pandas as pd


def calculate_intraday_engine(ticker):
    """
    Intraday Technical Engine
    Timeframe: 5-minute
    Core: VWAP + 9/21 EMA + Volume Surge + CPR
    """

    stock = yf.Ticker(f"{ticker}.NS")

    df = stock.history(
        period="5d",
        interval="5m",
        auto_adjust=False
    )

    if df.empty or len(df) < 30:
        return None

    df = df.dropna().copy()

    # ---------------------------------------------------------
    # 1. EMA 9 / EMA 21
    # ---------------------------------------------------------
    df["EMA_9"] = df["Close"].ewm(
        span=9,
        adjust=False
    ).mean()

    df["EMA_21"] = df["Close"].ewm(
        span=21,
        adjust=False
    ).mean()

    # ---------------------------------------------------------
    # 2. Daily-reset VWAP
    # VWAP must restart every trading day
    # ---------------------------------------------------------
    df["Typical_Price"] = (
        df["High"] +
        df["Low"] +
        df["Close"]
    ) / 3

    df["TP_Volume"] = (
        df["Typical_Price"] *
        df["Volume"]
    )

    df["Trading_Date"] = df.index.date

    df["Cum_TPV"] = df.groupby(
        "Trading_Date"
    )["TP_Volume"].cumsum()

    df["Cum_Volume"] = df.groupby(
        "Trading_Date"
    )["Volume"].cumsum()

    df["VWAP"] = (
        df["Cum_TPV"] /
        df["Cum_Volume"]
    )

    # ---------------------------------------------------------
    # 3. Volume SMA 20
    # ---------------------------------------------------------
    df["Volume_SMA20"] = (
        df["Volume"]
        .rolling(20)
        .mean()
    )

    df["Volume_Ratio"] = (
        df["Volume"] /
        df["Volume_SMA20"]
    )

    # ---------------------------------------------------------
    # 4. Previous Trading Day CPR
    # ---------------------------------------------------------
    daily = stock.history(
        period="10d",
        interval="1d",
        auto_adjust=False
    )

    if daily.empty or len(daily) < 2:
        return None

    daily = daily.dropna().copy()

    previous_day = daily.iloc[-2]

    prev_high = float(previous_day["High"])
    prev_low = float(previous_day["Low"])
    prev_close = float(previous_day["Close"])

    pivot = (
        prev_high +
        prev_low +
        prev_close
    ) / 3

    bc = (
        prev_high +
        prev_low
    ) / 2

    tc = (
        2 * pivot
    ) - bc

    cpr_top = max(tc, bc)
    cpr_bottom = min(tc, bc)

    # ---------------------------------------------------------
    # 5. Latest candle
    # ---------------------------------------------------------
    last = df.iloc[-1]
    prev = df.iloc[-2]

    close = float(last["Close"])
    open_price = float(last["Open"])
    vwap = float(last["VWAP"])
    ema9 = float(last["EMA_9"])
    ema21 = float(last["EMA_21"])
    volume_ratio = float(last["Volume_Ratio"])

    # ---------------------------------------------------------
    # 6. Four Core Conditions
    # ---------------------------------------------------------

    # Condition 1: Price above VWAP
    c1_vwap = close > vwap

    # Condition 2: 9 EMA above 21 EMA
    c2_ema = ema9 > ema21

    # Condition 3: Volume >= 1.5x 20-period average
    c3_volume = (
        volume_ratio >= 1.5
        if pd.notna(volume_ratio)
        else False
    )

    # Condition 4: Price above CPR
    c4_cpr = close > cpr_top

    # ---------------------------------------------------------
    # 7. Score
    # ---------------------------------------------------------
    score = sum([
        c1_vwap,
        c2_ema,
        c3_volume,
        c4_cpr
    ])

    return {
        "Ticker": ticker,
        "LTP": round(close, 2),

        "VWAP": round(vwap, 2),

        "EMA_9": round(ema9, 2),
        "EMA_21": round(ema21, 2),

        "Volume_Ratio": round(volume_ratio, 2)
        if pd.notna(volume_ratio)
        else None,

        "CPR_Pivot": round(pivot, 2),
        "CPR_Top": round(cpr_top, 2),
        "CPR_Bottom": round(cpr_bottom, 2),

        "VWAP_Status": "PASS"
        if c1_vwap else "FAIL",

        "EMA_Status": "PASS"
        if c2_ema else "FAIL",

        "Volume_Status": "PASS"
        if c3_volume else "FAIL",

        "CPR_Status": "PASS"
        if c4_cpr else "FAIL",

        "Raw_Score": score,
        "Score": f"{score}/4"
    }


if __name__ == "__main__":
    print("Intraday Technical Engine loaded successfully.")
    print("Core: VWAP + 9/21 EMA + Volume Surge + CPR")
