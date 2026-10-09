import csv
import math
import os
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from capital_risk_engine import CAPITAL


IST = ZoneInfo("Asia/Kolkata")
AUDIT_FILE = Path(__file__).with_name("trade_audit_ledger.csv")
EXIT_REASONS = {
    "TARGET_HIT",
    "STOP_LOSS_HIT",
    "EOD_SQUARE_OFF",
    "MANUAL_EXIT",
    "INVALIDATED",
}
LEDGER_FIELDS = [
    "Trade_ID",
    "Date",
    "Entry_Time",
    "Symbol",
    "Entry_Price",
    "Planned_SL",
    "Planned_Target",
    "Allocated_Qty",
    "Entry_Reason",
    "Technical_RVol",
    "Technical_ATR",
    "Technical_VWAP",
    "Pre_Range_Compression_Pct",
    "Risk_Per_Trade",
    "Position_Exposure",
    "Risk_Reward",
    "Exit_Time",
    "Exit_Price",
    "Exit_Reason",
    "Gross_PnL",
    "Brokerage",
    "Slippage",
    "Net_PnL",
    "Capital_Return_Pct",
]
_LEDGER_LOCK = threading.RLock()


def _number(value):
    if value is None or isinstance(value, str) and not value.strip():
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _cell(value):
    if value is None:
        return ""
    try:
        if not math.isfinite(float(value)):
            return ""
    except (TypeError, ValueError):
        pass
    return value


def _read_rows(path):
    if not path.exists():
        return list(LEDGER_FIELDS), []

    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        existing_fields = reader.fieldnames or []
        fields = list(existing_fields)
        fields.extend(field for field in LEDGER_FIELDS if field not in fields)
        rows = [dict(row) for row in reader]
    return fields, rows


def _write_rows(path, fields, rows):
    path = Path(path)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            newline="",
            encoding="utf-8",
            dir=path.parent,
            prefix=f"{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def read_trade_records(path=None):
    ledger_path = Path(path) if path is not None else AUDIT_FILE
    with _LEDGER_LOCK:
        _, rows = _read_rows(ledger_path)
        return rows


def _is_open(row):
    exit_price = row.get("Exit_Price", "")
    exit_time = row.get("Exit_Time", "")
    if str(exit_price or "").strip() or str(exit_time or "").strip():
        return False
    # Preserve legacy closed rows that used the old Exit column.
    return not str(row.get("Exit", "") or "").strip()


def _entry_reason(setup, risk_reward):
    score = setup.get("Raw_Score", setup.get("Score"))
    parts = ["Bullish Setup Detected", f"P1-P8 Score {score}/8"]

    rvol = _number(setup.get("Volume_Ratio"))
    if rvol is not None:
        parts.append(f"RVol {rvol:g}x")

    atr = _number(setup.get("ATR_14"))
    if atr is not None:
        parts.append(f"ATR {atr:g}")

    parts.append(f"R:R {risk_reward:g}")
    parts.append("Educational Analysis")
    return " | ".join(parts)


def record_qualifying_setup(setup, path=None, now=None):
    """Persist one risk-approved setup, reusing an already-open symbol record."""
    if not isinstance(setup, dict):
        return None
    if setup.get("Status") != "Bullish Setup Detected":
        return None

    score = _number(setup.get("Raw_Score", setup.get("Score")))
    symbol = str(setup.get("Ticker") or setup.get("Symbol") or "").strip().upper()
    entry = _number(setup.get("Entry_Reference", setup.get("LTP")))
    planned_sl = _number(setup.get("Stop_Loss", setup.get("Planned_SL")))
    target = _number(setup.get("Target", setup.get("Planned_Target")))
    quantity = _number(setup.get("Allocated_Qty"))
    risk = _number(setup.get("Max_Theoretical_Loss", setup.get("Risk_Per_Trade")))
    exposure = _number(setup.get("Position_Exposure"))
    risk_reward = _number(setup.get("Risk_Reward_Calculated"))

    if (
        score != 8
        or not symbol
        or entry is None or entry <= 0
        or planned_sl is None or planned_sl <= 0
        or target is None or target <= 0
        or quantity is None or quantity <= 0 or not quantity.is_integer()
        or risk is None or risk <= 0
        or exposure is None or exposure <= 0
        or risk_reward is None or risk_reward < 2.0
    ):
        return None

    timestamp = now or datetime.now(IST)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=IST)
    else:
        timestamp = timestamp.astimezone(IST)
    ledger_path = Path(path) if path is not None else AUDIT_FILE
    symbol_id = "".join(character for character in symbol if character.isalnum())

    with _LEDGER_LOCK:
        fields, rows = _read_rows(ledger_path)

        for row in rows:
            if row.get("Trade_ID") and row.get("Trade_ID") == setup.get("Trade_ID"):
                return row["Trade_ID"]
            if row.get("Symbol", "").strip().upper() == symbol and _is_open(row):
                return row.get("Trade_ID") or None

        trade_id = setup.get("Trade_ID") or (
            f"TRD_{timestamp.strftime('%Y%m%d_%H%M%S_%f')}_{symbol_id}"
        )
        if any(row.get("Trade_ID") == trade_id for row in rows):
            return trade_id

        record = {field: "" for field in fields}
        record.update({
            "Trade_ID": trade_id,
            "Date": timestamp.strftime("%Y-%m-%d"),
            "Entry_Time": timestamp.strftime("%H:%M:%S.%f%z"),
            "Symbol": symbol,
            "Entry_Price": entry,
            "Planned_SL": planned_sl,
            "Planned_Target": target,
            "Allocated_Qty": int(quantity),
            "Entry_Reason": _entry_reason(setup, risk_reward),
            "Technical_RVol": _cell(setup.get("Volume_Ratio")),
            "Technical_ATR": _cell(setup.get("ATR_14")),
            "Technical_VWAP": _cell(setup.get("Technical_VWAP", setup.get("VWAP"))),
            "Pre_Range_Compression_Pct": _cell(
                setup.get("Pre_Range_Compression_Pct")
            ),
            "Risk_Per_Trade": risk,
            "Position_Exposure": exposure,
            "Risk_Reward": risk_reward,
        })
        rows.append(record)
        _write_rows(ledger_path, fields, rows)
        return trade_id


def _apply_exit(row, exit_price, exit_reason, brokerage, slippage, timestamp):
    entry = _number(row.get("Entry_Price"))
    quantity = _number(row.get("Allocated_Qty"))
    exit_value = _number(exit_price)
    if entry is None or quantity is None or exit_value is None:
        return False

    brokerage_value = _number(brokerage)
    slippage_value = _number(slippage)
    if brokerage_value is not None and brokerage_value < 0:
        return False
    if slippage_value is not None and slippage_value < 0:
        return False

    gross_pnl = (exit_value - entry) * quantity
    costs_known = brokerage_value is not None and slippage_value is not None
    net_pnl = gross_pnl - brokerage_value - slippage_value if costs_known else None

    row.update({
        "Exit_Time": timestamp.strftime("%H:%M:%S.%f%z"),
        "Exit_Price": exit_value,
        "Exit_Reason": exit_reason,
        "Gross_PnL": gross_pnl,
        "Brokerage": brokerage_value if brokerage_value is not None else "",
        "Slippage": slippage_value if slippage_value is not None else "",
        "Net_PnL": net_pnl if net_pnl is not None else "",
        "Capital_Return_Pct": (
            net_pnl / CAPITAL * 100 if net_pnl is not None else ""
        ),
    })
    return True


def update_trade_exit(
    trade_id,
    exit_price,
    exit_reason,
    brokerage=None,
    slippage=None,
    path=None,
    now=None,
):
    if not trade_id or exit_reason not in EXIT_REASONS:
        return False

    timestamp = now or datetime.now(IST)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=IST)
    else:
        timestamp = timestamp.astimezone(IST)
    ledger_path = Path(path) if path is not None else AUDIT_FILE

    with _LEDGER_LOCK:
        fields, rows = _read_rows(ledger_path)
        for row in rows:
            if row.get("Trade_ID") != trade_id:
                continue
            if not _is_open(row):
                return False
            if not _apply_exit(row, exit_price, exit_reason, brokerage, slippage, timestamp):
                return False
            _write_rows(ledger_path, fields, rows)
            return True
    return False


def update_open_trade_exit(
    symbol,
    exit_price,
    exit_reason,
    brokerage=None,
    slippage=None,
    path=None,
    now=None,
):
    normalized_symbol = str(symbol or "").strip().upper()
    if not normalized_symbol:
        return False

    ledger_path = Path(path) if path is not None else AUDIT_FILE
    with _LEDGER_LOCK:
        _, rows = _read_rows(ledger_path)
        for row in reversed(rows):
            if (
                row.get("Symbol", "").strip().upper() == normalized_symbol
                and _is_open(row)
            ):
                trade_id = row.get("Trade_ID")
                if not trade_id:
                    return False
                return update_trade_exit(
                    trade_id,
                    exit_price,
                    exit_reason,
                    brokerage=brokerage,
                    slippage=slippage,
                    path=ledger_path,
                    now=now,
                )
    return False
