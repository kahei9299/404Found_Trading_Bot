import unittest

from bot.data.market_data import Candle
from bot.strategy.backtest import run_precision_sniper_backtest


class BacktestTests(unittest.TestCase):
    def test_empty_backtest_returns_zeroed_summary(self):
        result = run_precision_sniper_backtest([])

        self.assertEqual(result.trades, 0)
        self.assertEqual(result.total_pnl, 0.0)
        self.assertEqual(result.trade_log, [])

    def test_no_signal_backtest_produces_no_trades(self):
        candles = [
            Candle(
                pair="BTC/USD",
                interval="1h",
                open_time=1700000000000 + (idx * 3_600_000),
                close_time=1700003599999 + (idx * 3_600_000),
                open=100.0,
                high=101.0,
                low=99.0,
                close=100.0,
                volume=1000.0,
                quote_volume=100000.0,
                trade_count=100,
                taker_buy_base_volume=500.0,
                taker_buy_quote_volume=50000.0,
                source="binance",
                source_symbol="BTCUSDT",
            )
            for idx in range(80)
        ]

        result = run_precision_sniper_backtest(candles)

        self.assertEqual(result.trades, 0)
        self.assertEqual(result.trade_log, [])


if __name__ == "__main__":
    unittest.main()
