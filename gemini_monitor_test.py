import os
from datetime import datetime
from google import genai

MODEL = "gemini-3.5-flash-lite"

def run_ai_monitor_test():
    api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        return {
            "status": "FAIL",
            "message": "GEMINI_API_KEY environment variable not found."
        }

    try:
        client = genai.Client(api_key=api_key)

        response = client.models.generate_content(
            model=MODEL,
            contents=(
                "You are a software audit monitor. "
                "Reply with exactly these three lines:\n"
                "STATUS: PASS\n"
                "ROLE: AI AUDITOR\n"
                "MESSAGE: Gemini AI Monitor is operational"
            )
        )

        text = (response.text or "").strip()

        return {
            "status": "PASS",
            "model": MODEL,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "response": text
        }

    except Exception as exc:
        return {
            "status": "FAIL",
            "model": MODEL,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "error": str(exc)
        }


if __name__ == "__main__":
    result = run_ai_monitor_test()

    print("=" * 60)
    print("GEMINI AI MONITOR - STANDALONE TEST")
    print("=" * 60)
    print(f"Status    : {result['status']}")
    print(f"Model     : {result.get('model', 'N/A')}")
    print(f"Timestamp : {result.get('timestamp', 'N/A')}")

    if result["status"] == "PASS":
        print("-" * 60)
        print(result["response"])
    else:
        print("-" * 60)
        print(f"Error: {result['message'] if 'message' in result else result['error']}")

    print("=" * 60)
