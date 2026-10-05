# Task 5 — Top-3 Technical AI Audit

## Architecture

The Python scanner remains authoritative for candidate filtering, ranking, P1-P8, `Raw_Score`, and `Score`. The Streamlit dashboard passes only `scan_results.head(3)` to `run_top3_ai_audit`; the audit module preserves that supplied order and does not select, filter, rerank, or mutate scanner rows.

No external AI service is required. The current result is explicitly marked `AI audit unavailable`; the review is deterministic and uses only fields supplied by the scanner. It does not claim generative AI verification.

## Ten Checks

Every stock receives exactly these checks. Each check contains a `Status` (`PASS`, `CAUTION`, or `FAIL`) and a short factual `Reason`.

1. `Audit_1_Candle` — existing P4 reversal/candle-structure result.
2. `Audit_2_Support_Resistance` — CAUTION because scanner data does not classify support/resistance; any supplied previous-day high or swing low is identified only as an unclassified reference.
3. `Audit_3_Volume` — existing P5 result and supplied volume ratio when available.
4. `Audit_4_Trend` — existing P1 primary-trend result.
5. `Audit_5_Momentum_RSI` — existing P6 result and supplied RSI when available.
6. `Audit_6_Pullback` — existing P3 pullback result.
7. `Audit_7_Volatility` — supplied ATR is reported, but classification is CAUTION because no scanner-defined ATR threshold is available.
8. `Audit_8_Sector` — CAUTION with `Sector classification/data unavailable.`
9. `Audit_9_Event_Risk` — CAUTION stating event information could not be verified from the supplied scanner/market data.
10. `Audit_10_Overall_Consistency` — cross-checks the eight P1-P8 status fields against `Raw_Score`; unavailable inputs produce CAUTION.

Verified information is limited to supplied scanner fields and their existing deterministic results. Sector, event/news, unclassified support/resistance, and ATR interpretation remain explicitly unavailable or unverified; no such facts are invented.

## Output and Dashboard

Each audit record contains `Rank`, `Ticker`, `Raw_Score`, `Score`, the scanner `Status`, `Analysis_Type`, all ten check objects, `AI_Audit_Summary`, and `AI_Audit_Timestamp`. Python score/status fields are copied, not recalculated or changed.

The dashboard adds a separate `TOP 3 — TECHNICAL AI AUDIT` section with `Educational Analysis`, Python P1-P8 results, each check's status/reason, summary, and timestamp. The required disclaimer is displayed. The Task 3 scanner results table remains unchanged.

No audit data is written to CSV or another file. The audit exists only as an in-memory dashboard result.
