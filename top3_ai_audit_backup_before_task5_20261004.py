import os
import json
from google import genai


GEMINI_MODEL = "gemini-3.5-flash-lite"

ALLOWED_STATUSES = {
    "Bullish Setup Detected",
    "Watch / Confirmation Required",
    "Risk Alert / Setup Weakening",
    "No Clear Setup",
}


def run_top3_ai_audit(stock_data):
    """
    Gemini audit layer for Top-3 technical setups.

    Python calculations remain the source of truth.
    Gemini only audits the supplied technical data.
    """

    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        return {
            "status": "AI Monitor Unavailable",
            "message": "GEMINI_API_KEY environment variable not found."
        }

    client = genai.Client(api_key=api_key)

    prompt = f"""
You are a technical-market AUDITOR, not an investment adviser.

Review the following Top-3 stock technical data.

IMPORTANT:
- Do NOT give Buy, Sell, or personalized investment advice.
- Do NOT guarantee profit or accuracy.
- Do NOT invent, infer, estimate, or reconstruct missing data. If a field is not supplied, write "Not Available".
- Use ONLY the supplied Python-calculated data. Every numeric value in the audit must exist in the supplied input. Do not create alternate values.
- Clearly identify uncertainty. Missing fields must remain "Not Available".
- Return exactly one status for each stock from:
  1. Bullish Setup Detected
  2. Watch / Confirmation Required
  3. Risk Alert / Setup Weakening
  4. No Clear Setup

For every stock audit these 10 areas where data is available:
1. Price structure
2. VWAP
3. EMA trend
4. Volume
5. RSI / momentum
6. CPR / Pivot
7. Previous-day levels
8. ATR / risk structure
9. Support / resistance
10. Fakeout or weakening-risk observation

Return ONLY valid JSON in this structure:

{{
  "audits": [
    {{
      "ticker": "ABC",
      "status": "Bullish Setup Detected",
      "confidence": "LOW/MEDIUM/HIGH",
      "technical_summary": "short factual summary",
      "supporting_points": [
        "point 1",
        "point 2",
        "point 3"
      ],
      "risk_flags": [
        "risk 1"
      ],
      "confirmation_required": [
        "confirmation 1"
      ],
      "notification": true,
      "notification_reason": "short reason"
    }}
  ]
}}

Stock data:
{json.dumps(stock_data, indent=2, default=str)}
"""

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt
        )

        text = response.text.strip()

        if text.startswith("```"):
            text = text.replace("```json", "").replace("```", "").strip()

        result = json.loads(text)

        audits = result.get("audits", [])

        for audit in audits:
            if audit.get("status") not in ALLOWED_STATUSES:
                audit["status"] = "Watch / Confirmation Required"

            audit["notification"] = bool(audit.get("notification", False))

        return result

    except Exception as exc:
        return {
            "status": "AI Audit Error",
            "message": str(exc)
        }


if __name__ == "__main__":
    test_data = [
        {
            "Ticker": "RELIANCE",
            "Mode": "Intraday",
            "LTP": 1176.80,
            "VWAP": 1178.20,
            "EMA_9": 1177.10,
            "EMA_21": 1178.00,
            "Volume_Ratio": 0.41,
            "ATR_14": 1.97,
            "Swing_High_20": 1183.80,
            "Swing_Low_20": 1176.30,
            "52W_High": 1611.80,
            "52W_Low": 1176.20,
            "Risk_Reward": "1:2"
        }
    ]

    print("=" * 60)
    print("TOP-3 AI AUDIT MODULE TEST")
    print("=" * 60)

    result = run_top3_ai_audit(test_data)

    print(json.dumps(result, indent=2, ensure_ascii=False))

