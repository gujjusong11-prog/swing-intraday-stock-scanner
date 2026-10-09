import csv
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from parallel_nse_scanner import scan_parallel
from trade_ledger import (
    LEDGER_FIELDS,
    read_trade_records,
    record_qualifying_setup,
    update_trade_exit,
)


class TradeLedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_dir.name) / "audit.csv"
        self.now = datetime(2026, 10, 8, 10, 15, 30)
        self.setup = {
            "Ticker": "TEST",
            "Status": "Bullish Setup Detected",
            "Raw_Score": 8,
            "LTP": 100.0,
            "Stop_Loss": 95.0,
            "Target": 110.0,
            "Allocated_Qty": 10,
            "Max_Theoretical_Loss": 50.0,
            "Position_Exposure": 1000.0,
            "Risk_Reward_Calculated": 2.0,
            "Volume_Ratio": 2.65,
            "ATR_14": 2.1,
        }

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_qualifying_setup_creates_one_complete_entry_record(self):
        trade_id = record_qualifying_setup(self.setup, path=self.path, now=self.now)

        rows = read_trade_records(self.path)
        self.assertEqual(len(rows), 1)
        self.assertTrue(trade_id.startswith("TRD_20261008_101530_"))
        self.assertEqual(rows[0]["Trade_ID"], trade_id)
        self.assertEqual(rows[0]["Symbol"], "TEST")
        self.assertIn("Bullish Setup Detected", rows[0]["Entry_Reason"])
        self.assertIn("Educational Analysis", rows[0]["Entry_Reason"])
        self.assertTrue(all(rows[0][field] == "" for field in (
            "Exit_Time", "Exit_Price", "Exit_Reason", "Gross_PnL",
            "Brokerage", "Slippage", "Net_PnL", "Capital_Return_Pct",
        )))

    def test_non_qualifying_stock_creates_no_record_or_file(self):
        non_qualifying = {**self.setup, "Status": "Watch / Confirmation Required"}

        self.assertIsNone(record_qualifying_setup(non_qualifying, path=self.path))
        self.assertFalse(self.path.exists())

    def test_missing_optional_technical_values_remain_blank(self):
        setup = {key: value for key, value in self.setup.items() if key not in (
            "Volume_Ratio", "ATR_14", "Technical_VWAP", "VWAP",
            "Pre_Range_Compression_Pct",
        )}
        record_qualifying_setup(setup, path=self.path, now=self.now)

        row = read_trade_records(self.path)[0]
        for field in (
            "Technical_RVol", "Technical_ATR", "Technical_VWAP",
            "Pre_Range_Compression_Pct",
        ):
            self.assertEqual(row[field], "")
        self.assertNotIn("RVol", row["Entry_Reason"])
        self.assertNotIn("ATR", row["Entry_Reason"])

    def test_repeated_open_setup_reuses_trade_id_without_duplicate_row(self):
        first_id = record_qualifying_setup(self.setup, path=self.path, now=self.now)
        second_id = record_qualifying_setup(self.setup, path=self.path, now=self.now)

        self.assertEqual(first_id, second_id)
        self.assertEqual(len(read_trade_records(self.path)), 1)

    def test_exit_updates_existing_trade_row(self):
        trade_id = record_qualifying_setup(self.setup, path=self.path, now=self.now)

        updated = update_trade_exit(
            trade_id,
            110.0,
            "TARGET_HIT",
            path=self.path,
            now=self.now,
        )

        rows = read_trade_records(self.path)
        self.assertTrue(updated)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["Trade_ID"], trade_id)
        self.assertEqual(float(rows[0]["Exit_Price"]), 110.0)
        self.assertEqual(rows[0]["Exit_Reason"], "TARGET_HIT")

    def test_pnl_uses_supplied_actual_costs(self):
        trade_id = record_qualifying_setup(self.setup, path=self.path, now=self.now)
        update_trade_exit(
            trade_id,
            110.0,
            "TARGET_HIT",
            brokerage=5.0,
            slippage=1.0,
            path=self.path,
            now=self.now,
        )

        row = read_trade_records(self.path)[0]
        self.assertAlmostEqual(float(row["Gross_PnL"]), 100.0)
        self.assertAlmostEqual(float(row["Brokerage"]), 5.0)
        self.assertAlmostEqual(float(row["Slippage"]), 1.0)
        self.assertAlmostEqual(float(row["Net_PnL"]), 94.0)
        self.assertAlmostEqual(float(row["Capital_Return_Pct"]), 4.7)

    def test_existing_records_and_legacy_columns_are_preserved(self):
        with self.path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["Legacy_Note", "Symbol", "Trade_ID", "Exit_Price"],
            )
            writer.writeheader()
            writer.writerow({
                "Legacy_Note": "preserve exactly",
                "Symbol": "OLD",
                "Trade_ID": "OLD_TRADE",
                "Exit_Price": "99.5",
            })

        record_qualifying_setup(self.setup, path=self.path, now=self.now)
        rows = read_trade_records(self.path)

        self.assertEqual(rows[0]["Legacy_Note"], "preserve exactly")
        self.assertEqual(rows[0]["Symbol"], "OLD")
        self.assertEqual(rows[0]["Trade_ID"], "OLD_TRADE")
        self.assertEqual(rows[0]["Exit_Price"], "99.5")
        self.assertEqual(len(rows), 2)

    def test_p1_risk_engine_values_are_copied_without_resizing(self):
        record_qualifying_setup(self.setup, path=self.path, now=self.now)
        row = read_trade_records(self.path)[0]

        self.assertEqual(int(row["Allocated_Qty"]), 10)
        self.assertEqual(float(row["Risk_Per_Trade"]), 50.0)
        self.assertEqual(float(row["Position_Exposure"]), 1000.0)
        self.assertEqual(float(row["Planned_SL"]), 95.0)
        self.assertEqual(float(row["Planned_Target"]), 110.0)

    def test_unknown_costs_do_not_fabricate_net_pnl_or_return(self):
        trade_id = record_qualifying_setup(self.setup, path=self.path, now=self.now)
        update_trade_exit(trade_id, 105.0, "MANUAL_EXIT", path=self.path, now=self.now)

        row = read_trade_records(self.path)[0]
        self.assertEqual(float(row["Gross_PnL"]), 50.0)
        self.assertEqual(row["Brokerage"], "")
        self.assertEqual(row["Slippage"], "")
        self.assertEqual(row["Net_PnL"], "")
        self.assertEqual(row["Capital_Return_Pct"], "")

    def test_scanner_persists_only_risk_approved_candidate(self):
        scanner_result = {
            "Ticker": "TEST",
            "LTP": 200.0,
            "Stop_Loss": 195.0,
            "Target": 210.0,
            "Score": 8,
            "Raw_Score": 8,
            "Status": "Bullish Setup Detected",
            "Analysis_Type": "Intraday",
            "P1_Primary_Trend": "PASS",
            "P2_Short_Momentum": "PASS",
            "P3_Pullback_Detection": "PASS",
            "P4_Reversal_Confirmation": "PASS",
            "P5_Volume_Surge": "PASS",
            "P6_RSI_Filter": "PASS",
            "P7_Previous_High_Trigger": "PASS",
            "P8_Risk_Reward": "PASS",
            "RSI_14": 60.0,
            "Volume_Ratio": 2.65,
            "ATR_14": 2.1,
            "Risk_Reward": "1:2.00",
            "Reward_Risk_Ratio": 2.0,
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
            patch(
                "parallel_nse_scanner.record_qualifying_setup",
                side_effect=lambda result: record_qualifying_setup(
                    result, path=self.path, now=self.now
                ),
            ),
        ):
            result = scan_parallel(["TEST"], max_workers=1, realized_daily_loss=0.0)

        self.assertEqual(len(result), 1)
        self.assertEqual(len(read_trade_records(self.path)), 1)
        self.assertEqual(result.iloc[0]["Trade_ID"], read_trade_records(self.path)[0]["Trade_ID"])


if __name__ == "__main__":
    unittest.main()
