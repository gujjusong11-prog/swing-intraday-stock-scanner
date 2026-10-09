import pandas as pd
from eight_parameter_engine import calculate_eight_parameter_setup


NSE_EQUITY_URL = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"


def load_nse_universe():
    """
    Load current NSE equity universe.
    Only normal EQ series securities are included.
    """

    import io
    import requests

    response = requests.get(
        NSE_EQUITY_URL,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "text/csv,application/octet-stream,*/*",
            "Referer": "https://www.nseindia.com/",
        },
        timeout=30,
    )
    response.raise_for_status()

    df = pd.read_csv(io.BytesIO(response.content))

    df.columns = [
        str(col).strip().upper()
        for col in df.columns
    ]

    required = {"SYMBOL", "SERIES"}

    if not required.issubset(df.columns):
        raise ValueError(
            f"Unexpected NSE CSV columns: {list(df.columns)}"
        )

    df = df[
        df["SERIES"].astype(str).str.upper().eq("EQ")
    ].copy()

    df["SYMBOL"] = (
        df["SYMBOL"]
        .astype(str)
        .str.strip()
    )

    df = df[
        df["SYMBOL"].ne("") &
        df["SYMBOL"].ne("NAN")
    ]

    df = df.drop_duplicates(
        subset=["SYMBOL"]
    )

    return df.sort_values("SYMBOL")["SYMBOL"].dropna().astype(str).str.strip().tolist()


def is_candidate_pre_filter(result):
    """
    Candidate pre-filter using validated P1-P8 engine output.
    """

    if not result:
        return False

    try:
        close_5m = float(result.get("LTP"))
        ema20_5m = float(result.get("5M_EMA20"))
        volume_ratio = float(result.get("Volume_Ratio"))
        rsi14 = float(result.get("RSI_14"))
    except (TypeError, ValueError):
        return False

    return (
        close_5m > ema20_5m
        and volume_ratio >= 1.5
        and 55 <= rsi14 <= 68
    )


def scan_nse_universe(universe):
    """
    Run the validated 8-parameter engine
    across the dynamic NSE EQ universe.
    """

    results = []
    failed = 0

    total = len(universe)

    print(f"NSE EQ universe: {total} stocks")
    print("Starting 8-parameter technical scan...")
    print()

    for number, symbol in enumerate(
        universe,
        start=1,
    ):
        try:
            result = calculate_eight_parameter_setup(
                symbol,
                "Intraday",
            )

            if result is not None and is_candidate_pre_filter(result):
                results.append(result)

        except Exception as exc:
            failed += 1

            print(
                f"[SKIP] {symbol}: {exc}"
            )

        if number % 25 == 0 or number == total:
            print(
                f"Progress: {number}/{total} | "
                f"Valid: {len(results)} | "
                f"Failed: {failed}"
            )

    return results, failed


def rank_results(results):
    """
    Rank by deterministic 8-parameter score.

    Primary:
        Raw_Score

    Secondary:
        Volume_Ratio
    """

    if not results:
        return pd.DataFrame()

    df = pd.DataFrame(results)

    df = df.sort_values(
        by=[
            "Raw_Score",
            "Volume_Ratio",
        ],
        ascending=[
            False,
            False,
        ],
        na_position="last",
    ).reset_index(drop=True)

    df.insert(
        0,
        "Rank",
        range(1, len(df) + 1),
    )

    return df
def main():

    print("=" * 70)
    print("NSE 8-PARAMETER DYNAMIC SCANNER")
    print("=" * 70)

    universe = load_nse_universe()

    print(
        f"Loaded NSE EQ stocks: {len(universe)}"
    )

    results, failed = scan_nse_universe(
        universe
    )

    print()
    print("=" * 70)
    print("CANDIDATE PRE-FILTER SUMMARY")
    print("=" * 70)
    print(f"NSE Universe     : {len(universe)}")
    print(f"Candidate Stocks : {len(results)}")
    print(f"Failed Data      : {failed}")
    print()

    ranked = rank_results(results)

    if ranked.empty:
        print()
        print("No valid market-data results returned.")
        return

    print()
    print("=" * 70)
    print("SCAN COMPLETED")
    print("=" * 70)

    print(
        f"Stocks with valid data : {len(ranked)}"
    )

    print(
        f"Stocks skipped/errors   : {failed}"
    )

    print()
    print("TOP 20 BY 8-PARAMETER SCORE")
    print("-" * 70)

    display_columns = [
        "Rank",
        "Ticker",
        "LTP",
        "EMA_20",
        "EMA_50",
        "EMA_200",
        "RSI_14",
        "Volume_Ratio",
        "ATR_14",
        "P1_Primary_Trend",
        "P2_Short_Momentum",
        "P3_Pullback_Zone",
        "P4_Reversal_Confirmation",
        "P5_Volume_Surge",
        "P6_Momentum_Range",
        "P7_Previous_High_Trigger",
        "P8_Risk_Reward",
        "Risk_Reward",
        "Score",
        "Status",
    ]

    available_columns = [
        column
        for column in display_columns
        if column in ranked.columns
    ]

    print(
        ranked[
            available_columns
        ].head(20).to_string(index=False)
    )



if __name__ == "__main__":
    main()







