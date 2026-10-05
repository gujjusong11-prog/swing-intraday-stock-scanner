
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class RuntimeErrorRecord:
    file_name: str
    function_name: str
    error_type: str
    error_message: str
    traceback_text: str = ""
    context: str = ""


def build_runtime_error_report(
    *,
    file_name: str,
    function_name: str,
    error_message: str,
    traceback_text: str = "",
    context: str = "",
) -> str:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return (
        "🚨 SOFTWARE ERROR & ACTION REPORT\n"
        f"Time: {timestamp}\n"
        f"File: {file_name}\n"
        f"Function: {function_name}\n"
        f"Problem: {error_message}\n\n"
        "Traceback:\n"
        f"{traceback_text or 'Not available'}\n\n"
        "Context:\n"
        f"{context or 'Not available'}\n"
    )


def build_chatgpt_ready_prompt(
    *,
    file_name: str,
    function_name: str,
    error_message: str,
    traceback_text: str,
    context: str,
    gemini_diagnosis: str,
) -> str:
    return (
        "Review the actual project file/code and diagnose this runtime error.\n\n"
        f"File: {file_name}\n"
        f"Function: {function_name}\n"
        f"Error: {error_message}\n\n"
        "Traceback:\n"
        f"{traceback_text or 'Not available'}\n\n"
        "Context:\n"
        f"{context or 'Not available'}\n\n"
        "Gemini Diagnosis:\n"
        f"{gemini_diagnosis or 'Not available'}\n\n"
        "Requirements:\n"
        "1. Identify the exact root cause.\n"
        "2. Propose the smallest safe fix.\n"
        "3. Do not change P1-P8 logic unless explicitly required.\n"
        "4. Do not change scanner scoring/ranking behavior unnecessarily.\n"
        "5. Provide an automated test for the fix.\n"
    )


def diagnose_runtime_error(
    *,
    file_name: str,
    function_name: str,
    error_message: str,
    traceback_text: str = "",
    context: str = "",
) -> dict[str, Any]:

    report = build_runtime_error_report(
        file_name=file_name,
        function_name=function_name,
        error_message=error_message,
        traceback_text=traceback_text,
        context=context,
    )

    gemini_diagnosis = ""
    gemini_status = "NOT_RUN"

    try:
        from gemini_test_auditor import run_gemini_diagnostics

        gemini_result = run_gemini_diagnostics(
            "RUNTIME_ERROR",
            {
                "file_name": file_name,
                "function_name": function_name,
                "error_message": error_message,
                "traceback": traceback_text,
                "context": context,
            },
            {
                "python_diagnostic_status": "READY",
                "python_report": report,
            },
        )

        gemini_status = str(gemini_result.get("status", "UNKNOWN"))
        gemini_diagnosis = str(gemini_result.get("report", ""))

    except Exception as exc:
        gemini_status = f"FAILED: {type(exc).__name__}: {exc}"
        gemini_diagnosis = (
            "Gemini diagnosis unavailable. "
            "Python diagnostic report remains valid."
        )

    chatgpt_ready_prompt = build_chatgpt_ready_prompt(
        file_name=file_name,
        function_name=function_name,
        error_message=error_message,
        traceback_text=traceback_text,
        context=context,
        gemini_diagnosis=gemini_diagnosis,
    )

    final_message = (
        f"{report}\n"
        "Gemini Diagnosis:\n"
        f"{gemini_diagnosis or 'Not available'}\n\n"
        "ChatGPT-Ready Prompt:\n"
        f"{chatgpt_ready_prompt}"
    )

    telegram_status = "NOT_SENT"

    try:
        telegram_status = asyncio.run(
            send_runtime_error_report(final_message)
        )
    except Exception as exc:
        telegram_status = f"FAILED: {type(exc).__name__}: {exc}"

    return {
        "status": "READY",
        "report": report,
        "gemini_status": gemini_status,
        "gemini_diagnosis": gemini_diagnosis,
        "chatgpt_ready_prompt": chatgpt_ready_prompt,
        "telegram_status": telegram_status,
        "message": final_message,
    }


async def send_runtime_error_report(message: str) -> bool:
    from software_notifier import send_telegram_message
    return await send_telegram_message(message)
