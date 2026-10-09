import unittest
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pandas as pd
from unittest.mock import patch

from data_quality import validate_data_quality
from parallel_nse_scanner import (
    MAX_P4_CANDIDATES,
    MIN_AVG_DAILY_TURNOVER,
    _evaluate_capital_filter,
    _validate_configured_daily_loss,
    apply_smart_pre_filter,
    build_capital_safe_watchlist,
    scan_single_stock,
    scan_parallel,
)


class SmartPreFilterTests(unittest.TestCase):
    def setUp(self):
        self.quality = [{
            "Ticker": "TEST",
            "Data_Quality_Status": "PASS",
            "Data_Quality_Reason": "All required data passed.",
        }]
        self.liquidity = {
            "TEST": {
                "Liquidity_Avg_Daily_Volume": 600_000.0,
                "Liquidity_Avg_Daily_Turnover": 120_000_000.0,
            }
        }

    @staticmethod
    def candidate(symbol="TEST", **overrides):
        row = {
            "Ticker": symbol,
            "LTP": 200.0,
            "Raw_Score": 8,
            "Score": "8/8",
            "Status": "Bullish Setup Detected",
            "Analysis_Type": "Educational Analysis",
            "RSI_14": 60.0,
            "Volume_Ratio": 1.8,
            "ATR_14": 2.0,
            "Risk_Reward": "1:2.00",
            "Risk_Reward_Calculated": 2.0,
            "Stop_Loss": 195.0,
            "Target": 210.0,
            "P1_Primary_Trend": "PASS",
            "P2_Short_Momentum": "PASS",
            "P3_Pullback_Detection": "PASS",
            "P4_Reversal_Confirmation": "PASS",
            "P5_Volume_Surge": "PASS",
            "P6_RSI_Filter": "PASS",
            "P7_Previous_High_Trigger": "PASS",
            "P8_Risk_Reward": "PASS",
            "Technical_VWAP": None,
        }
        row.update(overrides)
        return row

    def test_liquidity_filter_uses_production_exposure_and_real_turnover(self):
        index = pd.date_range("2026-09-01", periods=20, freq="D")
        frame = pd.DataFrame({
            "Close": [200.0] * 20,
            "Volume": [1000] * 20,
        }, index=index)

        metrics, reason = _evaluate_capital_filter(frame)

        self.assertIsNone(reason)
        self.assertEqual(metrics["Liquidity_Avg_Daily_Volume"], 1000)
        self.assertEqual(metrics["Liquidity_Avg_Daily_Turnover"], 200_000)
        self.assertEqual(MIN_AVG_DAILY_TURNOVER, 10_000)

    def test_price_out_of_range_and_low_liquidity_have_specific_reasons(self):
        index = pd.date_range("2026-09-01", periods=20, freq="D")
        outside_price = pd.DataFrame({"Close": [451.0] * 20, "Volume": [1_000_000] * 20}, index=index)
        low_liquidity = pd.DataFrame({"Close": [200.0] * 20, "Volume": [1] * 20}, index=index)

        _, price_reason = _evaluate_capital_filter(outside_price)
        _, liquidity_reason = _evaluate_capital_filter(low_liquidity)

        self.assertIn("PRICE_OUTSIDE_RANGE", price_reason)
        self.assertIn("LOW_LIQUIDITY", liquidity_reason)

    def test_configured_daily_loss_requires_current_date_and_valid_amount(self):
        self.assertEqual(_validate_configured_daily_loss("0", "2026-10-09", "2026-10-09"), 0.0)
        with self.assertRaises(ValueError):
            _validate_configured_daily_loss("0", "2026-10-08", "2026-10-09")
        with self.assertRaises(ValueError):
            _validate_configured_daily_loss("-1", "2026-10-09", "2026-10-09")

    def test_single_symbol_yahoo_multiindex_response_is_extracted(self):
        index = pd.date_range("2026-09-01", periods=20, freq="D")
        columns = pd.MultiIndex.from_product(
            [["TEST.NS"], ["Open", "High", "Low", "Close", "Adj Close", "Volume"]]
        )
        values = [[199.0, 201.0, 198.0, 200.0, 200.0, 1000] for _ in index]
        response = pd.DataFrame(values, index=index, columns=columns)

        with patch("parallel_nse_scanner.yf.download", return_value=response):
            watchlist = build_capital_safe_watchlist(["TEST"], batch_size=1)

        self.assertEqual(watchlist, ["TEST.NS"])

    def test_production_engine_runs_without_duplicate_raw_technical_gate(self):
        engine_result = {"Ticker": "TEST", "Volume_Ratio": 1.8, "RSI_14": 60.0}
        quality = {
            "Ticker": "TEST",
            "Data_Quality_Status": "PASS",
            "Data_Quality_Reason": "All required data passed.",
            "Data_Quality_Timestamp": "2026-10-09T09:00:00+05:30",
        }

        with (
            patch("parallel_nse_scanner.yf.Ticker"),
            patch("parallel_nse_scanner.time.sleep"),
            patch("parallel_nse_scanner._throttled_history", return_value=pd.DataFrame()),
            patch("parallel_nse_scanner.validate_data_quality", return_value=quality),
            patch("parallel_nse_scanner.calculate_eight_parameter_setup", return_value=engine_result) as engine,
            patch("parallel_nse_scanner.is_candidate_pre_filter", return_value=True),
        ):
            result = scan_single_stock("TEST")

        self.assertEqual(result["Ticker"], "TEST")
        self.assertEqual(result["Data_Quality_Status"], "PASS")
        engine.assert_called_once()

    def test_missing_rvol_atr_or_quality_rejects_without_fabricating_values(self):
        candidate = self.candidate(Volume_Ratio=None, ATR_14=None)
        kept, rejected = apply_smart_pre_filter(
            pd.DataFrame([candidate]),
            self.quality,
            self.liquidity,
        )

        self.assertTrue(kept.empty)
        row = rejected.iloc[0]
        self.assertIsNone(row["ATR_Percent"])
        self.assertEqual(row["Filter_Status"], "REJECTED")
        self.assertIn("RVol FAIL (DATA UNAVAILABLE)", row["Filter_Reason"])
        self.assertIn("ATR FAIL (DATA UNAVAILABLE)", row["Filter_Reason"])

        kept, rejected = apply_smart_pre_filter(
            pd.DataFrame([self.candidate()]),
            [],
            self.liquidity,
        )
        self.assertTrue(kept.empty)
        self.assertIn("Data Quality FAIL (DATA UNAVAILABLE)", rejected.iloc[0]["Filter_Reason"])

    def test_stale_intraday_market_data_fails_data_quality(self):
        timezone = ZoneInfo("Asia/Kolkata")
        now = datetime(2026, 10, 9, 12, 0, tzinfo=timezone)
        daily_index = pd.date_range(
            end="2026-10-07 15:30",
            periods=220,
            freq="B",
            tz=timezone,
        )
        intraday_index = pd.date_range(
            end="2026-10-07 15:25",
            periods=100,
            freq="5min",
            tz=timezone,
        )

        def market_frame(index):
            return pd.DataFrame({
                "Open": 199.0,
                "High": 201.0,
                "Low": 198.0,
                "Close": 200.0,
                "Volume": 1000,
            }, index=index)

        result = validate_data_quality(
            "TEST",
            market_frame(daily_index),
            market_frame(intraday_index),
            now=now,
        )

        self.assertEqual(result["Data_Quality_Status"], "FAIL")
        self.assertIn("data is stale", result["Data_Quality_Reason"])

    def test_under_target_candidate_count_is_not_padded_and_fields_are_preserved(self):
        candidate = self.candidate()
        kept, rejected = apply_smart_pre_filter(
            pd.DataFrame([candidate]),
            self.quality,
            self.liquidity,
        )

        self.assertEqual(len(kept), 1)
        self.assertTrue(rejected.empty)
        for field in (
            "Ticker", "LTP", "P1_Primary_Trend", "Score", "RSI_14",
            "Volume_Ratio", "ATR_14", "Technical_VWAP", "Risk_Reward",
            "Stop_Loss", "Target", "Data_Quality_Status",
            "Liquidity_Avg_Daily_Volume", "Liquidity_Avg_Daily_Turnover",
            "Filter_Status", "Filter_Reason",
        ):
            self.assertIn(field, kept.columns)
        self.assertEqual(kept.iloc[0]["Filter_Status"], "PASS")

    def test_candidate_limit_is_twelve_and_rejections_explain_overflow(self):
        candidates = [self.candidate(f"TICKER{number}") for number in range(15)]
        quality = [
            {"Ticker": row["Ticker"], "Data_Quality_Status": "PASS"}
            for row in candidates
        ]
        liquidity = {
            row["Ticker"]: {
                "Liquidity_Avg_Daily_Volume": 600_000.0,
                "Liquidity_Avg_Daily_Turnover": 120_000_000.0,
            }
            for row in candidates
        }

        kept, rejected = apply_smart_pre_filter(pd.DataFrame(candidates), quality, liquidity)

        self.assertEqual(MAX_P4_CANDIDATES, 12)
        self.assertEqual(len(kept), 12)
        self.assertEqual(len(rejected), 3)
        self.assertTrue(rejected["Filter_Reason"].str.contains("CANDIDATE_LIMIT").all())

    def test_scanner_applies_p4_after_risk_and_before_ledger_persistence(self):
        engine_result = self.candidate()
        engine_result["Target_Percent"] = 5.0
        quality = [{
            "Ticker": "TEST",
            "Data_Quality_Status": "PASS",
            "Data_Quality_Reason": "All required data passed.",
        }]
        liquidity = {
            "TEST": {
                "Liquidity_Avg_Daily_Volume": 600_000.0,
                "Liquidity_Avg_Daily_Turnover": 120_000_000.0,
            }
        }

        with (
            patch("parallel_nse_scanner.build_capital_safe_watchlist", return_value=["TEST"]),
            patch("parallel_nse_scanner.scan_single_stock", return_value=engine_result),
            patch("parallel_nse_scanner.get_data_quality_results", return_value=quality),
            patch("parallel_nse_scanner.get_capital_filter_metrics", return_value=liquidity),
            patch("parallel_nse_scanner.record_qualifying_setup", return_value="TRD_TEST") as ledger,
        ):
            result = scan_parallel(["TEST"], max_workers=1, realized_daily_loss=0.0)

        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["Score"], 8)
        self.assertEqual(result.iloc[0]["Allocated_Qty"], 10)
        self.assertEqual(result.iloc[0]["Filter_Status"], "PASS")
        self.assertEqual(result.iloc[0]["Trade_ID"], "TRD_TEST")
        ledger.assert_called_once()

    def test_scanner_does_not_persist_p4_rejected_candidate(self):
        engine_result = self.candidate()
        engine_result["Target_Percent"] = 5.0

        with (
            patch("parallel_nse_scanner.build_capital_safe_watchlist", return_value=["TEST"]),
            patch("parallel_nse_scanner.scan_single_stock", return_value=engine_result),
            patch("parallel_nse_scanner.get_data_quality_results", return_value=[]),
            patch("parallel_nse_scanner.get_capital_filter_metrics", return_value={}),
            patch("parallel_nse_scanner.record_qualifying_setup") as ledger,
        ):
            result = scan_parallel(["TEST"], max_workers=1, realized_daily_loss=0.0)

        self.assertTrue(result.empty)
        ledger.assert_not_called()


if __name__ == "__main__":
    unittest.main()
