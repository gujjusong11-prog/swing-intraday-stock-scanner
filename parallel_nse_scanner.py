import concurrent.futures
import gc
import os
import threading
import traceback
from software_diagnostics import RuntimeErrorRecord, diagnose_runtime_error
import time
import yfinance as yf
import pandas as pd
import asyncio

from software_notifier import send_scanner_message

from eight_parameter_engine import calculate_eight_parameter_setup
from nse_scanner import load_nse_universe, rank_results, is_candidate_pre_filter
from data_quality import validate_data_quality
from capital_risk_engine import MAX_EXPOSURE, apply_capital_risk, daily_loss_limit_reached
from trade_ledger import record_qualifying_setup
from top3_ai_audit import run_top3_ai_audit


MAX_WORKERS = 25
MIN_REQUEST_INTERVAL_SECONDS = 0.15
_request_lock = threading.Lock()
_last_request_started = 0.0
_failed_symbols = []
_failed_symbols_lock = threading.Lock()
_data_quality_results = []
_data_quality_lock = threading.Lock()
_capital_filter_metrics = {}
_capital_filter_rejections = []
_capital_filter_lock = threading.Lock()


def _record_data_quality(result):
    with _data_quality_lock:
        _data_quality_results.append(result)


def get_data_quality_results():
    with _data_quality_lock:
        return [result.copy() for result in _data_quality_results]


def get_capital_filter_metrics():
    with _capital_filter_lock:
        return {symbol: metrics.copy() for symbol, metrics in _capital_filter_metrics.items()}


def get_smart_filter_rejections():
    with _capital_filter_lock:
        return [row.copy() for row in _capital_filter_rejections]


def _symbol_key(symbol):
    return str(symbol or "").strip().upper().removesuffix(".NS")


def _finite_number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if pd.notna(number) and number not in (float("inf"), float("-inf")) else None


def _validate_configured_daily_loss(value, as_of, current_date):
    loss = _finite_number(value)
    if loss is None or loss < 0:
        raise ValueError("REALIZED_DAILY_LOSS must be a finite, non-negative value")
    if as_of != current_date:
        raise ValueError("REALIZED_DAILY_LOSS_AS_OF must match today's market date")
    return loss


def _throttled_history(stock, symbol, **kwargs):
    global _last_request_started

    for attempt in range(3):
        with _request_lock:
            wait = MIN_REQUEST_INTERVAL_SECONDS - (
                time.monotonic() - _last_request_started
            )
            if wait > 0:
                time.sleep(wait)
            _last_request_started = time.monotonic()

        try:
            return stock.history(**kwargs)
        except Exception as exc:
            message = str(exc)
            response = getattr(exc, "response", None)
            status_code = getattr(response, "status_code", None)
            is_rate_limited = status_code == 429 or "429" in message or "too many requests" in message.lower()
            if not is_rate_limited or attempt == 2:
                print(f"[DATA ERROR] {symbol}: {message}")
                raise
            delay = 2 ** attempt
            print(f"[RETRY] {symbol}: HTTP 429; retrying in {delay}s")
            time.sleep(delay)


def scan_single_stock(symbol):
    daily = None
    intraday = None
    quality_result = None
    quality_recorded = False
    try:
        yf_symbol = symbol if symbol.endswith(".NS") else f"{symbol}.NS"
        time.sleep(0.15)
        stock = yf.Ticker(yf_symbol)

        daily = _throttled_history(
            stock,
            symbol,
            period="1y",
            interval="1d",
            auto_adjust=False,
        )
        intraday = _throttled_history(
            stock,
            symbol,
            period="5d",
            interval="5m",
            auto_adjust=False,
        )

        quality_result = validate_data_quality(symbol, daily, intraday)
        if quality_result["Data_Quality_Status"] == "FAIL":
            _record_data_quality(quality_result)
            quality_recorded = True
            return None

        result = calculate_eight_parameter_setup(symbol, daily_data=daily, intraday_data=intraday)
        quality_result = validate_data_quality(symbol, daily, intraday, result)
        _record_data_quality(
            quality_result
        )
        quality_recorded = True

        if (
            result
            and quality_result["Data_Quality_Status"] != "FAIL"
            and is_candidate_pre_filter(result)
        ):
            result["Data_Quality_Status"] = quality_result["Data_Quality_Status"]
            result["Data_Quality_Reason"] = quality_result["Data_Quality_Reason"]
            result["Data_Quality_Timestamp"] = quality_result["Data_Quality_Timestamp"]
            return result

        return None

    except Exception as exc:
        if not quality_recorded:
            if quality_result is None:
                quality_result = validate_data_quality(symbol, daily, intraday)
            _record_data_quality(quality_result)
        with _failed_symbols_lock:
            _failed_symbols.append(symbol)
        print(f"[SCAN ERROR] {symbol}: {exc}")
        return None



MIN_CAPITAL_PRICE = 150.0
MAX_CAPITAL_PRICE = 450.0
MIN_AVG_DAILY_TURNOVER = MAX_EXPOSURE
AVG_VOLUME_DAYS = 20
MAX_P4_CANDIDATES = 12
MIN_P4_TARGET_CANDIDATES = 8


def _evaluate_capital_filter(frame):
    if not isinstance(frame, pd.DataFrame):
        return None, "DATA UNAVAILABLE: daily frame missing"
    if not {"Close", "Volume"}.issubset(frame.columns):
        return None, "DATA UNAVAILABLE: Close or Volume missing"

    values = frame[["Close", "Volume"]].apply(pd.to_numeric, errors="coerce")
    values = values.replace([float("inf"), float("-inf")], float("nan")).dropna()
    if len(values) < AVG_VOLUME_DAYS:
        return None, f"DATA UNAVAILABLE: fewer than {AVG_VOLUME_DAYS} daily observations"

    recent = values.tail(AVG_VOLUME_DAYS)
    latest_price = float(recent["Close"].iloc[-1])
    average_volume = float(recent["Volume"].mean())
    average_turnover = float((recent["Close"] * recent["Volume"]).mean())
    if (
        not all(pd.notna(value) and value > 0 for value in (
            latest_price,
            average_volume,
            average_turnover,
        ))
    ):
        return None, "DATA UNAVAILABLE: invalid price, volume, or turnover"

    metrics = {
        "Liquidity_LTP": latest_price,
        "Liquidity_Avg_Daily_Volume": average_volume,
        "Liquidity_Avg_Daily_Turnover": average_turnover,
    }
    if not MIN_CAPITAL_PRICE <= latest_price <= MAX_CAPITAL_PRICE:
        return metrics, f"PRICE_OUTSIDE_RANGE: Rs.{latest_price:.2f}"
    if average_volume <= 0 or average_turnover < MIN_AVG_DAILY_TURNOVER:
        return metrics, (
            f"LOW_LIQUIDITY: 20-day average turnover Rs.{average_turnover:.0f} "
            f"is below production exposure limit Rs.{MIN_AVG_DAILY_TURNOVER:.0f}"
        )
    return metrics, None


def apply_smart_pre_filter(
    candidates,
    data_quality_results,
    liquidity_metrics,
    candidate_limit=MAX_P4_CANDIDATES,
):
    """Apply P4 quality gates to already-scanned and risk-approved rows."""
    if candidate_limit < 1:
        raise ValueError("candidate_limit must be at least 1")

    if candidates.empty:
        empty = candidates.copy()
        empty["Filter_Status"] = pd.Series(dtype="object")
        empty["Filter_Reason"] = pd.Series(dtype="object")
        return empty, pd.DataFrame()

    quality_by_symbol = {
        _symbol_key(row.get("Ticker")): row
        for row in data_quality_results
    }
    liquidity_by_symbol = {
        _symbol_key(symbol): metrics
        for symbol, metrics in liquidity_metrics.items()
    }
    accepted = []
    rejected = []

    for _, candidate in candidates.iterrows():
        row = candidate.to_dict()
        symbol = _symbol_key(row.get("Ticker"))
        quality = quality_by_symbol.get(symbol, {})
        liquidity = liquidity_by_symbol.get(symbol, {})

        price = _finite_number(row.get("LTP"))
        average_volume = _finite_number(liquidity.get("Liquidity_Avg_Daily_Volume"))
        average_turnover = _finite_number(liquidity.get("Liquidity_Avg_Daily_Turnover"))
        relative_volume = _finite_number(row.get("Volume_Ratio"))
        atr = _finite_number(row.get("ATR_14"))
        score = _finite_number(row.get("Raw_Score"))
        risk_reward = _finite_number(row.get("Risk_Reward_Calculated"))
        if risk_reward is None:
            risk_reward = _finite_number(row.get("Reward_Risk_Ratio"))
        data_status = str(quality.get("Data_Quality_Status", "DATA UNAVAILABLE"))

        price_pass = price is not None and MIN_CAPITAL_PRICE <= price <= MAX_CAPITAL_PRICE
        liquidity_pass = (
            average_volume is not None
            and average_volume > 0
            and average_turnover is not None
            and average_turnover >= MIN_AVG_DAILY_TURNOVER
        )
        rvol_pass = relative_volume is not None and relative_volume >= 1.5
        atr_pass = atr is not None and atr > 0 and price is not None and price > 0
        technical_pass = (
            row.get("Status") == "Bullish Setup Detected"
            and score == 8
            and risk_reward is not None
            and risk_reward >= 2.0
        )
        data_quality_pass = data_status == "PASS"

        reasons = [
            f"Price {'PASS' if price_pass else 'FAIL'}"
            + (f" (Rs.{price:.2f})" if price is not None else " (DATA UNAVAILABLE)"),
            f"Liquidity {'PASS' if liquidity_pass else 'FAIL'}"
            + (
                f" (20-day avg volume {average_volume:.0f}; avg turnover Rs.{average_turnover:.0f})"
                if average_volume is not None and average_turnover is not None
                else " (DATA UNAVAILABLE)"
            ),
            f"RVol {'PASS' if rvol_pass else 'FAIL'}"
            + (f" ({relative_volume:.2f}x)" if relative_volume is not None else " (DATA UNAVAILABLE)"),
            f"ATR {'PASS' if atr_pass else 'FAIL'}"
            + (f" ({atr:.4f})" if atr is not None else " (DATA UNAVAILABLE)"),
            f"P1-P8 {'PASS' if technical_pass else 'FAIL'}"
            + (f" ({score:.0f}/8, R:R {risk_reward:.2f})" if score is not None and risk_reward is not None else " (DATA UNAVAILABLE)"),
            f"Data Quality {'PASS' if data_quality_pass else 'FAIL'} ({data_status})",
        ]
        if not data_quality_pass and quality.get("Data_Quality_Reason"):
            reasons.append(str(quality["Data_Quality_Reason"]))

        row.update({
            "Data_Quality_Status": data_status,
            "Data_Quality_Reason": quality.get("Data_Quality_Reason", "DATA UNAVAILABLE"),
            "Liquidity_Avg_Daily_Volume": average_volume,
            "Liquidity_Avg_Daily_Turnover": average_turnover,
            "ATR_Percent": (atr / price * 100) if atr_pass else None,
            "Filter_Status": "PASS" if all((
                price_pass,
                liquidity_pass,
                rvol_pass,
                atr_pass,
                technical_pass,
                data_quality_pass,
            )) else "REJECTED",
            "Filter_Reason": " | ".join(reasons),
        })
        if row["Filter_Status"] == "PASS":
            accepted.append(row)
        else:
            rejected.append(row)

    if not accepted:
        return pd.DataFrame(columns=list(candidates.columns) + [
            "Data_Quality_Status", "Data_Quality_Reason",
            "Liquidity_Avg_Daily_Volume", "Liquidity_Avg_Daily_Turnover",
            "ATR_Percent", "Filter_Status", "Filter_Reason",
        ]), pd.DataFrame(rejected)

    accepted_frame = pd.DataFrame(accepted).sort_values(
        by=["Raw_Score", "Volume_Ratio", "Liquidity_Avg_Daily_Turnover"],
        ascending=[False, False, False],
        na_position="last",
        kind="stable",
    ).reset_index(drop=True)
    overflow = accepted_frame.iloc[candidate_limit:].copy()
    if not overflow.empty:
        overflow["Filter_Status"] = "REJECTED"
        overflow["Filter_Reason"] = f"CANDIDATE_LIMIT: P4 retains at most {candidate_limit} candidates"
        rejected.extend(overflow.to_dict("records"))

    accepted_frame = accepted_frame.head(candidate_limit).copy()
    accepted_frame.insert(0, "Candidate_Rank", range(1, len(accepted_frame) + 1))
    return accepted_frame, pd.DataFrame(rejected)


def build_capital_safe_watchlist(symbols, batch_size=500):
    """
    Capital & Liquidity Pre-Filter.
    Only stocks satisfying:
      150 <= latest daily close <= 450
    20-day average daily turnover >= maximum production exposure
    reach the P1-P8 engine.
    """
    watchlist = []
    metrics_by_symbol = {}
    rejections = []

    for start in range(0, len(symbols), batch_size):
        batch = [
            symbol if symbol.endswith(".NS") else f"{symbol}.NS"
            for symbol in symbols[start:start + batch_size]
        ]

        try:
            data = yf.download(
                batch,
                period="25d",
                interval="1d",
                auto_adjust=False,
                progress=False,
                threads=True,
                group_by="ticker",
            )

            for symbol in batch:
                try:
                    ticker = (
                        symbol
                        if symbol.endswith(".NS")
                        else f"{symbol}.NS"
                    )

                    if isinstance(getattr(data, "columns", None), pd.MultiIndex):
                        levels = data.columns.get_level_values(0)

                        if ticker not in levels:
                            rejections.append({
                                "Ticker": _symbol_key(symbol),
                                "Filter_Status": "REJECTED",
                                "Filter_Reason": "DATA UNAVAILABLE: no daily data returned",
                            })
                            continue

                        df = data[ticker].copy()
                    else:
                        df = data.copy()

                    metrics, reason = _evaluate_capital_filter(df)
                    if metrics is not None:
                        metrics_by_symbol[_symbol_key(symbol)] = metrics
                    if reason is None:
                        watchlist.append(ticker)
                    else:
                        rejections.append({
                            "Ticker": _symbol_key(symbol),
                            "Filter_Status": "REJECTED",
                            "Filter_Reason": reason,
                            **(metrics or {}),
                        })

                except Exception:
                    rejections.append({
                        "Ticker": _symbol_key(symbol),
                        "Filter_Status": "REJECTED",
                        "Filter_Reason": "DATA UNAVAILABLE: daily prefilter evaluation failed",
                    })
                    continue

            del data
            gc.collect()

        except Exception as exc:
            for symbol in batch:
                rejections.append({
                    "Ticker": _symbol_key(symbol),
                    "Filter_Status": "REJECTED",
                    "Filter_Reason": f"DATA UNAVAILABLE: daily batch failed ({type(exc).__name__})",
                })
            print(
                f"[CAPITAL PREFILTER ERROR] "
                f"{start}-{start + len(batch)}: {exc}"
            )

    with _capital_filter_lock:
        _capital_filter_metrics.clear()
        _capital_filter_metrics.update(metrics_by_symbol)
        _capital_filter_rejections[:] = rejections

    print("=" * 70)
    print("CAPITAL-SAFE PRE-FILTER")
    print("=" * 70)
    print(f"Universe          : {len(symbols)}")
    print(f"Price Range       : Rs.{MIN_CAPITAL_PRICE:.0f}-Rs.{MAX_CAPITAL_PRICE:.0f}")
    print(f"Min Avg Turnover  : Rs.{MIN_AVG_DAILY_TURNOVER:,.0f}")
    print("Liquidity Metric  : 20-day average daily traded turnover")
    print(f"P1-P8 Watchlist   : {len(watchlist)}")
    print("=" * 70)

    return watchlist


def scan_parallel(symbols, max_workers=MAX_WORKERS, realized_daily_loss=None):
    if realized_daily_loss is None:
        print("Daily realized loss unavailable; setup generation blocked.")
        return pd.DataFrame(columns=FINAL_OUTPUT_COLUMNS)

    if daily_loss_limit_reached(realized_daily_loss):
        print("Daily loss limit reached; setup generation blocked.")
        return pd.DataFrame(columns=FINAL_OUTPUT_COLUMNS)

    global _failed_symbols, _data_quality_results
    with _failed_symbols_lock:
        _failed_symbols = []
    with _data_quality_lock:
        _data_quality_results = []
    with _capital_filter_lock:
        _capital_filter_metrics.clear()
        _capital_filter_rejections.clear()

    # Capital-aligned pre-filter BEFORE P1-P8
    original_symbol_count = len(symbols)
    symbols = build_capital_safe_watchlist(symbols)

    print(
        f"Capital pre-filter: {original_symbol_count} -> "
        f"{len(symbols)} stocks before P1-P8"
    )
    start = time.perf_counter()

    results = []
    completed = 0
    total = len(symbols)

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=max_workers
    ) as executor:

        futures = {
            executor.submit(scan_single_stock, symbol): symbol
            for symbol in symbols
        }

        for future in concurrent.futures.as_completed(futures):
            completed += 1

            try:
                result = future.result()
                if result:
                    results.append(result)
            except Exception as exc:
                diagnostic_record = RuntimeErrorRecord(
                    file_name="parallel_nse_scanner.py",
                    function_name="scan_parallel",
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                    traceback_text=traceback.format_exc(),
                    context=f"scan_parallel future failed for symbol={futures.get(future)}",
                )
                diagnose_runtime_error(
                    file_name=diagnostic_record.file_name,
                    function_name=diagnostic_record.function_name,
                    error_message=(
                        f"{diagnostic_record.error_type}: "
                        f"{diagnostic_record.error_message}"
                    ),
                    traceback_text=diagnostic_record.traceback_text,
                    context=diagnostic_record.context,
                )

            if completed % 5 == 0 or completed == total:
                print(
                    f"Parallel Progress: {completed}/{total} | "
                    f"Candidates: {len(results)}"
                )

    elapsed = time.perf_counter() - start

    print()
    print("=" * 70)
    print("PARALLEL SCAN TEST")
    print("=" * 70)
    print(f"Stocks Tested     : {total}")
    print(f"Workers            : {max_workers}")
    print(f"Candidates         : {len(results)}")
    print(f"Elapsed Time       : {elapsed:.2f} seconds")
    print("=" * 70)

    ranked = rank_results(results)
    risk_input = ranked.copy()
    if "Raw_Score" in risk_input.columns:
        risk_input["Score"] = risk_input["Raw_Score"]
    risk_approved = apply_capital_risk(risk_input, realized_daily_loss)
    quality_results = get_data_quality_results()
    smart_candidates, filter_rejections = apply_smart_pre_filter(
        risk_approved,
        quality_results,
        get_capital_filter_metrics(),
    )
    with _capital_filter_lock:
        _capital_filter_rejections.extend(filter_rejections.to_dict("records"))
        existing_rejections = {
            _symbol_key(row.get("Ticker"))
            for row in _capital_filter_rejections
        }
        for quality in quality_results:
            symbol = _symbol_key(quality.get("Ticker"))
            if (
                quality.get("Data_Quality_Status") != "PASS"
                and symbol not in existing_rejections
            ):
                _capital_filter_rejections.append({
                    "Ticker": symbol,
                    "Filter_Status": "REJECTED",
                    "Filter_Reason": (
                        f"DATA QUALITY {quality.get('Data_Quality_Status', 'DATA UNAVAILABLE')}: "
                        f"{quality.get('Data_Quality_Reason', 'reason unavailable')}"
                    ),
                })

    print(
        f"P4 smart filter     : {len(smart_candidates)} candidates "
        f"(target {MIN_P4_TARGET_CANDIDATES}-{MAX_P4_CANDIDATES}; no padding)"
    )

    recorded_results = []
    for _, row in smart_candidates.iterrows():
        try:
            trade_id = record_qualifying_setup(row.to_dict())
            if trade_id:
                recorded_row = row.copy()
                recorded_row["Trade_ID"] = trade_id
                recorded_results.append(recorded_row)
            else:
                print(f"[LEDGER SKIP] {row.get('Ticker', '')}: setup was not recordable")
        except Exception as exc:
            print(f"[LEDGER ERROR] {row.get('Ticker', '')}: {exc}")

    if not recorded_results:
        return prepare_final_output(smart_candidates.iloc[0:0].copy())

    return prepare_final_output(pd.DataFrame(recorded_results))


FINAL_OUTPUT_COLUMNS = [
    "Rank",
    "Ticker",
    "LTP",
    "Raw_Score",
    "Score",
    "Status",
    "Analysis_Type",
    "P1_Primary_Trend",
    "P2_Short_Momentum",
    "P3_Pullback_Detection",
    "P4_Reversal_Confirmation",
    "P5_Volume_Surge",
    "P6_RSI_Filter",
    "P7_Previous_High_Trigger",
    "P8_Risk_Reward",
    "RSI_14",
    "Volume_Ratio",
    "Risk_Reward",
    "Stop_Loss",
    "Target",
    "Target_Gain_Percent",
]


def prepare_final_output(ranked):
    if ranked.empty:
        return ranked

    output = ranked.copy()
    output["Target_Gain_Percent"] = output["Target_Percent"]
    extra_columns = [
        column
        for column in output.columns
        if column not in FINAL_OUTPUT_COLUMNS
    ]
    return output[FINAL_OUTPUT_COLUMNS + extra_columns]


if __name__ == "__main__":
    try:
        configured_loss = os.getenv("REALIZED_DAILY_LOSS", "").strip()
        if configured_loss:
            current_market_date = pd.Timestamp.now(tz="Asia/Kolkata").date().isoformat()
            realized_daily_loss = _validate_configured_daily_loss(
                configured_loss,
                os.getenv("REALIZED_DAILY_LOSS_AS_OF", "").strip(),
                current_market_date,
            )
        else:
            realized_daily_loss = float(
                input("Today's realized loss in Rs. (enter 0 if verified): ")
            )
        universe = load_nse_universe()
        ranked = scan_parallel(
            universe,
            realized_daily_loss=realized_daily_loss,
        )

        if ranked.empty:
            print("No risk-approved setups found.")
        else:
            print()
            print(ranked[FINAL_OUTPUT_COLUMNS].to_string(index=False))

            bullish = ranked[
                ranked["Status"].eq("Bullish Setup Detected")
            ]

            if not bullish.empty:
                top = bullish.head(3)

                details = top[[
                    "Ticker",
                    "LTP",
                    "Score",
                    "Risk_Reward",
                    "Stop_Loss",
                    "Target",
                    "Target_Gain_Percent",
                    "Allocated_Qty",
                    "Max_Theoretical_Loss",
                ]].to_string(index=False)
                timestamp = pd.Timestamp.now(tz="Asia/Kolkata").isoformat(timespec="seconds")
                message = (
                    "SWING & INTRADAY SCANNER\n\n"
                    "Bullish Setup Detected\n"
                    f"{details}\n\n"
                    f"Top-3 Educational Analysis:\n{educational_analysis}\n\n"
                    f"Timestamp: {timestamp}\n"
                    "Educational Analysis. Risk Warning: market gaps and slippage may cause losses beyond estimates."
                )
                sent = asyncio.run(send_scanner_message(message))
                print("Telegram Bot-2 delivery: SENT" if sent else "Telegram Bot-2 delivery: DATA UNAVAILABLE")
    except (EOFError, ValueError) as exc:
        print(f"DATA UNAVAILABLE: verified realized daily loss required; setup generation blocked: {exc}")
        raise SystemExit(2) from exc








