from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from google import genai

from software_notifier import send_telegram_message


load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent

AUDIT_FILES = [
    "eight_parameter_engine.py",
    "nse_scanner.py",
    "AGENTS.md",
]

GEMINI_MODEL = "gemini-3.5-flash-lite"


def read_source_files() -> dict[str, str]:
    sources: dict[str, str] = {}

    for filename in AUDIT_FILES:
        path = PROJECT_ROOT / filename

        if path.exists():
            sources[filename] = path.read_text(
                encoding="utf-8",
                errors="replace",
            )
        else:
            sources[filename] = "FILE NOT FOUND"

    sources["fast_prefilter.py"] = (
        "FILE NOT FOUND — no such file exists in the current project."
    )
    sources["step_21g.py"] = (
        "FILE NOT FOUND — no such file exists in the current project."
    )

    return sources


def build_audit_prompt(sources: dict[str, str]) -> str:
    source_text = "\n\n".join(
        f"===== {name} =====\n{content}"
        for name, content in sources.items()
    )

    return f"""
You are a senior Python software architect and quantitative-system auditor.

Perform a READ-ONLY end-to-end software audit of the supplied Swing &
Intraday Stock Scanner Engine.

IMPORTANT:
Python deterministic calculations are the source of truth.
Do NOT invent missing code or market data.
Do NOT modify P1-P8 rules.
Do NOT recommend stocks.
Do NOT change rankings or calculations.

AUDIT OBJECTIVES:

1. Function-to-function mapping.
2. P1-P8 implementation integrity.
3. AGENTS.md versus executable Python discrepancies.
4. Specifically investigate P7:
   - AGENTS.md currently describes Previous Day High.
   - The executable engine may implement:
     First 15-minute High OR Previous Day High.
   - Determine the exact discrepancy from supplied source.
5. P8 mathematical correctness.
6. Possible look-ahead bias.
7. Missing-data / NaN / None handling.
8. Division-by-zero and invalid R:R protection.
9. Scanner pre-filter and ranking architecture.
10. Missing files such as fast_prefilter.py / step_21g.py.
11. Performance and memory bottlenecks.
12. Live-market validation gaps.
13. Telegram/Gemini integration risks visible from supplied source.
14. SEBI/product wording guardrails.

SEBI / PRODUCT WORDING:
- Never use Buy Signal.
- Never use Sell Signal.
- Never claim Guaranteed Profit.
- Never claim 100% Win Rate.
- Use Bullish Setup Detected.
- Use Educational Analysis.
- Do not provide personalized investment advice.

IMPORTANT:
- Report only findings supported by the supplied source.
- Clearly distinguish CRITICAL, HIGH, MEDIUM and LOW issues.
- Do not silently reconcile documentation with executable code.
- If documentation conflicts with executable code, explicitly report it.

RETURN A STRUCTURED AUDIT REPORT WITH:

1. EXECUTIVE_STATUS
2. FILE_INVENTORY
3. FUNCTION_MAPPING
4. P1_P8_AUDIT
5. DOCUMENTATION_VS_CODE_MISMATCHES
6. PERFORMANCE_AUDIT
7. DATA_VALIDATION_GAPS
8. SECURITY_CONFIGURATION_REVIEW
9. GEMINI_TELEGRAM_INTEGRATION_REVIEW
10. ORDERED_ACTION_PLAN

For every issue include:
- severity
- file
- evidence
- impact
- recommended_action

Do not output source code.
Do not expose secrets.

PROJECT SOURCE:
{source_text}
"""


def run_gemini_audit() -> dict[str, Any]:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()

    if not api_key:
        return {
            "status": "ERROR",
            "message": "GEMINI_API_KEY is missing.",
        }

    sources = read_source_files()
    prompt = build_audit_prompt(sources)

    client = genai.Client(api_key=api_key)

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
    )

    report = (response.text or "").strip()

    if not report:
        return {
            "status": "ERROR",
            "message": "Gemini returned an empty audit report.",
        }

    return {
        "status": "PASS",
        "report": report,
        "audited_files": list(sources.keys()),
    }


async def main() -> None:
    result = run_gemini_audit()

    if result["status"] != "PASS":
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    report = result["report"]

    telegram_message = (
        "🧠 SWING & INTRADAY SCANNER\n"
        "GEMINI SOFTWARE AUDIT\n\n"
        "Educational Analysis — Software Audit\n\n"
        f"{report}"
    )

    sent = await send_telegram_message(telegram_message)

    print(
        json.dumps(
            {
                "status": "PASS",
                "telegram_sent": sent,
                "audited_files": result["audited_files"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
