import tempfile
import unittest
from unittest.mock import patch

from bot.data.market_data import Candle
from bot.execution.execution import PaperExecutionAdapter
from bot.execution.order_manager import OrderManager
from bot.risk.risk_manager import RiskManager
from bot.runtime.models import BotConfig, TradingPairConfig
from bot.runtime.service import TradingService
from bot.storage.sqlite import SQLiteStorage


class FakeProvider:
    def __init__(self, candles):
        self.candles = candles

    def get_candles(self, pair, interval="1h", limit=100, start_time=None, end_time=None, only_closed=True):
        return self.candles[:limit]


class TradingServiceTests(unittest.TestCase):
    def test_cycle_opens_position_from_signal(self):
        base_time = 1700000000000
        candles = [
            Candle(
                pair="BTC/USD",
                interval="1h",
                open_time=base_time + (idx * 3_600_000),
                close_time=base_time + (idx * 3_600_000) + 3_599_999,
                open=100.0 + idx,
                high=101.0 + idx,
                low=99.0 + idx,
                close=100.5 + idx,
                volume=5_000.0,
                quote_volume=500_000.0,
                trade_count=1_000,
                taker_buy_base_volume=2_500.0,
                taker_buy_quote_volume=250_000.0,
                source="binance",
                source_symbol="BTCUSDT",
            )
            for idx in range(70)
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            storage = SQLiteStorage(f"{tmpdir}/state.sqlite3")
            storage.init_db()
            config = BotConfig(
                pairs=(TradingPairConfig(pair="BTC/USD", interval="1h", candle_limit=70),),
                max_trade_notional=1000.0,
                min_balance=100.0,
            )
            service = TradingService(
                config=config,
                market_data_provider=FakeProvider(candles),
                storage=storage,
                order_manager=OrderManager(PaperExecutionAdapter(), storage),
                risk_manager=RiskManager(config),
            )

            class FakeSignal:
                pair = "BTC/USD"
                interval = "1h"
                open_time = candles[-1].open_time
                direction = "LONG"
                score = 6.0
                entry = candles[-1].close
                stop_loss = candles[-1].close - 5.0
                take_profit_1 = candles[-1].close + 5.0
                take_profit_2 = candles[-1].close + 10.0
                take_profit_3 = candles[-1].close + 15.0

                def to_dict(self):
                    return {
                        "pair": self.pair,
                        "interval": self.interval,
                        "open_time": self.open_time,
                        "direction": self.direction,
                        "score": self.score,
                        "entry": self.entry,
                        "stop_loss": self.stop_loss,
                        "take_profit_1": self.take_profit_1,
                        "take_profit_2": self.take_profit_2,
                        "take_profit_3": self.take_profit_3,
                    }

            with patch.object(service, "_generate_signal", return_value=FakeSignal()):
                result = service.run_cycle()

            self.assertEqual(result["pairs"][0]["action"], "OPENED")
            self.assertIsNotNone(storage.get_open_position("BTC/USD"))


if __name__ == "__main__":
    unittest.main()
