# Task 7 — Data Quality Test Report

## Files Changed

- `data_quality.py` — new deterministic market-data and engine-output validator.
- `parallel_nse_scanner.py` — added a thread-safe in-memory per-symbol quality sidecar; existing scanner decisions and output formatter are unchanged.
- `app.py` — added the read-only Data Quality section and session-state handoff.
- `TASK7_DATA_QUALITY.md` — validation design and rules.
- `TASK7_DATA_QUALITY_TEST_REPORT.md` — this report.

`eight_parameter_engine.py`, `nse_scanner.py`, `event_risk.py`, and `top3_ai_audit.py` were not edited.

## Backups Created

- `parallel_nse_scanner_backup_before_task7_data_quality_20261004.py`
- `app.py.backup_before_task7_data_quality_20261004.py`
- `data_quality_backup_before_task7_intraday_minimum_20261004.py` — backup created before adding the engine's latest-date 3-bar requirement.

## Validation Rules

- Daily: required OHLCV fields, DatetimeIndex integrity, OHLCV sanity, at least 220 complete rows.
- Intraday: required OHLCV fields, DatetimeIndex integrity, duplicate detection, OHLCV sanity, positive prices, at least 100 complete bars and 3 complete bars on the latest date.
- Missing/non-numeric OHLCV rows: above 5% is FAIL; 0% to 5% (exclusive of zero) is CAUTION.
- Indicators: readiness is checked from existing observation counts and engine-produced values only; indicators are not recalculated.
- P1-P8: exact PASS/FAIL values, all fields present, integer Raw_Score in 0-8 equal to PASS count, and Score matching `<Raw_Score>/8`.
- Risk: checks numeric risk outputs and internal Target/LTP/Stop_Loss/target-gain/Risk_Reward consistency with rounding tolerance; it does not alter P8.
- Overall: FAIL > CAUTION > PASS; no missing or uncomputed value is silently passed.

## Test Results

- **A. Syntax:** `py -m py_compile data_quality.py parallel_nse_scanner.py app.py` passed. VS Code reported no errors in the three files.
- **B-H. Synthetic validation:** Passed for structurally valid frames; empty data; missing OHLCV column; excessive NaN rows; duplicate timestamps; invalid OHLC and zero price; insufficient latest-date bars; missing P1-P8 field; Raw_Score mismatch; and target-gain/risk-ratio mismatch. A valid fixture passed all five quality groups. When engine output was absent, indicators, P1-P8, and risk were CAUTION.
- **Per-symbol sidecar:** A synthetic scan recorded both a prefilter-rejected symbol and a candidate, while the ranked output retained only the candidate. A simulated data-fetch failure produced an explicit FAIL quality record and no candidate.
- **I. Streamlit AppTest:** Passed with both a non-empty candidate result and an empty candidate result; Data Quality rendered in both states. Event Risk was stubbed for this UI test to avoid live network calls.
- **J. Live scan:** Scanned `RELIANCE`, `TCS`, and `INFY`; the existing scanner produced one candidate (`TCS`) and the quality sidecar returned exactly three records. Daily and 5-minute source checks were PASS for all three; overall statuses were CAUTION for two rows and PASS for TCS. No Data Quality fields appeared in the ranked DataFrame.
- **K. HTTP 429 regression:** Existing `_throttled_history` was tested with two simulated 429 responses followed by success; it retried twice and succeeded. Rate-limit code was not changed.
- **L. Task 3 schema regression:** The exact 21 `FINAL_OUTPUT_COLUMNS` and `Target_Gain_Percent` alias were asserted unchanged; no Data Quality columns were added.
- **M. Task 6 regression:** A synthetic near-term earnings event still returned Event Risk CAUTION with the original ticker, Raw_Score, Score, and Status intact. `event_risk.py` was not changed.
- **N. Persistence:** Search of `data_quality.py`, `parallel_nse_scanner.py`, and `app.py` found no CSV read/write or file-open calls. No database or external store was added.
- **P1-P8/score integrity:** Synthetic input frames and engine values remained unchanged; rank and candidate output were unaffected by the quality sidecar.
- **P8 integrity:** Valid Target/LTP/Stop_Loss and ratio outputs passed; an inconsistent target gain was reported FAIL. No P8 formula was modified.

## Decision

**PASS — Task 7 implementation and scoped tests passed.** Quality results are advisory diagnostics only. No Task 8 or Task 9 work was started.
