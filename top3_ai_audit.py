from datetime import datetime
import math


AUDIT_CHECKS = [
  "Audit_1_Candle",
  "Audit_2_Support_Resistance",
  "Audit_3_Volume",
  "Audit_4_Trend",
  "Audit_5_Momentum_RSI",
  "Audit_6_Pullback",
  "Audit_7_Volatility",
  "Audit_8_Sector",
  "Audit_9_Event_Risk",
  "Audit_10_Overall_Consistency",
]

PARAMETER_FIELDS = [
  "P1_Primary_Trend",
  "P2_Short_Momentum",
  "P3_Pullback_Detection",
  "P4_Reversal_Confirmation",
  "P5_Volume_Surge",
  "P6_RSI_Filter",
  "P7_Previous_High_Trigger",
  "P8_Risk_Reward",
]


def _is_available(value):
  if value is None or str(value).strip().lower() in {"", "nan", "none", "<na>"}:
    return False
  try:
    return not math.isnan(float(value))
  except (TypeError, ValueError):
    return True


def _parameter_result(row, field):
  value = row.get(field)
  normalized = str(value).strip().upper() if _is_available(value) else ""
  if normalized in {"PASS", "FAIL"}:
    return normalized
  return "CAUTION"


def _check(status, reason):
  return {"Status": status, "Reason": reason}


def _scanner_check(row, field, label, detail=None):
  status = _parameter_result(row, field)
  if status == "CAUTION":
    return _check(status, f"{label} result is unavailable in scanner data.")
  explanation = f"{field}={status}; the scanner's {label.lower()} rule {status.lower()}."
  if detail:
    explanation = f"{detail}; {explanation}"
  return _check(status, explanation)


def _overall_consistency(row):
  results = [_parameter_result(row, field) for field in PARAMETER_FIELDS]
  passed = results.count("PASS")
  failed = results.count("FAIL")
  unknown = results.count("CAUTION")

  raw_score = row.get("Raw_Score")
  if unknown:
    return _check(
      "CAUTION",
      f"P1-P8 contain {passed} PASS, {failed} FAIL, and {unknown} unavailable result(s); consistency cannot be fully verified.",
    )

  if _is_available(raw_score):
    try:
      score_matches = float(raw_score) == passed
    except (TypeError, ValueError):
      score_matches = False
    if not score_matches:
      return _check(
        "FAIL",
        f"P1-P8 contain {passed} PASS results, but Raw_Score={raw_score}; the scanner fields are inconsistent.",
      )
  else:
    return _check("CAUTION", "Raw_Score is unavailable; score consistency cannot be verified.")

  status = "FAIL" if failed else "PASS"
  return _check(
    status,
    f"P1-P8 contain {passed} PASS and {failed} FAIL; Raw_Score={raw_score} matches the PASS count.",
  )


def _audit_stock(row, timestamp):
  checks = {}
  checks["Audit_1_Candle"] = _scanner_check(
    row,
    "P4_Reversal_Confirmation",
    "candle structure",
  )

  references = []
  for field in ("Previous_Day_High", "Swing_Low_5M"):
    value = row.get(field)
    if _is_available(value):
      references.append(f"{field}={value}")
  reference_text = f" Scanner references: {', '.join(references)}." if references else ""
  checks["Audit_2_Support_Resistance"] = _check(
    "CAUTION",
    f"No explicit support/resistance classification is supplied; available reference levels are not classified.{reference_text}",
  )

  volume_ratio = row.get("Volume_Ratio")
  volume_detail = f"Volume_Ratio={volume_ratio}" if _is_available(volume_ratio) else None
  checks["Audit_3_Volume"] = _scanner_check(
    row,
    "P5_Volume_Surge",
    "volume behaviour",
    volume_detail,
  )
  checks["Audit_4_Trend"] = _scanner_check(
    row,
    "P1_Primary_Trend",
    "primary trend",
  )

  rsi = row.get("RSI_14")
  rsi_detail = f"RSI_14={rsi}" if _is_available(rsi) else None
  checks["Audit_5_Momentum_RSI"] = _scanner_check(
    row,
    "P6_RSI_Filter",
    "momentum/RSI context",
    rsi_detail,
  )
  checks["Audit_6_Pullback"] = _scanner_check(
    row,
    "P3_Pullback_Detection",
    "pullback quality",
  )

  atr = row.get("ATR_14")
  if _is_available(atr):
    checks["Audit_7_Volatility"] = _check(
      "CAUTION",
      f"ATR_14={atr}; no scanner-defined volatility threshold is supplied for classification.",
    )
  else:
    checks["Audit_7_Volatility"] = _check(
      "CAUTION",
      "ATR_14 is unavailable in scanner data.",
    )

  checks["Audit_8_Sector"] = _check(
    "CAUTION",
    "Sector classification/data unavailable.",
  )
  checks["Audit_9_Event_Risk"] = _check(
    "CAUTION",
    "Event information could not be verified from the supplied scanner/market data.",
  )
  checks["Audit_10_Overall_Consistency"] = _overall_consistency(row)

  counts = {
    status: sum(check["Status"] == status for check in checks.values())
    for status in ("PASS", "CAUTION", "FAIL")
  }
  result = {
    "Rank": row.get("Rank"),
    "Ticker": row.get("Ticker"),
    "Raw_Score": row.get("Raw_Score"),
    "Score": row.get("Score"),
    "Status": row.get("Status"),
    "Analysis_Type": row.get("Analysis_Type", "Educational Analysis"),
    **checks,
    "AI_Audit_Summary": (
      "AI audit unavailable; deterministic review of supplied scanner data only. "
      f"Checks: {counts['PASS']} PASS, {counts['CAUTION']} CAUTION, {counts['FAIL']} FAIL. "
      "Python technical calculations remain the source of truth. Educational Analysis."
    ),
    "AI_Audit_Timestamp": timestamp,
  }
  return result


def run_top3_ai_audit(stock_data):
  """Audit, without reranking, at most the first three supplied scanner rows."""
  if hasattr(stock_data, "to_dict"):
    rows = stock_data.to_dict(orient="records")
  elif isinstance(stock_data, dict):
    rows = [stock_data]
  else:
    rows = list(stock_data or [])

  timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
  audits = [_audit_stock(row, timestamp) for row in rows[:3]]
  return {
    "status": "AI audit unavailable",
    "message": "No external AI service is configured; checks use supplied Python scanner data only.",
    "audits": audits,
  }

