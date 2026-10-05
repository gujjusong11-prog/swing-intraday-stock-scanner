import yfinance as yf
import pandas as pd


def calculate_eight_parameter_setup(ticker, mode="Intraday"):
    """
    Deterministic 8-Parameter Technical Engine.

    Python calculations are the source of truth.
    Educational Analysis only.
    """

    stock = yf.Ticker(f"{ticker}.NS")

    if mode == "Intraday":
        df = stock.history(
            period="1y",
            interval="1d",
            auto_adjust=False
        )
    else:
        df = stock.history(
            period="1y",
            interval="1d",
            auto_adjust=False
        )

    if df.empty or len(df) < 200:
        return None

    df = df.dropna().copy()

    # ---------------------------------------------------------
    # Technical calculations
    # ---------------------------------------------------------

    df["EMA_20"] = df["Close"].ewm(
        span=20,
        adjust=False
    ).mean()

    df["EMA_50"] = df["Close"].ewm(
        span=50,
        adjust=False
    ).mean()

    df["EMA_200"] = df["Close"].ewm(
        span=200,
        adjust=False
    ).mean()

    # RSI(14)
    delta = df["Close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()

    rs = avg_gain / avg_loss.replace(0, pd.NA)

    df["RSI_14"] = (
        100 - (100 / (1 + rs))
    )

    # 20-day average volume
    df["Volume_SMA20"] = (
        df["Volume"].rolling(20).mean()
    )

    # ---------------------------------------------------------
    # Latest candle
    # ---------------------------------------------------------

    last = df.iloc[-1]

    close = float(last["Close"])
    open_price = float(last["Open"])
    low = float(last["Low"])
    volume = float(last["Volume"])

    ema20 = float(last["EMA_20"])
    ema50 = float(last["EMA_50"])
    ema200 = float(last["EMA_200"])

    rsi14 = float(last["RSI_14"])
    avg_volume_20 = float(last["Volume_SMA20"])

    # ---------------------------------------------------------
    # 8 Parameters
    # ---------------------------------------------------------

    # 1. Primary Trend
    p1 = (
        close > ema200
        and ema50 > ema200
    )

    # 2. Short-term Momentum
    p2 = close > ema20

    # 3. Pullback Zone
    p3 = (
        low <= ema20
        and close >= ema20
    )

    # 4. Reversal Confirmation
    # Rule A selected by user:
    # Close > Open
    # Low <= 20 EMA
    # Close >= 20 EMA
    p4 = (
        close > open_price
        and low <= ema20
        and close >= ema20
    )

    # 5. Volume Surge
    p5 = (
        volume > avg_volume_20
        if pd.notna(avg_volume_20)
        else False
    )

    # 6. Momentum Range
    p6 = (
        50 <= rsi14 <= 65
        if pd.notna(rsi14)
        else False
    )

    # 7. Volatility Trigger
    if len(df) >= 2:
        previous_day_high = float(
            df.iloc[-2]["High"]
        )
    else:
        previous_day_high = None

    p7 = (
        close > previous_day_high
        if previous_day_high is not None
        else False
    )

    # 8. Risk-to-Reward
    # Deterministic market-structure rule:
    # Target = recent 20-period swing high
    # Stop Loss = lower of recent 5-period low
    #             and 1.5 ATR below close
    # P8 passes only when actual Reward / Risk >= 2.0

    atr_high_low = (
        df["High"] - df["Low"]
    )

    atr14 = float(
        atr_high_low.rolling(14).mean().iloc[-1]
    )

    target = float(
        df["High"].tail(20).max()
    )

    recent_5_low = float(
        df["Low"].tail(5).min()
    )

    if pd.isna(atr14) or atr14 <= 0:
        stop_loss = None
        risk = None
        reward = None
        reward_risk_ratio = None
        p8 = False
        risk_reward = None
    else:
        stop_loss = min(
            recent_5_low,
            close - (1.5 * atr14)
        )

        risk = close - stop_loss
        reward = target - close

        if risk > 0 and reward > 0:
            reward_risk_ratio = reward / risk
            p8 = reward_risk_ratio >= 2.0
            risk_reward = f"1:{reward_risk_ratio:.2f}"
        else:
            reward_risk_ratio = None
            p8 = False
            risk_reward = None

    parameters = [
        p1, p2, p3, p4,
        p5, p6, p7, p8
    ]

    score = sum(parameters)

    status = (
        "Bullish Setup Detected"
        if score == 8
        else "Watch / Confirmation Required"
    )

    return {
        "Ticker": ticker,
        "Mode": mode,

        "LTP": round(close, 2),

        "EMA_20": round(ema20, 2),
        "EMA_50": round(ema50, 2),
        "EMA_200": round(ema200, 2),

        "RSI_14": round(rsi14, 2)
        if pd.notna(rsi14)
        else None,

        "Volume": int(volume),
        "Volume_Avg_20D": int(avg_volume_20)
        if pd.notna(avg_volume_20)
        else None,
        "Volume_Ratio": round(
            float(volume) / float(avg_volume_20), 2
        )
        if pd.notna(avg_volume_20) and float(avg_volume_20) > 0
        else None,

        "Previous_Day_High": round(
            previous_day_high, 2
        )
        if previous_day_high is not None
        else None,

        "ATR_14": round(atr14, 2)
        if pd.notna(atr14)
        else None,

        "Swing_High_20": round(target, 2),
        "Recent_Low_5": round(recent_5_low, 2),
        "Stop_Loss": round(stop_loss, 2)
        if stop_loss is not None
        else None,
        "Risk_Per_Share": round(risk, 2)
        if risk is not None
        else None,
        "Reward_Per_Share": round(reward, 2)
        if reward is not None
        else None,
        "Reward_Risk_Ratio": round(reward_risk_ratio, 2)
        if reward_risk_ratio is not None
        else None,

        "Risk_Reward": risk_reward,

        "P1_Primary_Trend": "PASS" if p1 else "FAIL",
        "P2_Short_Momentum": "PASS" if p2 else "FAIL",
        "P3_Pullback_Zone": "PASS" if p3 else "FAIL",
        "P4_Reversal_Confirmation": "PASS" if p4 else "FAIL",
        "P5_Volume_Surge": "PASS" if p5 else "FAIL",
        "P6_Momentum_Range": "PASS" if p6 else "FAIL",
        "P7_Previous_High_Trigger": "PASS" if p7 else "FAIL",
        "P8_Risk_Reward": "PASS" if p8 else "FAIL",

        "Score": f"{score}/8",
        "Raw_Score": score,
        "Status": status
    }


if __name__ == "__main__":
    result = calculate_eight_parameter_setup(
        "RELIANCE",
        "Intraday"
    )

    if result:
        print("=" * 60)
        print("8-PARAMETER ENGINE TEST")
        print("=" * 60)

        for key, value in result.items():
            print(f"{key}: {value}")
    else:
        print("No valid data returned.")
