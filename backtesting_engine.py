from __future__ import annotations

import math
from datetime import date, time
from typing import Any

import pandas as pd
import yfinance as yf

from capital_risk_engine import (
    CAPITAL,
    DAILY_MAX_LOSS,
    apply_capital_risk,
    daily_loss_limit_reached,
)
from eight_parameter_engine import calculate_eight_parameter_setup


DEFAULT_INTRADAY_PERIOD = "60d"
DEFAULT_BROKERAGE_PER_TRADE = 50.0
DEFAULT_SLIPPAGE_RATE = 0.0005
SLIPPAGE_ASSUMPTION = "0.05% of entry notional plus exit notional"
MINIMUM_INTRADAY_BARS = 100


def fetch_historical_data(symbols, period=DEFAULT_INTRADAY_PERIOD):
    """Fetch free yfinance data; 5-minute history is limited by provider retention."""
    market_data = {}
    unavailable = []

    for symbol in symbols:
        ticker = symbol if str(symbol).upper().endswith(".NS") else f"{symbol}.NS"
        try:
            stock = yf.Ticker(ticker)
            daily = stock.history(period="1y", interval="1d", auto_adjust=False)
            intraday = stock.history(period=period, interval="5m", auto_adjust=False)
            if daily.empty or intraday.empty:
                unavailable.append(str(symbol))
                continue
            market_data[str(symbol).replace(".NS", "").upper()] = (daily, intraday)
        except Exception:
            unavailable.append(str(symbol))

    return market_data, unavailable


def _finite_number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _as_frames(value):
    if isinstance(value, dict):
        return value.get("daily_data"), value.get("intraday_data")
    if isinstance(value, (tuple, list)) and len(value) == 2:
        return value[0], value[1]
    return None, None


def _prepare_market_data(market_data):
    prepared = {}
    unavailable = []
    required = {"Open", "High", "Low", "Close", "Volume"}

    for symbol, value in market_data.items():
        daily, intraday = _as_frames(value)
        if not isinstance(daily, pd.DataFrame) or not isinstance(intraday, pd.DataFrame):
            unavailable.append(str(symbol))
            continue
        if not required.issubset(daily.columns) or not required.issubset(intraday.columns):
            unavailable.append(str(symbol))
            continue

        daily = daily.dropna(subset=list(required)).sort_index().copy()
        intraday = intraday.dropna(subset=list(required)).sort_index().copy()
        daily = daily.loc[~daily.index.duplicated(keep="last")]
        intraday = intraday.loc[~intraday.index.duplicated(keep="last")]
        if daily.empty or intraday.empty:
            unavailable.append(str(symbol))
            continue
        prepared[str(symbol).replace(".NS", "").upper()] = {
            "daily": daily,
            "intraday": intraday,
        }

    return prepared, unavailable


def _date_in_range(timestamp, start_date, end_date):
    timestamp_date = timestamp.date()
    if start_date is not None and timestamp_date < start_date:
        return False
    if end_date is not None and timestamp_date > end_date:
        return False
    return True


def _daily_data_as_of(daily, intraday_prefix, current_date):
    prior_days = daily.loc[[index.date() < current_date for index in daily.index]].copy()
    current_bars = intraday_prefix.loc[
        [index.date() == current_date for index in intraday_prefix.index]
    ]
    if current_bars.empty:
        return prior_days

    partial = {
        "Open": current_bars["Open"].iloc[0],
        "High": current_bars["High"].max(),
        "Low": current_bars["Low"].min(),
        "Close": current_bars["Close"].iloc[-1],
        "Volume": current_bars["Volume"].sum(),
    }
    partial_index = pd.Timestamp(current_date)
    daily_timezone = getattr(daily.index, "tz", None)
    if daily_timezone is not None:
        partial_index = partial_index.tz_localize(daily_timezone)
    partial_frame = pd.DataFrame([partial], index=[partial_index])
    return pd.concat([prior_days, partial_frame]).sort_index()


def _is_session_end(timestamp, next_timestamp):
    if next_timestamp is not None and next_timestamp.date() == timestamp.date():
        return False
    local_timestamp = timestamp
    if local_timestamp.tzinfo is not None:
        local_timestamp = local_timestamp.tz_convert("Asia/Kolkata")
    return local_timestamp.time() >= time(15, 20)


def _has_following_bar_today(index, position):
    if position + 1 >= len(index):
        return False
    return index[position + 1].date() == index[position].date()


def _check_exit(position, bar, session_end):
    entry = position["Entry_Price"]
    stop_loss = position["Planned_SL"]
    target = position["Planned_Target"]
    open_price = float(bar["Open"])
    high = float(bar["High"])
    low = float(bar["Low"])

    stop_hit = low <= stop_loss
    target_hit = high >= target
    if stop_hit and target_hit:
        return stop_loss, "STOP_LOSS_HIT"
    if open_price <= stop_loss:
        return open_price, "STOP_LOSS_HIT"
    if stop_hit:
        return stop_loss, "STOP_LOSS_HIT"
    if open_price >= target or target_hit:
        return target, "TARGET_HIT"
    if session_end:
        return float(bar["Close"]), "EOD_SQUARE_OFF"
    return None


def _complete_trade(position, exit_price, exit_reason, brokerage, slippage_rate, exit_time):
    quantity = position["Allocated_Qty"]
    entry_price = position["Entry_Price"]
    gross_pnl = (exit_price - entry_price) * quantity
    brokerage_cost = brokerage
    slippage_cost = slippage_rate * quantity * (entry_price + exit_price)
    net_pnl = gross_pnl - brokerage_cost - slippage_cost
    risk = position["Risk_Per_Trade"]

    return {
        **position,
        "Trade_Type": "HYPOTHETICAL TRADE",
        "Exit_Time": exit_time,
        "Exit_Price": exit_price,
        "Exit_Reason": exit_reason,
        "Gross_PnL": gross_pnl,
        "Brokerage": brokerage_cost,
        "Slippage": slippage_cost,
        "Net_PnL": net_pnl,
        "Capital_Return_Pct": net_pnl / CAPITAL * 100,
        "R_Multiple": net_pnl / risk if risk else None,
    }


def _empty_report(unavailable=None):
    return {
        "Status": "DATA UNAVAILABLE",
        "Data_Source": "yfinance historical data",
        "Unavailable_Symbols": unavailable or [],
        "Total_Scanned_Opportunities": 0,
        "Total_Setups": 0,
        "Valid_Setups": 0,
        "Executed_Hypothetical_Trades": 0,
        "Completed_Trades": 0,
        "Wins": 0,
        "Losses": 0,
        "Win_Rate_Pct": None,
        "Gross_PnL": 0.0,
        "Brokerage": 0.0,
        "Slippage": 0.0,
        "Net_PnL": 0.0,
        "Average_Win": None,
        "Average_Loss": None,
        "Expectancy": None,
        "Maximum_Drawdown": 0.0,
        "Maximum_Drawdown_Pct": 0.0,
        "Maximum_Consecutive_Losses": 0,
        "Average_R_Multiple": None,
        "Daily_Loss_Limit_Breaches": 0,
        "Risk_Reward_Distribution": {},
        "Signals": [],
        "Trades": [],
        "Open_Position": None,
        "Backtest_Start": None,
        "Backtest_End": None,
        "Execution_Assumptions": {
            "Entry": "Signal bar close; hypothetical fill, not an actual execution",
            "Stop_Target_Conflict": "Stop loss is applied first when one bar touches both levels",
            "Stop_Gap": "Fill at bar open when it gaps through stop loss",
            "Target_Gap": "Fill at planned target price",
            "Open_Position_Valuation": "Unrealized P&L is excluded from drawdown and summary P&L",
        },
        "Limitations": [
            "Only one open hypothetical position is modeled at a time",
            "yfinance intraday history is limited and is not an execution-grade feed",
        ],
        "Cost_Assumptions": {
            "Brokerage_Per_Completed_Trade": DEFAULT_BROKERAGE_PER_TRADE,
            "Slippage_Rate": DEFAULT_SLIPPAGE_RATE,
            "Slippage_Method": SLIPPAGE_ASSUMPTION,
        },
    }


def _summarize(trades, signals, valid_setups, scanned, unavailable, open_position, breach_dates):
    report = _empty_report(unavailable)
    pnl_values = [trade["Net_PnL"] for trade in trades]
    wins = [value for value in pnl_values if value > 0]
    losses = [value for value in pnl_values if value < 0]
    gross = sum(trade["Gross_PnL"] for trade in trades)
    brokerage = sum(trade["Brokerage"] for trade in trades)
    slippage = sum(trade["Slippage"] for trade in trades)
    net = sum(pnl_values)

    equity = CAPITAL
    peak = equity
    maximum_drawdown = 0.0
    maximum_drawdown_pct = 0.0
    consecutive_losses = 0
    maximum_consecutive_losses = 0
    for trade in trades:
        equity += trade["Net_PnL"]
        peak = max(peak, equity)
        drawdown = peak - equity
        maximum_drawdown = max(maximum_drawdown, drawdown)
        if peak > 0:
            maximum_drawdown_pct = max(maximum_drawdown_pct, drawdown / peak * 100)
        if trade["Net_PnL"] < 0:
            consecutive_losses += 1
            maximum_consecutive_losses = max(maximum_consecutive_losses, consecutive_losses)
        else:
            consecutive_losses = 0

    rr_distribution = {"2.0-2.99": 0, "3.0-3.99": 0, "4.0+": 0}
    for signal in signals:
        ratio = _finite_number(signal.get("Risk_Reward_Calculated"))
        if ratio is None:
            continue
        if ratio < 3:
            rr_distribution["2.0-2.99"] += 1
        elif ratio < 4:
            rr_distribution["3.0-3.99"] += 1
        else:
            rr_distribution["4.0+"] += 1

    report.update({
        "Status": "COMPLETED" if scanned else "DATA UNAVAILABLE",
        "Total_Scanned_Opportunities": scanned,
        "Total_Setups": len(signals),
        "Valid_Setups": valid_setups,
        "Executed_Hypothetical_Trades": len(trades) + int(open_position is not None),
        "Completed_Trades": len(trades),
        "Wins": len(wins),
        "Losses": len(losses),
        "Win_Rate_Pct": len(wins) / len(trades) * 100 if trades else None,
        "Gross_PnL": gross,
        "Brokerage": brokerage,
        "Slippage": slippage,
        "Net_PnL": net,
        "Average_Win": sum(wins) / len(wins) if wins else None,
        "Average_Loss": sum(losses) / len(losses) if losses else None,
        "Expectancy": net / len(trades) if trades else None,
        "Maximum_Drawdown": maximum_drawdown,
        "Maximum_Drawdown_Pct": maximum_drawdown_pct,
        "Maximum_Consecutive_Losses": maximum_consecutive_losses,
        "Average_R_Multiple": (
            sum(trade["R_Multiple"] for trade in trades) / len(trades)
            if trades else None
        ),
        "Daily_Loss_Limit_Breaches": len(breach_dates),
        "Risk_Reward_Distribution": rr_distribution,
        "Signals": signals,
        "Trades": trades,
        "Open_Position": open_position,
    })
    return report


def run_backtest(
    market_data,
    start_date=None,
    end_date=None,
    brokerage_per_trade=DEFAULT_BROKERAGE_PER_TRADE,
    slippage_rate=DEFAULT_SLIPPAGE_RATE,
):
    """Run the production setup and risk engines against historical 5-minute bars."""
    brokerage = _finite_number(brokerage_per_trade)
    slippage = _finite_number(slippage_rate)
    if brokerage is None or brokerage < 0 or slippage is None or slippage < 0:
        raise ValueError("Cost assumptions must be finite and non-negative")

    start = pd.Timestamp(start_date).date() if start_date is not None else None
    end = pd.Timestamp(end_date).date() if end_date is not None else None
    prepared, unavailable = _prepare_market_data(market_data or {})
    if not prepared:
        return _empty_report(unavailable)

    timestamps = sorted({
        timestamp
        for data in prepared.values()
        for timestamp in data["intraday"].index
        if _date_in_range(timestamp, start, end)
    })
    if not timestamps:
        return _empty_report(list(prepared))

    trades = []
    signals = []
    valid_setups = 0
    scanned = 0
    breach_dates = set()
    daily_net = {}
    position = None
    previously_qualified = set()

    for timestamp in timestamps:
        current_date = timestamp.date()
        had_position_at_timestamp = position is not None

        if position is not None:
            active_data = prepared[position["Symbol"]]["intraday"]
            if timestamp in active_data.index:
                active_index = active_data.index.get_loc(timestamp)
                bar = active_data.iloc[active_index]
                next_timestamp = (
                    active_data.index[active_index + 1]
                    if active_index + 1 < len(active_data.index)
                    else None
                )
                exit_event = _check_exit(
                    position,
                    bar,
                    _is_session_end(timestamp, next_timestamp),
                )
                if exit_event is not None:
                    exit_price, exit_reason = exit_event
                    completed = _complete_trade(
                        position,
                        exit_price,
                        exit_reason,
                        brokerage,
                        slippage,
                        timestamp,
                    )
                    trades.append(completed)
                    daily_net[current_date] = daily_net.get(current_date, 0.0) + completed["Net_PnL"]
                    if daily_net[current_date] <= -DAILY_MAX_LOSS:
                        breach_dates.add(current_date)
                    position = None

        candidates = []
        candidate_timestamps = {}
        currently_qualified = set()
        for symbol in sorted(prepared):
            intraday = prepared[symbol]["intraday"]
            if timestamp not in intraday.index:
                continue
            bar_position = intraday.index.get_loc(timestamp)
            prefix = intraday.iloc[:bar_position + 1]
            current_day = prefix.loc[[index.date() == current_date for index in prefix.index]]
            if len(prefix) < MINIMUM_INTRADAY_BARS or len(current_day) < 3:
                continue

            scanned += 1
            daily_as_of = _daily_data_as_of(prepared[symbol]["daily"], prefix, current_date)
            result = calculate_eight_parameter_setup(
                symbol,
                mode="Intraday",
                daily_data=daily_as_of,
                intraday_data=prefix,
            )
            if not result or result.get("Status") != "Bullish Setup Detected":
                continue

            signal = dict(result)
            signal["Trade_Type"] = "SIGNAL DETECTED"
            signal["Risk_Reward_Calculated"] = signal.get("Reward_Risk_Ratio")
            signal["Score"] = signal.get("Raw_Score", signal.get("Score"))
            symbol = str(signal.get("Ticker", symbol)).upper()
            qualification_key = (symbol, current_date)
            currently_qualified.add(qualification_key)
            if qualification_key in previously_qualified:
                continue
            signals.append(signal)
            candidates.append(signal)
            candidate_timestamps[symbol] = (bar_position, intraday.index)
        previously_qualified = currently_qualified

        if not candidates:
            continue

        candidate_frame = pd.DataFrame(candidates)
        realized_daily_loss = max(0.0, -daily_net.get(current_date, 0.0))
        approved = apply_capital_risk(candidate_frame, realized_daily_loss)
        valid_setups += len(approved)

        if (
            position is not None
            or had_position_at_timestamp
            or daily_loss_limit_reached(realized_daily_loss)
            or approved.empty
        ):
            continue

        selected = approved.iloc[0]
        symbol = str(selected["Ticker"]).upper()
        bar_position, symbol_index = candidate_timestamps[symbol]
        if not _has_following_bar_today(symbol_index, bar_position):
            continue

        position = {
            "Trade_ID": f"BT_{timestamp.strftime('%Y%m%d_%H%M%S')}_{symbol}",
            "Date": current_date.isoformat(),
            "Entry_Time": timestamp.isoformat(),
            "Symbol": symbol,
            "Entry_Price": float(selected["Entry_Reference"]),
            "Planned_SL": float(selected["Stop_Loss"]),
            "Planned_Target": float(selected["Target"]),
            "Allocated_Qty": int(selected["Allocated_Qty"]),
            "Risk_Per_Trade": float(selected["Max_Theoretical_Loss"]),
            "Position_Exposure": float(selected["Position_Exposure"]),
            "Risk_Reward": float(selected["Risk_Reward_Calculated"]),
            "Entry_Reason": "P1-P8 qualifying setup; HYPOTHETICAL TRADE",
        }

    report = _summarize(
        trades,
        signals,
        valid_setups,
        scanned,
        unavailable,
        position,
        breach_dates,
    )
    report["Backtest_Start"] = timestamps[0].isoformat()
    report["Backtest_End"] = timestamps[-1].isoformat()
    return report


def run_yfinance_backtest(
    symbols,
    period=DEFAULT_INTRADAY_PERIOD,
    start_date=None,
    end_date=None,
    brokerage_per_trade=DEFAULT_BROKERAGE_PER_TRADE,
    slippage_rate=DEFAULT_SLIPPAGE_RATE,
):
    market_data, unavailable = fetch_historical_data(symbols, period=period)
    report = run_backtest(
        market_data,
        start_date=start_date,
        end_date=end_date,
        brokerage_per_trade=brokerage_per_trade,
        slippage_rate=slippage_rate,
    )
    report["Unavailable_Symbols"] = unavailable
    report["Historical_Intraday_Period"] = period
    report["Data_Source_Limitation"] = (
        "yfinance 5-minute history is delayed/incomplete and typically limited to about 60 days; "
        "this is not an execution-grade feed."
    )
    return report
