import pandas as pd
import yfinance as yf
from intraday_engine import calculate_intraday_engine


NSE_EQUITY_URL = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"


def load_nse_universe():
    """
    Load current NSE equity universe.
    Only normal EQ series securities are included.
    """

    import io, requests
    response = requests.get(NSE_EQUITY_URL, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
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

    return df.sort_values("SYMBOL").reset_index(drop=True)


def scan_nse_universe(universe):
    """
    Run existing 4-condition intraday engine
    across the dynamic NSE universe.
    """

    results = []
    failed = 0

    total = len(universe)

    print(f"NSE EQ universe: {total} stocks")
    print("Starting intraday technical scan...")
    print()

    for number, symbol in enumerate(
        universe["SYMBOL"],
        start=1
    ):

        try:
            result = calculate_intraday_engine(
                symbol
            )

            if result is not None:
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
    Rank by technical score.
    Higher score first.

    Secondary ranking:
    1. Raw Score
    2. Volume Ratio
    """

    if not results:
        return pd.DataFrame()

    df = pd.DataFrame(results)

    df = df.sort_values(
        by=[
            "Raw_Score",
            "Volume_Ratio"
        ],
        ascending=[
            False,
            False
        ]
    ).reset_index(drop=True)

    df.insert(
        0,
        "Rank",
        range(1, len(df) + 1)
    )

    return df


def main():

    print("=" * 60)
    print("NSE INTRADAY DYNAMIC SCANNER - STEP 1B")
    print("=" * 60)

    universe = load_nse_universe()

    print(
        f"Loaded NSE EQ stocks: {len(universe)}"
    )

    results, failed = scan_nse_universe(
        universe
    )

    ranked = rank_results(results)

    if ranked.empty:
        print()
        print("No valid market-data results returned.")
        return

    ranked.to_csv(
        "intraday_ranked.csv",
        index=False
    )

    print()
    print("=" * 60)
    print("SCAN COMPLETED")
    print("=" * 60)

    print(
        f"Stocks with valid data : {len(ranked)}"
    )

    print(
        f"Stocks skipped/errors   : {failed}"
    )

    print()
    print("TOP 20 BY TECHNICAL SCORE")
    print("-" * 60)

    display_columns = [
        "Rank",
        "Ticker",
        "LTP",
        "VWAP",
        "EMA_9",
        "EMA_21",
        "Volume_Ratio",
        "CPR_Top",
        "Score"
    ]

    print(
        ranked[
            display_columns
        ].head(20).to_string(index=False)
    )

    print()
    print(
        "Saved: intraday_ranked.csv"
    )


if __name__ == "__main__":
    main()

