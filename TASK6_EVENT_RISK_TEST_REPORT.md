# Task 6 — Event Risk Test Report

## Files Changed

- `event_risk.py` — new yfinance-backed event-risk layer.
- `app.py` — added cached Event Risk output within the existing Top-3 stock expander.
- `TASK6_EVENT_RISK.md` — implementation and status logic.
- `TASK6_EVENT_RISK_TEST_REPORT.md` — this report.

`top3_ai_audit.py`, `eight_parameter_engine.py`, `parallel_nse_scanner.py`, and `nse_scanner.py` were not edited.

## Backups Created

- `app.py.backup_before_task6_event_risk_20261004.py` — created before editing the existing dashboard.
- `event_risk_backup_before_task6_status_refinement_20261004.py` — created before refining the new event module's empty-news classification.

## Exact Event Risk Logic

- Near-term means 14 calendar days, inclusive.
- Verified events inside the window produce CAUTION; verified next dates outside the window produce PASS for that source check.
- Missing/failed source fetches produce CAUTION with `Event data unavailable.` Missing upcoming schedule data produces CAUTION with `Event information could not be verified from available free data.`
- Empty but accessible news returns PASS for the news check; non-empty headlines are not treated as verified scheduled events and produce CAUTION.
- Overall status is CAUTION for any near-term verified event or incomplete check, and PASS only if all checks are complete with no verified near-term event. No FAIL is inferred from missing data; Yahoo's returned fields did not provide a verified impact/severity signal.

## Test Results

- **Synthetic Top-3:** Passed with four ranked rows. Exactly ranks 1–3 were queried and returned, in Python order; rank 4 was not queried.
- **Synthetic status cases:** A verified earnings date three days away returned CAUTION. Unavailable calendar/actions/news returned CAUTION and `Event data unavailable.` A complete fixture with all scheduled dates outside 14 days and an accessible empty news feed returned PASS. All event statuses were within PASS/CAUTION/FAIL.
- **Output/score integrity:** Required event fields were present. `Rank`, `Raw_Score`, `Score`, `Status`, and `Analysis_Type` matched the source contract. Full P1-P8 source values and the input DataFrame were unchanged.
- **Live scan:** Scanned `RELIANCE`, `TCS`, and `INFY`; one candidate qualified (`TCS`). Event Risk received exactly `TCS`, matching the Python-ranked Top-3 slice.
- **Live free-data result:** yfinance calendar returned an earnings date of 2026-10-08, four days after the 2026-10-04 test date. The overall result was CAUTION for that verified near-term event. The calendar's ex-dividend date was historical; yfinance action rows were historical and did not verify a future dividend/split schedule. The news endpoint returned no items in the event fetch.
- **Dashboard:** Streamlit `AppTest` rendered the Event Risk section using an injected provider without application errors.
- **Syntax/diagnostics:** `py -m py_compile app.py event_risk.py` passed; VS Code reported no errors in either file.
- **Task 3 schema:** The exact 21-column `FINAL_OUTPUT_COLUMNS` order and `Target_Gain_Percent` alias were asserted unchanged.
- **HTTP 429:** The existing retry function was tested with two simulated 429 responses followed by success; both retries occurred and the subsequent request succeeded. No scanner retry code was edited.
- **Persistence:** Search of `app.py` and `event_risk.py` found no CSV read/write or file-open calls. No raw CSV persistence was introduced.

## Data Limitations

The live source returned an earnings date, historical corporate-action data, and an empty news list. It did not verify a forward dividend or split/bonus schedule. `Ticker.actions` is historical data and is not represented as a future schedule. Empty news means no item was returned in that fetch, not proof that no event exists. The current free yfinance fields do not expose an independently verified high-impact classification.

## Decision

**PASS — Task 6 implementation and scoped tests passed.** Live status for TCS is CAUTION because a verified earnings date falls within the 14-day window; unavailable forward corporate-action details remain explicit CAUTIONs. No Task 7 or Task 8 work was started.
