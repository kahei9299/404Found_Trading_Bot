import unittest

from bot.risk.risk_manager import AccountSnapshot, RiskManager
from bot.runtime.models import BotConfig


class DummySignal:
    def __init__(self, pair="BTC/USD", direction="LONG", entry=100.0):
        self.pair = pair
        self.direction = direction
        self.entry = entry


class RiskManagerTests(unittest.TestCase):
    def test_rejects_when_balance_too_low(self):
        config = BotConfig(max_trade_notional=1000.0, min_balance=500.0)
        manager = RiskManager(config, account_snapshot=AccountSnapshot(available_balance=100.0))

        decision = manager.evaluate_signal(DummySignal(), [])

        self.assertFalse(decision.approved)
        self.assertEqual(decision.reason, "INSUFFICIENT_BALANCE")

    def test_approves_and_sizes_from_notional(self):
        config = BotConfig(max_trade_notional=1000.0, min_balance=100.0)
        manager = RiskManager(config, account_snapshot=AccountSnapshot(available_balance=1000.0))

        decision = manager.evaluate_signal(DummySignal(entry=200.0), [])

        self.assertTrue(decision.approved)
        self.assertEqual(decision.size, 5.0)
        self.assertEqual(decision.notional, 1000.0)


if __name__ == "__main__":
    unittest.main()
