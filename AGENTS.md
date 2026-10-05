# Swing & Intraday Stock Scanner Engine

- Stack: Python, pandas, yfinance, Streamlit. Free tools only.
- Python calculations are the source of truth. AI only audits/monitors.
- Work ONE issue/change at a time.
- Backup before editing existing files.
- Prefer surgical edits; preserve existing APIs, field names and outputs.
- Use `py`, not `python`.
- After edits run syntax/tests. Never claim fixed without testing.
- Maintain issue priority: Critical / High / Medium / Low.
- Resolve the current issue before moving to the next.
- Never restore old P1-P8 logic.

## Locked P1-P8

P1: Daily Close > EMA20 > EMA50 > EMA200.
P2: 5m Close > EMA20.
P3: 5m Low <= EMA20*1.002 AND Close > EMA20.
P4: 5m Close > Open AND body > upper wick.
P5: 5m Volume >= 1.5*SMA20 Volume.
P6: 5m RSI14 between 55 and 68.
P7: Current implementation: Close >= Previous Day High.
P8: Target >= Close + 2*(Close-SL) AND target >= 2%; preserve tested ATR/swing-low implementation.

## Compliance

Use: Bullish Setup Detected; Educational Analysis.
Never use: Buy Signal; Sell Signal; Guaranteed Profit; 100% Win Rate.
Keep risk disclaimer/warning in user-facing output.
Never expose secrets, API keys or passwords.

## Editing

Do not rewrite whole files unnecessarily.
Do not modify unrelated files.
Preserve tested logic unless the requested change requires it.
