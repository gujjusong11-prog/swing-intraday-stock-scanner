import unittest
from unittest.mock import patch

import pandas as pd

from capital_risk_engine import apply_capital_risk, daily_loss_limit_reached
from parallel_nse_scanner import scan_parallel


class CapitalRiskEngineTests(unittest.TestCase):
    def setUp(self):
        self.candidate = {
            "Rank": 1,
            "Ticker": "TEST",
            "LTP": 200.0,
            "Stop_Loss": 195.0,
            "Target": 210.0,
            "Score": 8,
            "Status": "Bullish Setup Detected",
        }

    def test_position_size_respects_capital_exposure_and_risk(self):
        approved = apply_capital_risk(pd.DataFrame([self.candidate]), 0.0)

        self.assertEqual(len(approved), 1)
        row = approved.iloc[0]
        self.assertEqual(row["Allocated_Qty"], 10)
        self.assertEqual(row["Position_Exposure"], 2000.0)
        self.assertEqual(row["Max_Theoretical_Loss"], 50.0)
        self.assertLessEqual(row["Max_Theoretical_Loss"], 100.0)

    def test_quantity_is_capped_by_maximum_trade_risk(self):
        candidate = {**self.candidate, "LTP": 100.0, "Stop_Loss": 90.0, "Target": 120.0}
        approved = apply_capital_risk(pd.DataFrame([candidate]), 0.0)

        self.assertEqual(approved.iloc[0]["Allocated_Qty"], 10)
        self.assertEqual(approved.iloc[0]["Max_Theoretical_Loss"], 100.0)

    def test_rejects_low_reward_to_risk_and_zero_quantity(self):
        low_reward = {**self.candidate, "Target": 209.0}
        unaffordable = {**self.candidate, "LTP": 2500.0, "Stop_Loss": 2400.0, "Target": 2700.0}
        approved = apply_capital_risk(pd.DataFrame([low_reward, unaffordable]), 0.0)

        self.assertTrue(approved.empty)

    def test_total_allocated_exposure_does_not_exceed_capital(self):
        second_candidate = {**self.candidate, "Rank": 2, "Ticker": "NEXT"}
        approved = apply_capital_risk(pd.DataFrame([self.candidate, second_candidate]), 0.0)

        self.assertEqual(len(approved), 1)
        self.assertLessEqual(approved["Position_Exposure"].sum(), 2000.0)
        self.assertLessEqual(approved["Position_Exposure"].sum(), 10000.0)

    def test_daily_loss_limit_and_unknown_loss_block_setups(self):
        self.assertFalse(daily_loss_limit_reached(149.99))
        self.assertTrue(daily_loss_limit_reached(150.0))
        self.assertTrue(daily_loss_limit_reached(None))
        self.assertTrue(apply_capital_risk(pd.DataFrame([self.candidate]), 150.0).empty)

    def test_only_fully_qualified_p1_p8_setups_are_approved(self):
        watch = {**self.candidate, "Score": 7, "Status": "Watch / Confirmation Required"}
        approved = apply_capital_risk(pd.DataFrame([watch]), 0.0)

        self.assertTrue(approved.empty)

    def test_scanner_pipeline_returns_position_sizing_fields(self):
        scanner_result = {
            **{key: value for key, value in self.candidate.items() if key != "Rank"},
            "Raw_Score": 8,
            "Analysis_Type": "Intraday",
            "P1_Primary_Trend": True,
            "P2_Short_Momentum": True,
            "P3_Pullback_Detection": True,
            "P4_Reversal_Confirmation": True,
            "P5_Volume_Surge": True,
            "P6_RSI_Filter": True,
            "P7_Previous_High_Trigger": True,
            "P8_Risk_Reward": True,
            "RSI_14": 60.0,
            "Volume_Ratio": 1.8,
            "ATR_14": 2.0,
            "Risk_Reward": "1:2.00",
            "Target_Percent": 5.0,
        }

        with (
            patch("parallel_nse_scanner.build_capital_safe_watchlist", return_value=["TEST"]),
            patch("parallel_nse_scanner.scan_single_stock", return_value=scanner_result),
            patch("parallel_nse_scanner.get_data_quality_results", return_value=[{
                "Ticker": "TEST",
                "Data_Quality_Status": "PASS",
                "Data_Quality_Reason": "Test data quality passed.",
            }]),
            patch("parallel_nse_scanner.get_capital_filter_metrics", return_value={
                "TEST": {
                    "Liquidity_Avg_Daily_Volume": 600_000.0,
                    "Liquidity_Avg_Daily_Turnover": 120_000_000.0,
                }
            }),
        ):
            result = scan_parallel(["TEST"], max_workers=1, realized_daily_loss=0.0)

        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["Allocated_Qty"], 10)
        self.assertEqual(result.iloc[0]["Max_Theoretical_Loss"], 50.0)
        self.assertEqual(result.iloc[0]["Position_Exposure"], 2000.0)

    def test_scanner_blocks_generation_before_market_data_at_daily_limit(self):
        with patch("parallel_nse_scanner.build_capital_safe_watchlist") as watchlist:
            result = scan_parallel(["TEST"], realized_daily_loss=150.0)

        self.assertTrue(result.empty)
        watchlist.assert_not_called()


if __name__ == "__main__":
    unittest.main()
