from __future__ import annotations

import yfinance as yf
import pandas as pd


def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(
        alpha=1 / period,
        min_periods=period,
        adjust=False
    ).mean()

    avg_loss = loss.ewm(
        alpha=1 / period,
        min_periods=period,
        adjust=False
    ).mean()

    rs = avg_gain / avg_loss.replace(0, pd.NA)
    return 100 - (100 / (1 + rs))


def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    previous_close = df["Close"].shift(1)

    tr1 = df["High"] - df["Low"]
    tr2 = (df["High"] - previous_close).abs()
    tr3 = (df["Low"] - previous_close).abs()

    true_range = pd.concat(
        [tr1, tr2, tr3],
        axis=1
    ).max(axis=1)

    return true_range.rolling(period).mean()


def calculate_eight_parameter_setup(
    ticker: str,
    mode: str = "Intraday",
    daily_data=None,
    intraday_data=None
):
    """
    NEW 8-PARAMETER ENGINE

    P1  Daily Primary Trend
    P2  5-Min Short Momentum
    P3  5-Min Pullback Detection
    P4  5-Min Reversal / Confirmation
    P5  5-Min Volume Surge
    P6  5-Min RSI Filter
    P7  First-15-Min High / PDH Trigger
    P8  Intraday ATR + Structure Risk/Reward

    Python is the calculation source of truth.
    """

    symbol = (
        ticker.strip().upper()
        if ticker.upper().endswith(".NS")
        else f"{ticker.strip().upper()}.NS"
    )

    try:
        stock = yf.Ticker(symbol)

        # =====================================================
        # DAILY DATA — P1
        # =====================================================

        daily = daily_data if daily_data is not None else stock.history(
            period="1y",
            interval="1d",
            auto_adjust=False
        )

        if daily.empty or len(daily) < 220:
            return None

        daily = daily.dropna(
            subset=["Open", "High", "Low", "Close", "Volume"]
        ).copy()

        daily["EMA20"] = daily["Close"].ewm(
            span=20,
            adjust=False
        ).mean()

        daily["EMA50"] = daily["Close"].ewm(
            span=50,
            adjust=False
        ).mean()

        daily["EMA200"] = daily["Close"].ewm(
            span=200,
            adjust=False
        ).mean()

        daily_last = daily.iloc[-1]

        daily_close = float(daily_last["Close"])
        daily_ema20 = float(daily_last["EMA20"])
        daily_ema50 = float(daily_last["EMA50"])
        daily_ema200 = float(daily_last["EMA200"])

        # =====================================================
        # P1 — PRIMARY TREND
        # Close > EMA20 > EMA50 > EMA200
        # =====================================================

        p1 = (
            daily_close > daily_ema20
            and daily_ema20 > daily_ema50
            and daily_ema50 > daily_ema200
        )

        # =====================================================
        # 5-MINUTE DATA — P2 TO P8
        # =====================================================

        intraday = intraday_data if intraday_data is not None else stock.history(
            period="5d",
            interval="5m",
            auto_adjust=False
        )

        if intraday.empty or len(intraday) < 100:
            return None

        intraday = intraday.dropna(
            subset=["Open", "High", "Low", "Close", "Volume"]
        ).copy()

        intraday["EMA20"] = intraday["Close"].ewm(
            span=20,
            adjust=False
        ).mean()

        intraday["RSI14"] = _rsi(
            intraday["Close"],
            14
        )

        intraday["ATR14"] = _atr(
            intraday,
            14
        )

        intraday["Volume_SMA20"] = (
            intraday["Volume"]
            .rolling(20)
            .mean()
        )

        # Current trading day
        latest_date = intraday.index[-1].date()

        today = intraday[
            intraday.index.date == latest_date
        ].copy()

        if len(today) < 3:
            return None

        # -----------------------------------------------------
        # Completed/current latest 5-min candle
        # -----------------------------------------------------

        last = today.iloc[-1]
        previous = today.iloc[-2]

        close = float(last["Close"])
        open_price = float(last["Open"])
        high = float(last["High"])
        low = float(last["Low"])

        ema20_5m = float(last["EMA20"])
        rsi14 = float(last["RSI14"])
        atr14 = float(last["ATR14"])

        volume = float(last["Volume"])
        volume_sma20 = float(last["Volume_SMA20"])

        # =====================================================
        # P2 — SHORT MOMENTUM
        # 5-Min Close > 5-Min EMA20
        # =====================================================

        p2 = (
            pd.notna(ema20_5m)
            and close > ema20_5m
        )

        # =====================================================
        # P3 — PULLBACK DETECTION
        #
        # Low <= EMA20 * 1.002
        # Close > EMA20
        # =====================================================

        p3 = (
            pd.notna(ema20_5m)
            and low <= (ema20_5m * 1.002)
            and close > ema20_5m
        )

        # =====================================================
        # P4 — REVERSAL / CONFIRMATION
        #
        # Green candle
        # Body > upper wick
        # =====================================================

        body = abs(close - open_price)

        upper_wick = max(
            0.0,
            high - max(open_price, close)
        )

        p4 = (
            close > open_price
            and body > upper_wick
        )

        # =====================================================
        # P5 — VOLUME SURGE
        #
        # Current Volume >= 1.5 x 20-bar SMA
        # =====================================================

        volume_ratio = None

        if (
            pd.notna(volume_sma20)
            and volume_sma20 > 0
        ):
            volume_ratio = volume / volume_sma20

        p5 = (
            volume_ratio is not None
            and volume_ratio >= 1.5
        )

        # =====================================================
        # P6 — RSI FILTER
        #
        # 55 <= RSI <= 68
        # =====================================================

        p6 = (
            pd.notna(rsi14)
            and 55 <= rsi14 <= 68
        )

        # =====================================================
        # P7 — FIRST 15-MIN HIGH / PDH TRIGGER
        #
        # First 3 x 5-minute candles = first 15 minutes.
        #
        # PASS:
        # Close >= First-15-Min High
        # OR
        # Close >= Previous Day High
        # =====================================================

        first_15 = today.iloc[:3]

        first_15_high = float(
            first_15["High"].max()
        )

        previous_trading_days = daily[
            daily.index.date < latest_date
        ]

        previous_day_high = None

        if not previous_trading_days.empty:
            previous_day_high = float(
                previous_trading_days.iloc[-1]["High"]
            )

        p7_first_15 = (
            close >= first_15_high
        )

        p7_pdh = (
            previous_day_high is not None
            and close >= previous_day_high
        )

        p7 = p7_first_15 or p7_pdh

        # =====================================================
        # P8 — INTRADAY RISK / REWARD
        #
        # Swing Low = recent 5 completed 5-min bars
        # SL = Swing Low - 1 x ATR
        #
        # Target = recent 20 completed 5-min bars High
        #
        # PASS:
        # R:R >= 1:2
        # AND
        # Target gain >= 2%
        # =====================================================

        completed_bars = today.iloc[:-1]

        if len(completed_bars) < 20:
            completed_bars = today.copy()

        recent_5 = completed_bars.tail(5)
        recent_20 = completed_bars.tail(20)

        swing_low = float(
            recent_5["Low"].min()
        )

        target = float(
            recent_20["High"].max()
        )

        stop_loss = None
        risk = None
        reward = None
        reward_risk_ratio = None
        target_percent = None
        risk_reward = None

        if (
            pd.notna(atr14)
            and atr14 > 0
        ):
            stop_loss = swing_low - atr14

            risk = close - stop_loss
            reward = target - close

            if close > 0:
                target_percent = (
                    reward / close
                ) * 100

            if risk > 0 and reward > 0:
                reward_risk_ratio = (
                    reward / risk
                )

                risk_reward = (
                    f"1:{reward_risk_ratio:.2f}"
                )

        p8 = (
            risk is not None
            and reward is not None
            and reward_risk_ratio is not None
            and target_percent is not None
            and reward_risk_ratio >= 2.0
            and target_percent >= 2.0
        )

        # =====================================================
        # FINAL SCORE
        # =====================================================

        parameters = [
            p1,
            p2,
            p3,
            p4,
            p5,
            p6,
            p7,
            p8
        ]

        score = sum(parameters)

        status = (
            "Bullish Setup Detected"
            if score == 8
            else "Watch / Confirmation Required"
        )

        return {
            "Ticker": ticker.replace(".NS", ""),

            "LTP": round(close, 2),

            "Daily_Close": round(daily_close, 2),
            "Daily_EMA20": round(daily_ema20, 2),
            "Daily_EMA50": round(daily_ema50, 2),
            "Daily_EMA200": round(daily_ema200, 2),

            "5M_EMA20": round(ema20_5m, 2),
            "RSI_14": round(rsi14, 2)
            if pd.notna(rsi14)
            else None,

            "Volume": int(volume),
            "Volume_SMA20": round(volume_sma20, 2)
            if pd.notna(volume_sma20)
            else None,

            "Volume_Ratio": round(volume_ratio, 2)
            if volume_ratio is not None
            else None,

            "ATR_14": round(atr14, 2)
            if pd.notna(atr14)
            else None,

            "First_15_Min_High": round(
                first_15_high,
                2
            ),

            "Previous_Day_High": round(
                previous_day_high,
                2
            )
            if previous_day_high is not None
            else None,

            "Swing_Low_5M": round(
                swing_low,
                2
            ),

            "Target": round(target, 2),

            "Stop_Loss": round(stop_loss, 2)
            if stop_loss is not None
            else None,

            "Risk_Per_Share": round(risk, 2)
            if risk is not None
            else None,

            "Reward_Per_Share": round(reward, 2)
            if reward is not None
            else None,

            "Target_Percent": round(
                target_percent,
                2
            )
            if target_percent is not None
            else None,

            "Reward_Risk_Ratio": round(
                reward_risk_ratio,
                2
            )
            if reward_risk_ratio is not None
            else None,

            "Risk_Reward": risk_reward,

            "P1_Primary_Trend": (
                "PASS" if p1 else "FAIL"
            ),

            "P2_Short_Momentum": (
                "PASS" if p2 else "FAIL"
            ),

            "P3_Pullback_Detection": (
                "PASS" if p3 else "FAIL"
            ),

            "P4_Reversal_Confirmation": (
                "PASS" if p4 else "FAIL"
            ),

            "P5_Volume_Surge": (
                "PASS" if p5 else "FAIL"
            ),

            "P6_RSI_Filter": (
                "PASS" if p6 else "FAIL"
            ),

            "P7_Previous_High_Trigger": (
                "PASS" if p7 else "FAIL"
            ),

            "P7_First_15M_High": (
                "PASS" if p7_first_15 else "FAIL"
            ),

            "P7_PDH": (
                "PASS" if p7_pdh else "FAIL"
            ),

            "P8_Risk_Reward": (
                "PASS" if p8 else "FAIL"
            ),

            "Score": f"{score}/8",
            "Raw_Score": score,

            "Status": status,

            "Analysis_Type": "Educational Analysis"
        }

    except Exception:
        return None


if __name__ == "__main__":
    print("eight_parameter_engine.py loaded")
    print("NEW P1-P8 parameter engine")






