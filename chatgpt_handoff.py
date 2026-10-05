"""
ChatGPT Developer Handoff
Purpose:
- Convert Gemini Auditor result into a safe developer handoff.
- PASS -> no fix required.
- FAIL/ERROR -> structured issue report.
- Locked 8 parameters and SEBI guardrails must never be changed automatically.
"""

from datetime import datetime


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


SEBI_GUARDRAILS = [
    "Never use Buy Signal.",
    "Never use Sell Signal.",
    "Never claim Guaranteed Profit.",
    "Never claim 100% Win Rate.",
    "Use Bullish Setup Detected when technically applicable.",
    "Use Educational Analysis.",
    "Do not provide personalized investment advice.",
]


def build_chatgpt_handoff(audit_result: dict) -> dict:
    """
    Convert Gemini audit result into a safe developer handoff.
    """

    if not isinstance(audit_result, dict):
        return {
            "status": "ERROR",
            "action": "MANUAL_REVIEW_REQUIRED",
            "message": "Gemini audit result is not a dictionary.",
        }

    verdict = str(audit_result.get("verdict", "")).upper().strip()

    if verdict == "PASS":
        return {
            "status": "PASS",
            "action": "NO_FIX_REQUIRED",
            "message": "Gemini audit passed. No developer patch is required.",
            "locked_rules_changed": False,
            "sebi_guardrail_issue": False,
        }

    if verdict not in {"FAIL", "ERROR"}:
        return {
            "status": "ERROR",
            "action": "MANUAL_REVIEW_REQUIRED",
            "message": f"Unknown Gemini verdict: {verdict or 'EMPTY'}",
        }

    return {
        "status": verdict,
        "action": "DEVELOPER_REVIEW_REQUIRED",
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "test_name": audit_result.get("test_name"),
        "summary": audit_result.get("summary"),
        "issues": audit_result.get("issues", []),
        "developer_action": audit_result.get(
            "dev_action_for_chatgpt",
            "Review the reported issue before making any code change.",
        ),
        "locked_rules": LOCKED_RULES,
        "locked_rules_changed": audit_result.get(
            "locked_rules_changed",
            False,
        ),
        "sebi_guardrail_issue": audit_result.get(
            "sebi_guardrail_issue",
            False,
        ),
        "sebi_guardrails": SEBI_GUARDRAILS,
        "instruction": (
            "Do not automatically modify locked rules or SEBI guardrails. "
            "Create a backup before any approved code change and validate "
            "the change with deterministic Python tests."
        ),
    }


def print_handoff_report(handoff: dict) -> None:
    print("\n" + "=" * 70)
    print("CHATGPT DEVELOPER HANDOFF")
    print("=" * 70)

    for key, value in handoff.items():
        print(f"{key}: {value}")

    print("=" * 70)


if __name__ == "__main__":
    demo_pass = {
        "verdict": "PASS",
        "test_name": "Eight_Parameter_Engine_Full_Audit",
        "summary": "All locked rules passed.",
        "issues": [],
        "dev_action_for_chatgpt": "NONE",
        "locked_rules_changed": False,
        "sebi_guardrail_issue": False,
    }

    result = build_chatgpt_handoff(demo_pass)
    print_handoff_report(result)