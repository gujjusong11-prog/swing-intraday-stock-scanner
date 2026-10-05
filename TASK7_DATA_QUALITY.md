# Task 7 — Data Quality & Data Integrity

## Architecture

`data_quality.py` validates market frames and existing engine outputs. The parallel scanner records one in-memory quality result per scanned symbol, including fetch failures and rows rejected by the existing prefilter. Validation runs before the 5-minute prefilter; its status never gates or changes the prefilter, engine, candidate list, rank, score, P1-P8, P8 calculation, or Event Risk result.

The scanner's ranked DataFrame and Task 3 formatter are unchanged. The dashboard displays the sidecar results in a separate read-only Data Quality section, including when a scan has no candidates. Results are reset for each scan and held only in memory/session state.

## Validation Rules

- **Daily history:** Requires a non-empty DataFrame with `Open`, `High`, `Low`, `Close`, and `Volume`; at least 220 complete rows, matching the existing engine's minimum for its EMA200 path. More than 5% incomplete/non-numeric rows is FAIL; a non-zero missing fraction up to 5% is CAUTION.
- **Intraday history:** Requires the same OHLCV columns, at least 100 complete bars, and at least 3 complete bars on the latest date, matching existing engine guards. Duplicate timestamps, invalid/non-chronological indexes, excessive missing data, or too few bars are FAIL.
- **Index integrity:** Both frame indexes must be `DatetimeIndex` values without NaT, duplicates, or non-chronological order.
- **OHLCV integrity:** `High >= max(Open, Close)`, `Low <= min(Open, Close)`, `High >= Low`, OHLC prices must be positive, and Volume must be non-negative. Violations are FAIL.
- **Indicator readiness:** Does not calculate indicators. It checks the observation minimums and, when engine output exists, checks that `Daily_EMA20`, `Daily_EMA50`, `Daily_EMA200`, `5M_EMA20`, `RSI_14`, `ATR_14`, and `Volume_SMA20` are numeric. Missing engine outputs are CAUTION; insufficient observations are FAIL.
- **P1-P8 integrity:** Requires all eight fields, each exactly `PASS` or `FAIL`; `Raw_Score` must be an integer from 0 to 8 and equal the P1-P8 PASS count; `Score` must match as `<Raw_Score>/8`.
- **Risk integrity:** When risk calculation outputs are available, checks numeric `LTP`, `Stop_Loss`, `Target`, target gain, `Reward_Risk_Ratio`, and formatted `Risk_Reward`; verifies a positive risk/reward structure and consistency of target gain with Target/LTP and the ratio with Target/LTP/Stop_Loss. Comparisons allow for two-decimal output rounding. A P8 PASS with missing risk outputs is FAIL; unavailable P8 outputs on a P8 FAIL are CAUTION.
- **Overall status:** FAIL takes precedence over CAUTION, which takes precedence over PASS. Uncomputed engine outputs are never reported as PASS.

All checks inspect copies/conversions for validation only; no source frame or engine value is changed.

## Dashboard

The Data Quality table reports ticker, overall status, daily, 5-minute, indicator, P1-P8, and risk statuses, the combined reason, timestamp, and `Analysis_Type = Educational Analysis`. It does not add columns to the scanner's Task 3 output and does not persist data.
