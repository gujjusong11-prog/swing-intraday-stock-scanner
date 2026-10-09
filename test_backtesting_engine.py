import unittest
from unittest.mock import patch

import pandas as pd

from backtesting_engine import (
    DEFAULT_BROKERAGE_PER_TRADE,
    DEFAULT_SLIPPAGE_RATE,
    run_backtest,
)
from eight_parameter_engine import calculate_eight_parameter_setup


class BacktestingEngineTests(unittest.TestCase):
    def setUp(self):
        self.daily, self.intraday = self._market_frames()
        self.trigger_timestamp = self.intraday.index[110]
        self.engine_result = {
            "Ticker": "TEST",
            "LTP": 100.0,
            "Stop_Loss": 95.0,
            "Target": 110.0,
            "Risk_Reward": "1:2.00",
            "Reward_Risk_Ratio": 2.0,
            "Score": "8/8",
            "Raw_Score": 8,
            "Status": "Bullish Setup Detected",
            "Analysis_Type": "Educational Analysis",
        }

    @staticmethod
    def _market_frames():
        timezone = "Asia/Kolkata"
        daily_index = pd.bdate_range(end="2026-10-08", periods=230, tz=timezone)
        daily_close = pd.Series([80.0 + index * 0.1 for index in range(230)], index=daily_index)
        daily = pd.DataFrame({
            "Open": daily_close - 0.2,
            "High": daily_close + 0.5,
            "Low": daily_close - 0.5,
            "Close": daily_close,
            "Volume": 1_000_000,
        }, index=daily_index)

        timestamps = []
        for session_date in daily_index[-2:]:
            session = pd.date_range(
                session_date.normalize() + pd.Timedelta(hours=9, minutes=15),
                periods=70,
                freq="5min",
            )
            timestamps.extend(session)
        intraday_index = pd.DatetimeIndex(timestamps)
        closes = [99.0 + (index % 4) * 0.1 for index in range(len(intraday_index))]
        intraday = pd.DataFrame({
            "Open": [close - 0.1 for close in closes],
            "High": [close + 0.2 for close in closes],
            "Low": [close - 0.3 for close in closes],
            "Close": closes,
            "Volume": 1000,
        }, index=intraday_index)
        intraday.iloc[111, intraday.columns.get_loc("Open")] = 100.0
        intraday.iloc[111, intraday.columns.get_loc("High")] = 111.0
        intraday.iloc[111, intraday.columns.get_loc("Low")] = 94.0
        intraday.iloc[111, intraday.columns.get_loc("Close")] = 102.0
        return daily, intraday

    def test_production_engine_receives_historical_prefix_and_trade_costs_are_applied(self):
        def setup_at_selected_bars(
            ticker,
            mode,
            daily_data,
            intraday_data,
        ):
            if intraday_data.index[-1] in {
                self.trigger_timestamp,
                self.intraday.index[111],
                self.intraday.index[120],
            }:
                return dict(self.engine_result)
            return None

        with patch(
            "backtesting_engine.calculate_eight_parameter_setup",
            side_effect=setup_at_selected_bars,
        ) as setup_engine:
            report = run_backtest({"TEST": (self.daily, self.intraday)})

        self.assertGreater(setup_engine.call_count, 0)
        self.assertEqual(report["Total_Setups"], 2)
        self.assertEqual(report["Executed_Hypothetical_Trades"], 1)
        self.assertEqual(report["Completed_Trades"], 1)
        self.assertEqual(report["Daily_Loss_Limit_Breaches"], 1)
        self.assertEqual(report["Signals"][0]["Trade_Type"], "SIGNAL DETECTED")
        trade = report["Trades"][0]
        self.assertEqual(trade["Trade_Type"], "HYPOTHETICAL TRADE")
        self.assertEqual(trade["Exit_Reason"], "STOP_LOSS_HIT")
        self.assertEqual(trade["Exit_Price"], 95.0)
        self.assertEqual(trade["Allocated_Qty"], 20)
        self.assertEqual(trade["Risk_Per_Trade"], 100.0)
        self.assertEqual(trade["Gross_PnL"], -100.0)
        self.assertEqual(trade["Brokerage"], DEFAULT_BROKERAGE_PER_TRADE)
        self.assertAlmostEqual(trade["Slippage"], DEFAULT_SLIPPAGE_RATE * 20 * (100 + 95))
        self.assertAlmostEqual(trade["Net_PnL"], -151.95)
        self.assertAlmostEqual(report["Net_PnL"], -151.95)
        self.assertAlmostEqual(report["Maximum_Drawdown"], 151.95)
        self.assertEqual(report["Cost_Assumptions"]["Brokerage_Per_Completed_Trade"], 50.0)

    def test_target_exit_uses_target_price_not_favorable_gap_open(self):
        intraday = self.intraday.copy()
        intraday.iloc[111, intraday.columns.get_loc("Open")] = 112.0
        intraday.iloc[111, intraday.columns.get_loc("High")] = 113.0
        intraday.iloc[111, intraday.columns.get_loc("Low")] = 100.0
        intraday.iloc[111, intraday.columns.get_loc("Close")] = 112.0

        def setup_at_trigger(ticker, mode, daily_data, intraday_data):
            if intraday_data.index[-1] == self.trigger_timestamp:
                return dict(self.engine_result)
            return None

        with patch("backtesting_engine.calculate_eight_parameter_setup", side_effect=setup_at_trigger):
            report = run_backtest({"TEST": (self.daily, intraday)})

        trade = report["Trades"][0]
        self.assertEqual(trade["Exit_Reason"], "TARGET_HIT")
        self.assertEqual(trade["Exit_Price"], 110.0)

    def test_no_qualifying_setup_produces_no_hypothetical_trade(self):
        with patch("backtesting_engine.calculate_eight_parameter_setup", return_value=None):
            report = run_backtest({"TEST": (self.daily, self.intraday)})

        self.assertGreater(report["Total_Scanned_Opportunities"], 0)
        self.assertEqual(report["Total_Setups"], 0)
        self.assertEqual(report["Executed_Hypothetical_Trades"], 0)
        self.assertEqual(report["Trades"], [])

    def test_real_production_setup_engine_accepts_historical_prefixes(self):
        with patch(
            "backtesting_engine.calculate_eight_parameter_setup",
            wraps=calculate_eight_parameter_setup,
        ) as production_engine:
            report = run_backtest({"TEST": (self.daily, self.intraday)})

        self.assertGreater(production_engine.call_count, 0)
        _, engine_kwargs = production_engine.call_args
        self.assertIsInstance(engine_kwargs["daily_data"], pd.DataFrame)
        self.assertIsInstance(engine_kwargs["intraday_data"], pd.DataFrame)
        self.assertLessEqual(len(engine_kwargs["intraday_data"]), len(self.intraday))
        self.assertEqual(report["Data_Source"], "yfinance historical data")

    def test_missing_historical_data_is_reported_as_unavailable(self):
        report = run_backtest({"TEST": (self.daily, self.intraday.iloc[0:0])})

        self.assertEqual(report["Status"], "DATA UNAVAILABLE")
        self.assertIn("TEST", report["Unavailable_Symbols"])
        self.assertEqual(report["Trades"], [])

    def test_cost_inputs_must_be_nonnegative(self):
        with self.assertRaises(ValueError):
            run_backtest(
                {"TEST": (self.daily, self.intraday)},
                brokerage_per_trade=-1,
            )


if __name__ == "__main__":
    unittest.main()
