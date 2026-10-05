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

        # Keep intraday Volume_Ratio consistent with intraday_engine.py:
        # current 5-minute volume / 20-period 5-minute average volume.
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
