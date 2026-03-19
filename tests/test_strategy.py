import unittest

from bot.data.market_data import Candle
from bot.strategy.precision_sniper import generate_precision_sniper_signal, infer_htf_interval


class StrategyTests(unittest.TestCase):
    def test_infer_htf_interval(self):
        self.assertEqual(infer_htf_interval("1h"), "4h")
        self.assertEqual(infer_htf_interval("15m"), "1h")
        self.assertIsNone(infer_htf_interval("1M"))

    def test_returns_none_when_not_enough_history(self):
        candles = [
            Candle(
                pair="BTC/USD",
                interval="1h",
                open_time=1700000000000 + (idx * 3_600_000),
                close_time=1700003599999 + (idx * 3_600_000),
                open=100 + idx,
                high=101 + idx,
                low=99 + idx,
                close=100.5 + idx,
                volume=1000 + idx,
                quote_volume=100000 + idx,
                trade_count=100 + idx,
                taker_buy_base_volume=500 + idx,
                taker_buy_quote_volume=50000 + idx,
                source="binance",
                source_symbol="BTCUSDT",
            )
            for idx in range(20)
        ]

        signal = generate_precision_sniper_signal(candles)

        self.assertIsNone(signal)


if __name__ == "__main__":
    unittest.main()
