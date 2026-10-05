# Task 6 — Event Risk Layer

## Architecture

`event_risk.py` is a separate read-only layer for the first three rows supplied by the Python-ranked scanner. It does not filter or reorder candidates and copies `Rank`, `Ticker`, `Raw_Score`, `Score`, and scanner `Status` without changing them. `Analysis_Type` is set to `Educational Analysis`.

The dashboard invokes this layer only on the existing Top-3 rows, displays the result inside each current Top-3 expander, and caches the free-data result for 15 minutes. No scanner, engine, ranking, filtering, Task 2 retry, or Task 3 formatting code is changed.

## Data Sources

The layer uses free yfinance fields only:

- `Ticker.calendar` for earnings and ex-dividend dates, and split/bonus schedule keys when returned.
- `Ticker.actions` for dividend and split action records. Historical rows are not presented as upcoming events.
- `Ticker.news` for whether Yahoo Finance returned news items. Headlines are not treated as verified scheduled events or assigned impact levels.

Each source is fetched independently. Exceptions and `None` results become CAUTION with `Event data unavailable.` The module does not call a paid news service or require a key.

## Event Logic

The near-term window is 14 calendar days, inclusive.

- A verified scheduled event within 14 days returns CAUTION and names the verified event/date; it may materially affect volatility.
- A verified next event beyond 14 days returns PASS for that event check.
- An accessible source that supplies no upcoming schedule returns CAUTION with `Event information could not be verified from available free data.` Historical actions are not assumed to prove that no future action exists.
- An accessible news feed with zero returned items returns PASS for the news check, stating that no news-based event risk was verified in that fetch. Non-empty news returns CAUTION because headlines are not classified as verified scheduled events.
- Overall status is CAUTION if a verified event is within 14 days or any check is incomplete/unavailable. It is PASS only when every check is complete and no verified near-term event is found.
- FAIL is not inferred from missing information. Current free yfinance fields do not expose a verified event-impact/severity classification, so the layer does not emit FAIL absent such evidence.

Each stock record includes the requested rank/ticker/score/status fields, `Event_Earnings`, `Event_Dividend`, `Event_Split_Bonus`, `Event_News`, `Event_Risk_Status`, `Event_Risk_Reason`, and `Event_Risk_Timestamp`. Each source check contains a status and factual reason.

## Dashboard

Within the existing Top-3 audit section, each stock displays the overall Event Risk status/reason plus earnings, dividend, split/bonus, and news availability. The display is read-only and keeps data in memory; no CSV persistence was added.
