import unittest
from unittest.mock import Mock, patch

from bot.data.market_data import BinanceMarketDataProvider


class BinanceMarketDataProviderTests(unittest.TestCase):
    def setUp(self):
        self.provider = BinanceMarketDataProvider()

    def test_usd_pair_maps_to_default_quote(self):
        self.assertEqual(self.provider._to_binance_symbol("BTC/USD"), "BTCUSDT")

    @patch("bot.data.market_data.requests.get")
    def test_get_candles_normalizes_binance_payload(self, mock_get):
        mock_response = Mock()
        mock_response.json.return_value = [[
            1700000000000,
            "50000.0",
            "51000.0",
            "49000.0",
            "50500.0",
            "123.45",
            1700003599999,
            "6200000.0",
            1000,
            "61.72",
            "3100000.0",
            "0",
        ]]
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        candles = self.provider.get_candles("BTC/USD", interval="1h", limit=1)

        self.assertEqual(len(candles), 1)
        self.assertEqual(candles[0].pair, "BTC/USD")
        self.assertEqual(candles[0].source_symbol, "BTCUSDT")
        self.assertEqual(candles[0].close, 50500.0)
        self.assertEqual(candles[0].trade_count, 1000)


if __name__ == "__main__":
    unittest.main()
