import math

import pandas as pd


CAPITAL = 2000.0
DAILY_MAX_LOSS = 150.0
MAX_RISK_PER_TRADE = 100.0
MAX_EXPOSURE = 10000.0
MIN_RISK_REWARD = 2.0

RISK_OUTPUT_COLUMNS = [
    "Entry_Reference",
    "Allocated_Qty",
    "Risk_Per_Share",
    "Max_Theoretical_Loss",
    "Position_Exposure",
    "Risk_Reward_Calculated",
]


def _finite_number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def daily_loss_limit_reached(realized_daily_loss):
    if realized_daily_loss is None:
        return True

    loss = _finite_number(realized_daily_loss)
    if loss is None or loss < 0:
        raise ValueError("realized_daily_loss must be a finite, non-negative amount")

    return loss >= DAILY_MAX_LOSS


def apply_capital_risk(ranked, realized_daily_loss):
    """Keep only P1-P8-qualified setups that fit capital and risk limits."""
    output = ranked.copy()
    for column in RISK_OUTPUT_COLUMNS:
        output[column] = pd.Series(index=output.index, dtype="object")

    if output.empty or daily_loss_limit_reached(realized_daily_loss):
        return output.iloc[0:0].copy()

    capital_remaining = CAPITAL
    exposure_remaining = MAX_EXPOSURE
    approved_indices = []

    for index, row in output.iterrows():
        if row.get("Status") != "Bullish Setup Detected":
            continue

        score = _finite_number(row.get("Score"))
        entry = _finite_number(row.get("LTP"))
        stop_loss = _finite_number(row.get("Stop_Loss"))
        target = _finite_number(row.get("Target"))

        if score != 8 or entry is None or stop_loss is None or target is None:
            continue
        if entry <= 0 or stop_loss <= 0 or stop_loss >= entry or target <= entry:
            continue

        risk_per_share = entry - stop_loss
        reward_per_share = target - entry
        risk_reward = reward_per_share / risk_per_share
        if risk_reward < MIN_RISK_REWARD:
            continue

        quantity = min(
            math.floor(MAX_RISK_PER_TRADE / risk_per_share),
            math.floor(capital_remaining / entry),
            math.floor(exposure_remaining / entry),
        )
        if quantity <= 0:
            continue

        position_exposure = quantity * entry
        theoretical_loss = quantity * risk_per_share
        output.at[index, "Entry_Reference"] = entry
        output.at[index, "Allocated_Qty"] = quantity
        output.at[index, "Risk_Per_Share"] = risk_per_share
        output.at[index, "Max_Theoretical_Loss"] = theoretical_loss
        output.at[index, "Position_Exposure"] = position_exposure
        output.at[index, "Risk_Reward_Calculated"] = risk_reward

        capital_remaining -= position_exposure
        exposure_remaining -= position_exposure
        approved_indices.append(index)

    output = output.loc[approved_indices].copy()
    for column in RISK_OUTPUT_COLUMNS:
        output[column] = pd.to_numeric(output[column], errors="coerce")

    if "Rank" in output.columns:
        output["Rank"] = range(1, len(output) + 1)

    return output
