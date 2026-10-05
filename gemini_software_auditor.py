from pathlib import Path
import os
from typing import Any

from dotenv import load_dotenv
from google import genai

from software_notifier import send_telegram_message

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent

AUDIT_FILES = [
    "AGENTS.md",
    "eight_parameter_engine.py",
    "nse_scanner.py",
    "parallel_nse_scanner.py",
    "app.py",
    "top3_ai_audit.py",
    "event_risk.py",
    "data_quality.py",
    "software_notifier.py",
    "gemini_test_auditor.py",
    "gemini_software_auditor.py",
]

GEMINI_MODEL = "gemini-3.5-flash-lite"


def read_source_files() -> dict[str, str]:
    sources: dict[str, str] = {}

    for filename in AUDIT_FILES:
        path = PROJECT_ROOT / filename

        if path.is_file():
            try:
                sources[filename] = path.read_text(encoding="utf-8")
            except Exception as exc:
                sources[filename] = (
                    f"FILE READ ERROR: {type(exc).__name__}: {exc}"
                )
        else:
            sources[filename] = "FILE NOT FOUND"

    return sources


def build_audit_prompt(sources: dict[str, str]) -> str:
    codebase_context = "\n\n".join(
        f"===== FILE: {filename} =====\n{content}"
        for filename, content in sources.items()
    )

    return f"""
You are an independent senior Python software architect and quantitative
scanner auditor.

Perform a READ-ONLY, end-to-end audit of the supplied Swing & Intraday Stock
Scanner Engine.

IMPORTANT SOURCE-OF-TRUTH RULE:
- Python deterministic engine and automated tests are the technical source of truth.
- Gemini must NEVER invent a rule.
- Gemini must NEVER silently change P1-P8.
- Gemini must NEVER recommend treating an AI opinion as a trading signal.
- Do not claim guaranteed performance.

AUDIT THE COMPLETE PROJECT:

1. FILE INVENTORY
   - Verify every supplied file.
   - Identify missing, duplicate, stale, dead, or inconsistent modules.

2. FUNCTION / MODULE MAPPING
   - Identify every function/class that materially affects scanning,
     ranking, dashboard output, AI audit, event risk, data quality,
     Telegram notification, or Gemini integration.
   - Explain its role briefly.

3. P1-P8 LOGIC
   Compare AGENTS.md against the ACTUAL executable implementation.
   Explicitly audit:
   P1 Primary Trend
   P2 Short Momentum
   P3 Pullback Zone
   P4 Reversal Confirmation
   P5 Volume Surge
   P6 RSI Filter
   P7 High Trigger
   P8 Risk-to-Reward

   PAY SPECIAL ATTENTION TO P7:
   determine whether documentation and executable code use the same rule.
   If different, clearly report both versions and state that executable
   Python is the current source of truth.

4. P8
   Verify stop-loss, target, risk, reward, R:R and target-percentage
   calculations, including zero/negative/NaN/insufficient-data edge cases.

5. DATA FLOW
   Audit the complete chain:
   market data -> indicators -> P1-P8 -> score -> prefilter ->
   parallel scanning -> ranking -> data quality -> Top-3 audit ->
   event risk -> Streamlit dashboard.

6. RUNTIME ROBUSTNESS
   Check:
   - empty DataFrame
   - insufficient rows
   - NaN
   - duplicate timestamps
   - invalid OHLCV
   - failed yfinance requests
   - HTTP 429
   - worker exceptions
   - unexpected calculation errors.

7. PERFORMANCE
   Review:
   - sequential vs parallel scanning
   - unnecessary repeated calculations
   - network request volume
   - concurrency/rate-limit risks
   - memory retention
   - avoidable bottlenecks.

8. DASHBOARD
   Verify app.py consumes scanner output correctly without creating a
   second independent P1-P8 calculation.

9. AI AUDIT
   Verify Top-3 technical audit does not alter deterministic ranking,
   score, or P1-P8 results.

10. EVENT RISK
    Verify missing/unverified event information is handled conservatively
    and is not invented.

11. DATA QUALITY
    Verify FAIL-quality candidates cannot silently enter final candidates.

12. TELEGRAM / GEMINI
    Audit ONLY the existing SOFTWARE monitoring Bot-1 architecture.
    Do NOT create, reference, configure, or recommend Bot-2 at this stage.

13. SECURITY
    Check API-key handling, secrets, hard-coded credentials, logging
    exposure, and unsafe external inputs.
    Never reproduce secret values.

14. COMPLIANCE LANGUAGE
    Verify that software/user-facing wording avoids:
    Buy Signal, Sell Signal, Guaranteed Profit, 100% Win Rate.
    Prefer:
    Bullish Setup Detected
    Educational Analysis

15. LIVE-WORKING LIMITATION
    Clearly distinguish:
    - static source audit
    - automated tests
    - live runtime observations
    Do not claim a live behavior was verified unless the supplied evidence
    actually supports it.

OUTPUT LANGUAGE:
Gujarati.
Keep technical identifiers such as filenames, function names, P1-P8,
HTTP 429, yfinance, Gemini, Telegram in English.

OUTPUT FORMAT:

🛡️ GEMINI SOFTWARE AUDIT — BOT-1

1. EXECUTIVE STATUS
2. FILE INVENTORY
3. FUNCTION / MODULE MAP
4. P1-P8 VERIFICATION
5. P7 DOCUMENTATION vs ENGINE
6. P8 RISK-REWARD REVIEW
7. END-TO-END DATA FLOW
8. RUNTIME / ERROR RISKS
9. PERFORMANCE REVIEW
10. DASHBOARD / INTEGRATION REVIEW
11. AI / EVENT / DATA-QUALITY REVIEW
12. SECURITY REVIEW
13. PRIORITY FINDINGS
   CRITICAL
   HIGH
   MEDIUM
   LOW
14. ORDERED ACTION PLAN
15. FINAL AUDIT STATUS

Do not output source code.
Do not expose API keys, tokens, chat IDs, or secrets.
Do not claim fixes were implemented unless the source proves they exist.

PROJECT SOURCE:
{codebase_context}
"""


def run_gemini_audit() -> dict[str, Any]:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()

    if not api_key:
        return {
            "status": "FAIL",
            "message": "GEMINI_API_KEY is missing.",
            "report": "",
        }

    sources = read_source_files()
    prompt = build_audit_prompt(sources)

    try:
        client = genai.Client(api_key=api_key)

        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
        )

        report = (response.text or "").strip()

        if not report:
            return {
                "status": "FAIL",
                "message": "Gemini returned an empty audit report.",
                "report": "",
            }

        return {
            "status": "PASS",
            "message": "Full-project Gemini audit completed.",
            "report": report,
            "files_audited": list(sources.keys()),
        }

    except Exception as exc:
        return {
            "status": "FAIL",
            "message": f"{type(exc).__name__}: {exc}",
            "report": "",
        }


def main() -> int:
    result = run_gemini_audit()

    if result["status"] != "PASS":
        print("GEMINI AUDIT STATUS: FAIL")
        print(result["message"])
        return 1

    message = (
        "🛡️ GEMINI SOFTWARE AUDIT — BOT-1\n"
        "Educational Analysis — Software Health Audit\n\n"
        + result["report"]
    )

    async def _dispatch_chunks():
        chunk_size = 4000
        chunks = [message[i:i + chunk_size] for i in range(0, len(message), chunk_size)]
        results = []
        for chunk in chunks:
            results.append(await send_telegram_message(chunk))
        return bool(chunks) and all(results)

    sent = __import__("asyncio").run(_dispatch_chunks())

    print("GEMINI AUDIT STATUS: PASS")
    print("FILES AUDITED:", len(result.get("files_audited", [])))
    print("BOT-1 DISPATCH:", "PASS" if sent else "FAIL")

    return 0 if sent else 1


if __name__ == "__main__":
    raise SystemExit(main())

