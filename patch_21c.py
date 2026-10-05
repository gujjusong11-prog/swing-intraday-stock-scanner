from pathlib import Path

p = Path("eight_parameter_engine.py")
s = p.read_text(encoding="utf-8")

old_header = '''def calculate_eight_parameter_setup(
    ticker: str,
    mode: str = "Intraday"
):'''

new_header = '''def calculate_eight_parameter_setup(
    ticker: str,
    mode: str = "Intraday",
    daily_data=None,
    intraday_data=None
):'''

old_daily = '''        daily = stock.history(
            period="1y",
            interval="1d",
            auto_adjust=False
        )'''

new_daily = '''        daily = daily_data if daily_data is not None else stock.history(
            period="1y",
            interval="1d",
            auto_adjust=False
        )'''

old_intraday = '''        intraday = stock.history(
            period="5d",
            interval="5m",
            auto_adjust=False
        )'''

new_intraday = '''        intraday = intraday_data if intraday_data is not None else stock.history(
            period="5d",
            interval="5m",
            auto_adjust=False
        )'''

checks = [
    (old_header, new_header, "function header"),
    (old_daily, new_daily, "daily fetch"),
    (old_intraday, new_intraday, "intraday fetch"),
]

for old, new, name in checks:
    if old not in s:
        raise SystemExit(f"PATCH ABORTED: exact {name} block not found")
    s = s.replace(old, new, 1)

p.write_text(s, encoding="utf-8")
print("STEP 21C DATA REUSE PATCH APPLIED")
