import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import software_notifier
import top3_ai_audit
from parallel_nse_scanner import _validate_configured_daily_loss


class ScannerGoLiveTests(unittest.IsolatedAsyncioTestCase):
    async def test_bot2_sender_reports_confirmed_delivery(self):
        bot = MagicMock()
        bot.__aenter__ = AsyncMock(return_value=bot)
        bot.__aexit__ = AsyncMock(return_value=False)
        bot.send_message = AsyncMock(return_value=object())

        with (
            patch.object(software_notifier, "BOT2_TOKEN", "test-token"),
            patch.object(software_notifier, "SCANNER_CHAT_ID", "12345"),
            patch.object(software_notifier, "Bot", return_value=bot),
        ):
            sent = await software_notifier.send_scanner_message("test")

        self.assertTrue(sent)
        bot.send_message.assert_awaited_once_with(chat_id=12345, text="test")

    async def test_bot2_sender_fails_closed_when_unconfigured_or_rejected(self):
        with (
            patch.object(software_notifier, "BOT2_TOKEN", ""),
            patch.object(software_notifier, "SCANNER_CHAT_ID", "12345"),
        ):
            self.assertFalse(await software_notifier.send_scanner_message("test"))

        bot = MagicMock()
        bot.__aenter__ = AsyncMock(return_value=bot)
        bot.__aexit__ = AsyncMock(return_value=False)
        bot.send_message = AsyncMock(side_effect=RuntimeError("delivery rejected"))
        with (
            patch.object(software_notifier, "BOT2_TOKEN", "test-token"),
            patch.object(software_notifier, "SCANNER_CHAT_ID", "12345"),
            patch.object(software_notifier, "Bot", return_value=bot),
        ):
            self.assertFalse(await software_notifier.send_scanner_message("test"))

    def test_gemini_audits_python_selected_rows_without_reranking(self):
        selected_rows = [{
            "Ticker": "TEST",
            "Raw_Score": 8,
            "Score": "8/8",
            "Status": "Bullish Setup Detected",
            "P1_Primary_Trend": "PASS",
            "P2_Short_Momentum": "PASS",
            "P3_Pullback_Detection": "PASS",
            "P4_Reversal_Confirmation": "PASS",
            "P5_Volume_Surge": "PASS",
            "P6_RSI_Filter": "PASS",
            "P7_Previous_High_Trigger": "PASS",
            "P8_Risk_Reward": "PASS",
        }]
        response = MagicMock(text="Educational Analysis. Risk Warning: supplied data only.")
        client = MagicMock()
        client.models.generate_content.return_value = response

        with (
            patch.dict(top3_ai_audit.os.environ, {"GEMINI_API_KEY": "test-key"}),
            patch.object(top3_ai_audit.genai, "Client", return_value=client),
        ):
            result = top3_ai_audit.run_top3_ai_audit(selected_rows)

        self.assertEqual(result["status"], "AI audit available")
        self.assertEqual(result["audits"][0]["Raw_Score"], 8)
        self.assertEqual(selected_rows[0]["Raw_Score"], 8)
        self.assertIn("Educational Analysis", result["gemini_analysis"])
        client.models.generate_content.assert_called_once()

    def test_daily_loss_value_must_be_current_and_nonnegative(self):
        self.assertEqual(
            _validate_configured_daily_loss("0", "2026-10-09", "2026-10-09"),
            0.0,
        )
        with self.assertRaises(ValueError):
            _validate_configured_daily_loss("0", "2026-10-08", "2026-10-09")
        with self.assertRaises(ValueError):
            _validate_configured_daily_loss("-1", "2026-10-09", "2026-10-09")


if __name__ == "__main__":
    unittest.main()