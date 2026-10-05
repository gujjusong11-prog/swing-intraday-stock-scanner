from datetime import date, datetime, timezone
import math

import pandas as pd
import yfinance as yf


NEAR_TERM_DAYS = 14


def _as_dates(value):
    if value is None:
        return []
    if isinstance(value, (list, tuple, set, pd.Index, pd.Series)):
        dates = []
        for item in value:
            dates.extend(_as_dates(item))
        return dates
    if pd.isna(value):
        return []
    if isinstance(value, datetime):
        return [value.date()]
    if isinstance(value, date):
        return [value]
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        try:
            return [datetime.fromtimestamp(float(value), tz=timezone.utc).date()]
        except (OverflowError, OSError, ValueError):
            return []
    parsed = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(parsed):
        return []
    return [parsed.date()]


def _calendar_value(calendar, key):
    if isinstance(calendar, dict):
        return calendar.get(key)
    if isinstance(calendar, pd.DataFrame):
        if key in calendar.columns:
            return calendar[key].tolist()
        if key in calendar.index:
            return calendar.loc[key].tolist()
    return None


def _source(stock, name):
    try:
        value = getattr(stock, name)
    except Exception:
        return None, False
    if value is None:
        return None, False
    return value, True


def _future_action_dates(actions, column, today):
    if not isinstance(actions, pd.DataFrame) or actions.empty:
        return []
    matching_column = next(
        (name for name in actions.columns if str(name).strip().lower() == column.lower()),
        None,
    )
    if matching_column is None:
        return []

    dates = []
    for action_date, row in actions.iterrows():
        parsed_dates = _as_dates(action_date)
        if not parsed_dates:
            continue
        try:
            value = float(row[matching_column])
        except (TypeError, ValueError):
            continue
        if value > 0 and today <= parsed_dates[0]:
            dates.append(parsed_dates[0])
    return dates


def _calendar_action_dates(calendar, keys):
    dates = []
    for key in keys:
        dates.extend(_as_dates(_calendar_value(calendar, key)))
    return dates


def _date_check(label, dates, source_available, today, source_detail):
    future_dates = sorted(event_date for event_date in dates if event_date >= today)
    if not source_available:
        return {"Status": "CAUTION", "Reason": "Event data unavailable."}, []
    if not future_dates:
        return {
            "Status": "CAUTION",
            "Reason": (
                "Event information could not be verified from available free data. "
                f"No upcoming {label.lower()} date was supplied by {source_detail}."
            ),
        }, []

    next_date = future_dates[0]
    days_until = (next_date - today).days
    if days_until <= NEAR_TERM_DAYS:
        description = f"{label} on {next_date.isoformat()} ({days_until} day(s) away)"
        return {
            "Status": "CAUTION",
            "Reason": (
                f"Verified upcoming {label.lower()} may materially affect volatility: "
                f"{next_date.isoformat()} ({days_until} day(s) away)."
            ),
        }, [description]
    return {
        "Status": "PASS",
        "Reason": (
            f"Verified next {label.lower()} date is {next_date.isoformat()}, "
            f"outside the {NEAR_TERM_DAYS}-day near-term window."
        ),
    }, []


def _news_check(news, available):
    if not available:
        return {"Status": "CAUTION", "Reason": "Event data unavailable."}
    if isinstance(news, dict):
        items = news.get("news", [])
    elif isinstance(news, (list, tuple)):
        items = news
    else:
        items = []
    if items:
        return {
            "Status": "CAUTION",
            "Reason": (
                f"Yahoo Finance returned {len(items)} news item(s); headlines were not "
                "treated as verified scheduled events."
            ),
        }
    return {
        "Status": "CAUTION",
        "Reason": (
            "Event information could not be verified from available free data. "
            "Yahoo Finance news returned no items in this fetch."
        ),
    }


def _audit_row(row, ticker_factory, today, timestamp):
    ticker = str(row.get("Ticker", "")).strip()
    symbol = ticker if ticker.upper().endswith((".NS", ".BO")) else f"{ticker}.NS"
    try:
        stock = ticker_factory(symbol)
    except Exception:
        stock = None

    if stock is None:
        calendar, calendar_available = None, False
        actions, actions_available = None, False
        news, news_available = None, False
    else:
        calendar, calendar_available = _source(stock, "calendar")
        actions, actions_available = _source(stock, "actions")
        news, news_available = _source(stock, "news")

    earnings_dates = _as_dates(_calendar_value(calendar, "Earnings Date"))
    earnings, earnings_near = _date_check(
        "Earnings",
        earnings_dates,
        calendar_available,
        today,
        "the Yahoo Finance calendar",
    )

    dividend_dates = _as_dates(_calendar_value(calendar, "Ex-Dividend Date"))
    dividend_dates.extend(_future_action_dates(actions, "Dividends", today))
    dividend, dividend_near = _date_check(
        "Dividend / ex-dividend",
        dividend_dates,
        calendar_available or actions_available,
        today,
        "the Yahoo Finance calendar/actions data",
    )

    split_dates = _future_action_dates(actions, "Stock Splits", today)
    split_dates.extend(
        _calendar_action_dates(calendar, ("Stock Split Date", "Split Date", "Bonus Date"))
    )
    split_bonus, split_near = _date_check(
        "Split / bonus / corporate action",
        split_dates,
        calendar_available or actions_available,
        today,
        "the Yahoo Finance calendar/actions data",
    )
    event_news = _news_check(news, news_available)

    near_term_events = earnings_near + dividend_near + split_near
    checks = (earnings, dividend, split_bonus, event_news)
    incomplete = any(check["Status"] == "CAUTION" for check in checks)
    if near_term_events:
        event_status = "CAUTION"
        event_reason = (
            "Verified upcoming event(s) within the 14-day near-term window may materially "
            f"affect volatility: {', '.join(near_term_events)}."
        )
    elif incomplete:
        event_status = "CAUTION"
        event_reason = "Event information could not be verified from available free data."
    else:
        event_status = "PASS"
        event_reason = "No verified near-term event risk found from available free data."

    return {
        "Rank": row.get("Rank"),
        "Ticker": row.get("Ticker"),
        "Raw_Score": row.get("Raw_Score"),
        "Score": row.get("Score"),
        "Status": row.get("Status"),
        "Analysis_Type": "Educational Analysis",
        "Event_Earnings": earnings,
        "Event_Dividend": dividend,
        "Event_Split_Bonus": split_bonus,
        "Event_News": event_news,
        "Event_Risk_Status": event_status,
        "Event_Risk_Reason": event_reason,
        "Event_Risk_Timestamp": timestamp,
    }


def run_top3_event_risk(stock_data, ticker_factory=None, now=None):
    """Check free yfinance event data for, at most, the supplied first three rows."""
    if hasattr(stock_data, "to_dict"):
        rows = stock_data.to_dict(orient="records")
    elif isinstance(stock_data, dict):
        rows = [stock_data]
    else:
        rows = list(stock_data or [])

    if now is None:
        current_time = datetime.now().astimezone()
    elif isinstance(now, datetime):
        current_time = now
    else:
        current_time = datetime.combine(now, datetime.min.time()).astimezone()
    today = current_time.date()
    timestamp = current_time.isoformat(timespec="seconds")
    factory = ticker_factory or yf.Ticker
    return [_audit_row(row, factory, today, timestamp) for row in rows[:3]]
