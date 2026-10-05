from datetime import datetime
import math
import numbers
import re

import pandas as pd


REQUIRED_COLUMNS = ("Open", "High", "Low", "Close", "Volume")
P1_P8_FIELDS = (
    "P1_Primary_Trend",
    "P2_Short_Momentum",
    "P3_Pullback_Detection",
    "P4_Reversal_Confirmation",
    "P5_Volume_Surge",
    "P6_RSI_Filter",
    "P7_Previous_High_Trigger",
    "P8_Risk_Reward",
)
DAILY_MINIMUM_ROWS = 220
INTRADAY_MINIMUM_ROWS = 100
MAX_MISSING_ROW_FRACTION = 0.05


def _number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        if pd.isna(value):
            return None
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if math.isfinite(parsed) else None


def _frame_quality(frame, label, minimum_rows):
    failures = []
    cautions = []
    valid_rows = 0

    if not isinstance(frame, pd.DataFrame):
        return "FAIL", f"{label} data is unavailable or is not a DataFrame.", valid_rows
    if frame.empty:
        return "FAIL", f"{label} DataFrame is empty.", valid_rows

    missing_columns = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing_columns:
        failures.append(f"Missing required columns: {', '.join(missing_columns)}.")

    index = frame.index
    if not isinstance(index, pd.DatetimeIndex):
        failures.append("Index is not a DatetimeIndex.")
    else:
        if index.hasnans:
            failures.append("Index contains invalid timestamps.")
        if index.has_duplicates:
            failures.append("Index contains duplicate timestamps.")
        if not index.is_monotonic_increasing:
            failures.append("Index is not ordered chronologically.")

    available_columns = [column for column in REQUIRED_COLUMNS if column in frame.columns]
    if available_columns:
        numeric = frame[available_columns].apply(pd.to_numeric, errors="coerce")
        numeric = numeric.replace([float("inf"), float("-inf")], float("nan"))
        complete_rows = numeric.notna().all(axis=1)
        missing_fraction = float((~complete_rows).mean())
        valid = numeric.loc[complete_rows]
        valid_rows = len(valid)

        if missing_fraction > MAX_MISSING_ROW_FRACTION:
            failures.append(
                f"{missing_fraction:.1%} of rows contain missing/non-numeric required values; "
                f"limit is {MAX_MISSING_ROW_FRACTION:.0%}."
            )
        elif missing_fraction > 0:
            cautions.append(f"{missing_fraction:.1%} of rows contain missing/non-numeric required values.")

        if valid_rows < minimum_rows:
            failures.append(
                f"Only {valid_rows} complete rows; at least {minimum_rows} are required."
            )

        if not valid.empty and set(REQUIRED_COLUMNS).issubset(valid.columns):
            open_price = valid["Open"]
            high = valid["High"]
            low = valid["Low"]
            close = valid["Close"]
            volume = valid["Volume"]

            bad_high = high < pd.concat([open_price, close], axis=1).max(axis=1)
            bad_low = low > pd.concat([open_price, close], axis=1).min(axis=1)
            bad_range = high < low
            bad_prices = (valid[["Open", "High", "Low", "Close"]] <= 0).any(axis=1)
            bad_volume = volume < 0
            if bad_high.any():
                failures.append("High is below Open or Close on one or more rows.")
            if bad_low.any():
                failures.append("Low is above Open or Close on one or more rows.")
            if bad_range.any():
                failures.append("High is below Low on one or more rows.")
            if bad_prices.any():
                failures.append("OHLC contains zero or negative prices.")
            if bad_volume.any():
                failures.append("Volume contains negative values.")

    if failures:
        return "FAIL", " ".join(failures + cautions), valid_rows
    if cautions:
        return "CAUTION", " ".join(cautions), valid_rows
    return "PASS", f"{valid_rows} complete rows passed structural checks.", valid_rows


def _indicators_quality(daily_rows, intraday_rows, engine_result):
    failures = []
    cautions = []
    if daily_rows < DAILY_MINIMUM_ROWS:
        failures.append(f"Daily EMA20/EMA50/EMA200 require at least {DAILY_MINIMUM_ROWS} complete rows.")
    if intraday_rows < INTRADAY_MINIMUM_ROWS:
        failures.append(f"5-minute indicators require at least {INTRADAY_MINIMUM_ROWS} complete bars.")

    if engine_result is None:
        cautions.append("Engine indicator outputs were not produced for this symbol.")
    else:
        required_outputs = (
            ("Daily_EMA20", "EMA20"),
            ("Daily_EMA50", "EMA50"),
            ("Daily_EMA200", "EMA200"),
            ("5M_EMA20", "5-minute EMA20"),
            ("RSI_14", "RSI14"),
            ("ATR_14", "ATR14"),
            ("Volume_SMA20", "Volume SMA20"),
        )
        for field, label in required_outputs:
            if _number(engine_result.get(field)) is None:
                cautions.append(f"{label} output is unavailable or non-numeric.")

    if failures:
        return "FAIL", " ".join(failures + cautions)
    if cautions:
        return "CAUTION", " ".join(cautions)
    return "PASS", "EMA20/EMA50/EMA200, RSI14, ATR14, and Volume SMA20 outputs are numeric and ready."


def _p1_p8_quality(engine_result):
    if engine_result is None:
        return "CAUTION", "P1-P8 results were not produced for this symbol."

    missing = [field for field in P1_P8_FIELDS if field not in engine_result]
    if missing:
        return "FAIL", f"Missing P1-P8 fields: {', '.join(missing)}."

    statuses = [engine_result[field] for field in P1_P8_FIELDS]
    if any(status not in {"PASS", "FAIL"} for status in statuses):
        return "FAIL", "Every P1-P8 value must be exactly PASS or FAIL."

    raw_score = engine_result.get("Raw_Score")
    if isinstance(raw_score, bool) or not isinstance(raw_score, numbers.Integral):
        return "FAIL", "Raw_Score is not an integer."
    if not 0 <= raw_score <= 8:
        return "FAIL", "Raw_Score is outside the range 0-8."

    pass_count = statuses.count("PASS")
    if raw_score != pass_count:
        return "FAIL", f"Raw_Score={raw_score}, but P1-P8 contain {pass_count} PASS values."

    score_match = re.fullmatch(r"\s*(\d+)\s*/\s*8\s*", str(engine_result.get("Score", "")))
    if score_match is None or int(score_match.group(1)) != raw_score:
        return "FAIL", f"Score does not match Raw_Score={raw_score}."

    return "PASS", f"All P1-P8 fields are valid; Raw_Score and Score both equal {raw_score}/8."


def _risk_quality(engine_result):
    if engine_result is None:
        return "CAUTION", "Risk outputs were not produced for this symbol."

    p8_status = engine_result.get("P8_Risk_Reward")
    ltp = _number(engine_result.get("LTP"))
    target = _number(engine_result.get("Target"))
    stop_loss = _number(engine_result.get("Stop_Loss"))
    target_percent = _number(engine_result.get("Target_Gain_Percent"))
    if target_percent is None:
        target_percent = _number(engine_result.get("Target_Percent"))
    reward_risk_ratio = _number(engine_result.get("Reward_Risk_Ratio"))
    risk_reward = engine_result.get("Risk_Reward")
    ratio_match = re.fullmatch(r"\s*1\s*:\s*([0-9]+(?:\.[0-9]+)?)\s*", str(risk_reward or ""))
    displayed_ratio = float(ratio_match.group(1)) if ratio_match else None

    calculation_available = any(
        _number(engine_result.get(field)) is not None
        for field in ("Stop_Loss", "Reward_Risk_Ratio", "Target_Percent", "Target_Gain_Percent")
    )
    if not calculation_available:
        if p8_status == "PASS":
            return "FAIL", "P8 is PASS but its risk calculation outputs are unavailable."
        return "CAUTION", "P8 risk calculation outputs are unavailable; risk consistency cannot be verified."

    missing = []
    if ltp is None or ltp <= 0:
        missing.append("positive LTP")
    if target is None:
        missing.append("numeric Target")
    if stop_loss is None:
        missing.append("numeric Stop_Loss")
    if target_percent is None:
        missing.append("numeric target gain percent")
    if reward_risk_ratio is None:
        missing.append("numeric Reward_Risk_Ratio")
    if displayed_ratio is None:
        missing.append("formatted Risk_Reward")
    if missing:
        status = "FAIL" if p8_status == "PASS" else "CAUTION"
        return status, f"Risk fields unavailable or invalid: {', '.join(missing)}."

    if stop_loss >= ltp or target <= ltp:
        return "FAIL", "Stop_Loss, LTP, and Target do not form a positive-risk, positive-reward structure."

    expected_target_percent = ((target - ltp) / ltp) * 100
    if abs(target_percent - expected_target_percent) > 0.05:
        return "FAIL", "Target gain percent is inconsistent with Target and LTP."

    expected_ratio = (target - ltp) / (ltp - stop_loss)
    if abs(reward_risk_ratio - expected_ratio) > 0.05:
        return "FAIL", "Reward_Risk_Ratio is inconsistent with Target, LTP, and Stop_Loss."
    if abs(displayed_ratio - reward_risk_ratio) > 0.01:
        return "FAIL", "Risk_Reward text is inconsistent with Reward_Risk_Ratio."

    return "PASS", "Stop_Loss, Target, Risk_Reward, and target gain are internally consistent."


def validate_data_quality(ticker, daily_data, intraday_data, engine_result=None):
    daily_status, daily_reason, daily_rows = _frame_quality(
        daily_data,
        "Daily",
        DAILY_MINIMUM_ROWS,
    )
    intraday_status, intraday_reason, intraday_rows = _frame_quality(
        intraday_data,
        "Intraday 5-minute",
        INTRADAY_MINIMUM_ROWS,
    )
    indicator_status, indicator_reason = _indicators_quality(
        daily_rows,
        intraday_rows,
        engine_result,
    )
    p1_p8_status, p1_p8_reason = _p1_p8_quality(engine_result)
    risk_status, risk_reason = _risk_quality(engine_result)

    statuses = (
        daily_status,
        intraday_status,
        indicator_status,
        p1_p8_status,
        risk_status,
    )
    overall = "FAIL" if "FAIL" in statuses else "CAUTION" if "CAUTION" in statuses else "PASS"
    reasons = [
        f"Daily: {daily_reason}",
        f"5m: {intraday_reason}",
        f"Indicators: {indicator_reason}",
        f"P1-P8: {p1_p8_reason}",
        f"Risk: {risk_reason}",
    ]

    return {
        "Ticker": ticker,
        "Data_Quality_Status": overall,
        "Daily_Data_Status": daily_status,
        "Intraday_Data_Status": intraday_status,
        "Indicator_Data_Status": indicator_status,
        "P1_P8_Data_Status": p1_p8_status,
        "Risk_Data_Status": risk_status,
        "Data_Quality_Reason": " ".join(reasons),
        "Data_Quality_Timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
        "Analysis_Type": "Educational Analysis",
    }
