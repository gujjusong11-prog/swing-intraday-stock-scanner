import json
import os
from typing import Any

from google import genai


GEMINI_MODEL = "gemini-3.5-flash-lite"


LOCKED_RULES = {
    "P1": "Close > 200 EMA AND 50 EMA > 200 EMA",
    "P2": "Close > 20 EMA",
    "P3": "Low <= 20 EMA AND Close >= 20 EMA",
    "P4": "Close > Open AND Low <= 20 EMA AND Close >= 20 EMA",
    "P5": "Daily Volume > 20-Day Average Volume",
    "P6": "RSI between 50 and 65 inclusive",
    "P7": "Close > Previous Day High",
    "P8": "Risk-to-Reward Ratio >= 1:2",
}


def run_gemini_diagnostics(
    test_name: str,
    input_data: Any,
    calculation_result: Any,
    api_key: str | None = None,
) -> dict:
    """
    Gemini AI Tester / Auditor.

    Gemini only audits supplied deterministic Python results.
    It does NOT become the source of truth for calculations.
    """

    key = api_key or os.getenv("GEMINI_API_KEY")

    if not key:
        return {
            "status": "ERROR",
            "message": "GEMINI_API_KEY is missing.",
        }

    client = genai.Client(api_key=key)

    diagnostic_prompt = f"""
You are a Quantitative Software Quality Auditor.

Your job is ONLY to audit the supplied Python calculation result.
Python is the deterministic source of truth.

DO NOT change, reinterpret, weaken, strengthen, or replace any locked rule.

LOCKED 8-PARAMETER RULES:
{json.dumps(LOCKED_RULES, indent=2)}

SEBI / PRODUCT WORDING RULES:
- Never use Buy Signal.
- Never use Sell Signal.
- Never claim Guaranteed Profit.
- Never claim 100% Win Rate.
- Use Bullish Setup Detected when technically applicable.
- Use Educational Analysis.
- Do not provide personalized investment advice.

TEST UNIT:
{test_name}

INPUT TECHNICAL DATA:
{json.dumps(input_data, default=str, indent=2)}

CALCULATED RESULT:
{json.dumps(calculation_result, default=str, indent=2)}

AUDIT THESE ITEMS:
1. Mathematical correctness.
2. Indicator calculation consistency.
3. Missing / None / NaN handling.
4. Division-by-zero protection.
5. Invalid Risk-to-Reward handling.
6. Possible look-ahead bias.
7. Incorrect previous-day reference.
8. Volume ratio consistency.
9. Locked 8-parameter rule integrity.
10. SEBI wording / guardrail integrity.

IMPORTANT:
- Do not invent missing market data.
- Do not change the locked rules.
- Do not recommend a stock.
- If the supplied result is technically valid, return PASS.
- If a material technical problem exists, return FAIL.
- If the test cannot be verified because required data is missing, return ERROR.

RETURN ONLY VALID JSON:

{{
  "verdict": "PASS",
  "test_name": "{test_name}",
  "summary": "Short technical summary.",
  "issues": [],
  "dev_action_for_chatgpt": "NONE",
  "locked_rules_changed": false,
  "sebi_guardrail_issue": false
}}

For FAIL, provide precise developer instructions inside
dev_action_for_chatgpt.

For PASS:
"dev_action_for_chatgpt": "NONE"
"""

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=diagnostic_prompt,
        )

        raw_text = (response.text or "").strip()

        try:
            report = json.loads(raw_text)
        except json.JSONDecodeError:
            return {
                "status": "ERROR",
                "message": "Gemini returned non-JSON output.",
                "raw_response": raw_text,
            }

        verdict = str(report.get("verdict", "")).upper()

        if verdict not in {"PASS", "FAIL", "ERROR"}:
            return {
                "status": "ERROR",
                "message": "Invalid Gemini verdict.",
                "report": report,
            }

        return {
            "status": verdict,
            "report": report,
        }

    except Exception as exc:
        return {
            "status": "ERROR",
            "message": str(exc),
        }