import concurrent.futures
import gc
import threading
import traceback
from software_diagnostics import RuntimeErrorRecord, diagnose_runtime_error
import time
import yfinance as yf
import pandas as pd

from eight_parameter_engine import calculate_eight_parameter_setup, _rsi
from nse_scanner import load_nse_universe, rank_results, is_candidate_pre_filter
from data_quality import validate_data_quality


MAX_WORKERS = 25
MIN_REQUEST_INTERVAL_SECONDS = 0.15
_request_lock = threading.Lock()
_last_request_started = 0.0
_failed_symbols = []
_failed_symbols_lock = threading.Lock()
_data_quality_results = []
_data_quality_lock = threading.Lock()


def _record_data_quality(result):
    with _data_quality_lock:
        _data_quality_results.append(result)


def get_data_quality_results():
    with _data_quality_lock:
        return [result.copy() for result in _data_quality_results]


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


def passes_raw_5m_prefilter(intraday):
    if not isinstance(intraday, pd.DataFrame):
        return False

    required = {"Open", "High", "Low", "Close", "Volume"}
    if not required.issubset(intraday.columns):
        return False

    df = intraday[list(required)].copy().dropna()

    if len(df) < 20:
        return False

    df["EMA20"] = df["Close"].ewm(span=20, adjust=False).mean()
    df["RSI14"] = _rsi(df["Close"], 14)
    df["Volume_SMA20"] = df["Volume"].rolling(20).mean()

    latest_day = df.index[-1].date()
    today_df = df[df.index.date == latest_day]

    if today_df.empty:
        return False

    latest = today_df.iloc[-1]

    try:
        close = float(latest["Close"])
        ema20 = float(latest["EMA20"])
        rsi14 = float(latest["RSI14"])
        volume = float(latest["Volume"])
        volume_sma20 = float(latest["Volume_SMA20"])
    except (TypeError, ValueError):
        return False

    if pd.isna(rsi14) or pd.isna(volume_sma20):
        return False

    return (
        close > ema20
        and volume >= 1.5 * volume_sma20
        and 55 <= rsi14 <= 68
    )

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

        if not passes_raw_5m_prefilter(intraday):
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
MIN_AVG_DAILY_VOLUME = 500_000
AVG_VOLUME_DAYS = 20


def build_capital_safe_watchlist(symbols, batch_size=500):
    """
    Capital & Liquidity Pre-Filter.
    Only stocks satisfying:
      150 <= latest daily close <= 450
      20-day average daily volume >= 500,000
    reach the P1-P8 engine.
    """
    watchlist = []

    for start in range(0, len(symbols), batch_size):
        batch = symbols[start:start + batch_size]

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

                    if len(batch) == 1:
                        df = data.copy()
                    else:
                        if not hasattr(data, "columns"):
                            continue

                        levels = data.columns.get_level_values(0)

                        if ticker not in levels:
                            continue

                        df = data[ticker].copy()

                    df = df.dropna(subset=["Close", "Volume"])

                    if len(df) < AVG_VOLUME_DAYS:
                        continue

                    ltp = float(df["Close"].iloc[-1])

                    avg_volume = float(
                        df["Volume"]
                        .tail(AVG_VOLUME_DAYS)
                        .mean()
                    )

                    if (
                        MIN_CAPITAL_PRICE <= ltp <= MAX_CAPITAL_PRICE
                        and avg_volume >= MIN_AVG_DAILY_VOLUME
                    ):
                        watchlist.append(ticker)

                except Exception:
                    continue

            del data
            gc.collect()

        except Exception as exc:
            print(
                f"[CAPITAL PREFILTER ERROR] "
                f"{start}-{start + len(batch)}: {exc}"
            )

    print("=" * 70)
    print("CAPITAL-SAFE PRE-FILTER")
    print("=" * 70)
    print(f"Universe          : {len(symbols)}")
    print(f"Price Range       : ₹{MIN_CAPITAL_PRICE:.0f}-₹{MAX_CAPITAL_PRICE:.0f}")
    print(f"Min Avg Volume    : {MIN_AVG_DAILY_VOLUME:,}")
    print(f"P1-P8 Watchlist   : {len(watchlist)}")
    print("=" * 70)

    return watchlist


def scan_parallel(symbols, max_workers=MAX_WORKERS):
    # Capital-aligned pre-filter BEFORE P1-P8
    original_symbol_count = len(symbols)
    symbols = build_capital_safe_watchlist(symbols)

    print(
        f"Capital pre-filter: {original_symbol_count} -> "
        f"{len(symbols)} stocks before P1-P8"
    )
    global _failed_symbols, _data_quality_results

    start = time.perf_counter()

    with _failed_symbols_lock:
        _failed_symbols = []
    with _data_quality_lock:
        _data_quality_results = []

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

    return prepare_final_output(rank_results(results))


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
    universe = load_nse_universe()

    test_symbols = universe[:20]

    ranked = scan_parallel(test_symbols)

    if ranked.empty:
        print("No candidates found.")
    else:
        print()
        print(ranked[FINAL_OUTPUT_COLUMNS].to_string(index=False))








