from pprint import pprint

from eight_parameter_engine import calculate_eight_parameter_setup
from gemini_test_auditor import run_gemini_diagnostics


TEST_TICKER = "RELIANCE"


def build_audit_input(result: dict) -> dict:
    """Prepare only the deterministic fields needed by the Gemini auditor."""

    fields = [
        "Ticker",
        "Mode",
        "LTP",
        "EMA_20",
        "EMA_50",
        "EMA_200",
        "RSI_14",
        "Volume",
        "Volume_Avg_20D",
        "Volume_Ratio",
        "Previous_Day_High",
        "ATR_14",
        "Swing_High_20",
        "Recent_Low_5",
        "Stop_Loss",
        "Risk_Per_Share",
        "Reward_Per_Share",
        "Reward_Risk_Ratio",
        "Risk_Reward",
        "P1_Primary_Trend",
        "P2_Short_Momentum",
        "P3_Pullback_Zone",
        "P4_Reversal_Confirmation",
        "P5_Volume_Surge",
        "P6_Momentum_Range",
        "P7_Previous_High_Trigger",
        "P8_Risk_Reward",
        "Score",
        "Raw_Score",
        "Status",
    ]

    return {
        field: result.get(field)
        for field in fields
    }


def main() -> None:
    print("=" * 70)
    print("8-PARAMETER GEMINI AUTOMATED AUDIT")
    print("=" * 70)

    print(f"Ticker: {TEST_TICKER}")
    print("Running Python deterministic calculation...")

    result = calculate_eight_parameter_setup(
        TEST_TICKER,
        "Intraday",
    )

    if result is None:
        print("STATUS: ERROR")
        print("Message: 8-parameter engine returned None.")
        return

    audit_input = build_audit_input(result)

    print("\nPython Calculation Summary:")
    print(f"Score: {result.get('Score')}")
    print(f"Raw Score: {result.get('Raw_Score')}")
    print(f"Status: {result.get('Status')}")
    print(f"Volume Ratio: {result.get('Volume_Ratio')}")
    print(f"Risk/Reward: {result.get('Risk_Reward')}")

    print("\nRunning Gemini Auditor...")

    audit = run_gemini_diagnostics(
        test_name="Eight_Parameter_Engine_Full_Audit",
        input_data=audit_input,
        calculation_result={
            "P1": result.get("P1_Primary_Trend"),
            "P2": result.get("P2_Short_Momentum"),
            "P3": result.get("P3_Pullback_Zone"),
            "P4": result.get("P4_Reversal_Confirmation"),
            "P5": result.get("P5_Volume_Surge"),
            "P6": result.get("P6_Momentum_Range"),
            "P7": result.get("P7_Previous_High_Trigger"),
            "P8": result.get("P8_Risk_Reward"),
            "Score": result.get("Score"),
            "Raw_Score": result.get("Raw_Score"),
            "Volume_Ratio": result.get("Volume_Ratio"),
            "Risk_Reward": result.get("Risk_Reward"),
            "Status": result.get("Status"),
        },
    )

    print("\nGemini Audit Result:")
    print(f"STATUS: {audit.get('status')}")

    if "report" in audit:
        pprint(audit["report"])
    else:
        print(audit.get("message", "No audit report returned."))


if __name__ == "__main__":
    main()