import yfinance as yf
import pandas as pd


def calculate_atr(df, period=14):
    high_low = df["High"] - df["Low"]
    high_prev_close = (df["High"] - df["Close"].shift(1)).abs()
    low_prev_close = (df["Low"] - df["Close"].shift(1)).abs()

    true_range = pd.concat(
        [high_low, high_prev_close, low_prev_close],
        axis=1
    ).max(axis=1)

    return true_range.rolling(period).mean()


def calculate_deep_setup(ticker, mode="Intraday"):
    try:
        stock = yf.Ticker(f"{ticker}.NS")

        if mode == "Intraday":
            df = stock.history(
                period="10d",
                interval="5m",
                auto_adjust=False
            )
        else:
            df = stock.history(
                period="1y",
                interval="1d",
                auto_adjust=False
            )

        if df.empty or len(df) < 50:
            return None

        df = df.dropna().copy()

        df["ATR_14"] = calculate_atr(df, 14)

        # EMA trend
        df["EMA_9"] = df["Close"].ewm(span=9, adjust=False).mean()
        df["EMA_21"] = df["Close"].ewm(span=21, adjust=False).mean()

        # RSI(14)
        delta = df["Close"].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)

        avg_gain = gain.rolling(14).mean()
        avg_loss = loss.rolling(14).mean()

        rs = avg_gain / avg_loss.replace(0, pd.NA)
        df["RSI_14"] = 100 - (100 / (1 + rs))
        df["RSI_14"] = df["RSI_14"].fillna(50)

        # Intraday VWAP
        typical_price = (df["High"] + df["Low"] + df["Close"]) / 3
        df["Trading_Date"] = df.index.date
        df["TP_Volume"] = typical_price * df["Volume"]
        df["Cum_TPV"] = df.groupby("Trading_Date")["TP_Volume"].cumsum()
        df["Cum_Volume"] = df.groupby("Trading_Date")["Volume"].cumsum()
        df["VWAP"] = df["Cum_TPV"] / df["Cum_Volume"]

        # Keep Volume_Ratio consistent with intraday_engine.py.
        df["Volume_SMA20"] = df["Volume"].rolling(20).mean()
        df["Volume_Ratio"] = df["Volume"] / df["Volume_SMA20"]

        last = df.iloc[-1]

        ltp = float(last["Close"])
        atr = float(last["ATR_14"])

        if pd.isna(atr) or atr <= 0:
            atr = float(last["High"] - last["Low"])

        # Recent swing levels
        recent_window = df.tail(20)

        swing_high = float(recent_window["High"].max())
        swing_low = float(recent_window["Low"].min())

        # 52-week range
        yearly = stock.history(
            period="1y",
            interval="1d",
            auto_adjust=False
        ).dropna()

        if yearly.empty:
            week52_high = None
            week52_low = None
        else:
            week52_high = float(yearly["High"].max())
            week52_low = float(yearly["Low"].min())

        # -------------------------------------------------
        # Mathematical technical levels
        # -------------------------------------------------

        if mode == "Intraday":
            entry_low = ltp - (0.25 * atr)
            stop_loss = ltp - (1.0 * atr)
        else:
            entry_low = ltp - (0.50 * atr)
            stop_loss = ltp - (1.50 * atr)

        entry_high = ltp

        risk = ltp - stop_loss

        if risk <= 0:
            return None

        target_1_2 = ltp + (2.0 * risk)

        volume_ratio = (
            float(last["Volume_Ratio"])
            if pd.notna(last["Volume_Ratio"])
            else None
        )

        ema9 = float(last["EMA_9"])
        ema21 = float(last["EMA_21"])
        rsi14 = float(last["RSI_14"])
        vwap = float(last["VWAP"])

        # Previous-day levels and CPR
        daily = stock.history(
            period="10d",
            interval="1d",
            auto_adjust=False
        ).dropna()

        if len(daily) >= 2:
            previous_day = daily.iloc[-2]

            previous_day_high = float(previous_day["High"])
            previous_day_low = float(previous_day["Low"])
            previous_day_close = float(previous_day["Close"])

            cpr_pivot = (
                previous_day_high
                + previous_day_low
                + previous_day_close
            ) / 3

            cpr_bc = (previous_day_high + previous_day_low) / 2
            cpr_tc = (2 * cpr_pivot) - cpr_bc

            cpr_top = max(cpr_tc, cpr_bc)
            cpr_bottom = min(cpr_tc, cpr_bc)
        else:
            previous_day_high = None
            previous_day_low = None
            previous_day_close = None
            cpr_pivot = None
            cpr_top = None
            cpr_bottom = None

        return {
            "Ticker": ticker,
            "Mode": mode,
            "LTP": round(ltp, 2),
            "Entry_Low": round(entry_low, 2),
            "Entry_High": round(entry_high, 2),
            "Stop_Loss": round(stop_loss, 2),
            "Target_1_2": round(target_1_2, 2),
            "Risk_Per_Share": round(risk, 2),
            "Reward_Per_Share": round(risk * 2, 2),
            "Risk_Reward": "1:2",
            "ATR_14": round(atr, 2),
            "EMA_9": round(ema9, 2),
            "EMA_21": round(ema21, 2),
            "RSI_14": round(rsi14, 2),
            "VWAP": round(vwap, 2),
            "Previous_Day_High": round(previous_day_high, 2) if previous_day_high is not None else None,
            "Previous_Day_Low": round(previous_day_low, 2) if previous_day_low is not None else None,
            "Previous_Day_Close": round(previous_day_close, 2) if previous_day_close is not None else None,
            "CPR_Pivot": round(cpr_pivot, 2) if cpr_pivot is not None else None,
            "CPR_Top": round(cpr_top, 2) if cpr_top is not None else None,
            "CPR_Bottom": round(cpr_bottom, 2) if cpr_bottom is not None else None,
            "Swing_High_20": round(swing_high, 2),
            "Swing_Low_20": round(swing_low, 2),
            "52W_High": round(week52_high, 2) if week52_high else None,
            "52W_Low": round(week52_low, 2) if week52_low else None,
            "Volume_Ratio": round(volume_ratio, 2) if volume_ratio is not None else None
        }

    except Exception as exc:
        print(f"[DEEP SETUP ERROR] {ticker}: {exc}")
        return None


if __name__ == "__main__":
    test = calculate_deep_setup("RELIANCE", "Intraday")

    if test:
        print("=" * 60)
        print("DEEP SETUP ENGINE TEST")
        print("=" * 60)

        for key, value in test.items():
            print(f"{key}: {value}")
    else:
        print("No valid deep setup data returned.")
