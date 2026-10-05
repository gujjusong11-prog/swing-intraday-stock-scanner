from datetime import datetime, time as dt_time
from zoneinfo import ZoneInfo
import time
import gc
from pathlib import Path
import csv

IST = ZoneInfo("Asia/Kolkata")

PRE_MARKET_START = dt_time(9, 0)
MARKET_START = dt_time(9, 15)
MARKET_END = dt_time(15, 15)

SCHEDULE_B_INTERVAL = 300
SCHEDULE_C_INTERVAL = 60
SCHEDULER_HEARTBEAT_INTERVAL = 30

MIN_PRICE = 150.0
MAX_PRICE = 450.0
MIN_AVG_VOLUME = 500_000

AUDIT_FILE = "trade_audit_ledger.csv"

daily_universe = []
active_trade = None

last_pre_market_date = None
last_scan_time = None
last_monitor_time = None


def cleanup_memory(*objects):
    for obj in objects:
        try:
            del obj
        except Exception:
            pass
    gc.collect()


def schedule_a_pre_market():
    global daily_universe
    global last_pre_market_date

    now = datetime.now(IST)

    if not (
        PRE_MARKET_START <= now.time() < MARKET_START
    ):
        return

    if last_pre_market_date == now.date():
        return

    from nse_scanner import load_nse_universe
    from parallel_nse_scanner import build_capital_safe_watchlist

    symbols = None
    shortlist = None

    try:
        print("[A] Building pre-market universe...")

        symbols = load_nse_universe()

        shortlist = build_capital_safe_watchlist(
            symbols,
            batch_size=100,
        )

        daily_universe.clear()
        daily_universe.extend(shortlist)

        last_pre_market_date = now.date()

        print(
            f"[A] Universe locked in RAM: "
            f"{len(daily_universe)} stocks"
        )

    finally:
        cleanup_memory(symbols, shortlist)


def schedule_b_live_scanner():
    global last_scan_time

    now = datetime.now(IST)

    if not (
        MARKET_START <= now.time() <= MARKET_END
    ):
        return

    if (
        last_scan_time is not None
        and (now - last_scan_time).total_seconds()
        < SCHEDULE_B_INTERVAL
    ):
        return

    universe = list(daily_universe)

    if not universe:
        print("[B] No pre-market universe available.")
        return

    results = []

    try:
        from eight_parameter_engine import (
            calculate_eight_parameter_setup
        )

        print(
            f"[B] P1-P8 scan started: "
            f"{len(universe)} stocks"
        )

        for ticker in universe:
            try:
                result = calculate_eight_parameter_setup(
                    ticker,
                    mode="Intraday",
                )

                if result:
                    results.append(result)

            except Exception as e:
                print(f"[B] {ticker}: {e}")

        results.sort(
            key=lambda x: int(x.get("Score", 0)),
            reverse=True,
        )

        print(
            f"[B] P1-P8 completed: "
            f"{len(results)} results"
        )

        if results:
            print("[B] TOP 3:")

            for row in results[:3]:
                print(
                    f"{row.get('Ticker','')} | "
                    f"Score={row.get('Score','')} | "
                    f"Status={row.get('Status','')}"
                )

    finally:
        last_scan_time = now
        cleanup_memory(results, universe)


def schedule_c_trade_monitor():
    global active_trade
    global last_monitor_time

    if active_trade is None:
        return

    now = datetime.now(IST)

    if (
        last_monitor_time is not None
        and (now - last_monitor_time).total_seconds()
        < SCHEDULE_C_INTERVAL
    ):
        return

    stock = active_trade.get("stock")

    print(
        f"[C] Active trade monitor: {stock}"
    )

    # Live price/volume integration will use
    # the existing project data function.
    #
    # No historical candle dataframe is stored here.

    last_monitor_time = now

    gc.collect()


def register_active_trade(
    stock,
    entry,
    target=None,
    stop_loss=None,
    pre_30m_vol_burst="",
    pre_range_pct="",
):
    global active_trade

    active_trade = {
        "stock": stock,
        "entry": float(entry),
        "target": target,
        "stop_loss": stop_loss,
        "pre_30m_vol_burst": pre_30m_vol_burst,
        "pre_range_pct": pre_range_pct,
        "entry_time": datetime.now(IST),
    }

    print(
        f"[C] Active trade registered: {stock}"
    )


def close_active_trade(exit_price, outcome):
    global active_trade

    if active_trade is None:
        return

    now = datetime.now(IST)

    entry = float(active_trade["entry"])
    exit_price = float(exit_price)

    pnl_pct = (
        (exit_price - entry) / entry
    ) * 100

    minutes_held = int(
        (
            now - active_trade["entry_time"]
        ).total_seconds() / 60
    )

    columns = [
        "Date",
        "Stock",
        "Entry",
        "Exit",
        "PnL_Pct",
        "Outcome",
        "Pre_30m_Vol_Burst",
        "Pre_Range_Pct",
        "Minutes_Held",
    ]

    file_exists = Path(AUDIT_FILE).exists()

    with open(
        AUDIT_FILE,
        "a",
        newline="",
        encoding="utf-8",
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=columns,
        )

        if not file_exists:
            writer.writeheader()

        writer.writerow({
            "Date": now.strftime("%Y-%m-%d"),
            "Stock": active_trade["stock"],
            "Entry": round(entry, 4),
            "Exit": round(exit_price, 4),
            "PnL_Pct": round(pnl_pct, 2),
            "Outcome": outcome,
            "Pre_30m_Vol_Burst": active_trade[
                "pre_30m_vol_burst"
            ],
            "Pre_Range_Pct": active_trade[
                "pre_range_pct"
            ],
            "Minutes_Held": minutes_held,
        })

    print(
        f"[C] Trade closed and audited: "
        f"{active_trade['stock']}"
    )

    active_trade = None
    gc.collect()


def print_scheduler_heartbeat(now=None):
    now = now or datetime.now(IST)
    current_time = now.time()

    if last_pre_market_date == now.date():
        a_status = "DONE"
    elif PRE_MARKET_START <= current_time < MARKET_START:
        a_status = "READY"
    else:
        a_status = "WAIT"

    b_status = (
        "READY"
        if MARKET_START <= current_time <= MARKET_END and daily_universe
        else "WAIT"
    )
    c_status = "MONITORING" if active_trade is not None else "IDLE"

    print(
        f"[SCHEDULER] {now.strftime('%H:%M:%S')} | "
        f"A={a_status} | B={b_status} | C={c_status}",
        flush=True,
    )


def run_scheduler():
    print("=" * 60)
    print("STRICT SCANNER SCHEDULER")
    print("Timezone: Asia/Kolkata")
    print("A: 09:00-09:15 | Once")
    print("B: 09:15-15:15 | Every 5 Minutes")
    print("C: Active Trade | Every 1 Minute")
    print("=" * 60)

    last_heartbeat = 0.0

    while True:
        try:
            monotonic_now = time.monotonic()
            if (
                monotonic_now - last_heartbeat
                >= SCHEDULER_HEARTBEAT_INTERVAL
            ):
                print_scheduler_heartbeat()
                last_heartbeat = monotonic_now

            schedule_a_pre_market()
            schedule_b_live_scanner()
            schedule_c_trade_monitor()

            time.sleep(1)

        except KeyboardInterrupt:
            print("Scheduler stopped.")
            daily_universe.clear()
            gc.collect()
            break

        except Exception as e:
            print(f"[SCHEDULER ERROR] {e}")
            gc.collect()
            time.sleep(2)


if __name__ == "__main__":
    run_scheduler()
