from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import requests

from bot.config.settings import (
    MARKET_DATA_BASE_URL,
    MARKET_DATA_DEFAULT_QUOTE,
    MARKET_DATA_PROVIDER,
)


SUPPORTED_INTERVALS = {
    "1m", "3m", "5m", "15m", "30m",
    "1h", "2h", "4h", "6h", "8h", "12h",
    "1d", "3d", "1w", "1M",
}


@dataclass(frozen=True)
class Candle:
    pair: str
    interval: str
    open_time: int
    close_time: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    quote_volume: float
    trade_count: int
    taker_buy_base_volume: float
    taker_buy_quote_volume: float
    source: str
    source_symbol: str


class BinanceMarketDataProvider:
    def __init__(self, base_url: str = MARKET_DATA_BASE_URL, default_quote: str = MARKET_DATA_DEFAULT_QUOTE):
        self.base_url = base_url.rstrip("/")
        self.default_quote = default_quote.upper()

    def get_latest_price(self, pair: str) -> dict[str, Any]:
        symbol = self._to_binance_symbol(pair)
        resp = requests.get(
            f"{self.base_url}/api/v3/ticker/price",
            params={"symbol": symbol},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "pair": pair,
            "source": "binance",
            "source_symbol": symbol,
            "price": float(data["price"]),
        }

    def get_candles(
        self,
        pair: str,
        interval: str = "1h",
        limit: int = 100,
        start_time: int | None = None,
        end_time: int | None = None,
        only_closed: bool = True,
    ) -> list[Candle]:
        if interval not in SUPPORTED_INTERVALS:
            raise ValueError(f"Unsupported interval '{interval}'. Supported intervals: {sorted(SUPPORTED_INTERVALS)}")
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")

        symbol = self._to_binance_symbol(pair)
        params: dict[str, Any] = {
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
        }
        if start_time is not None:
            params["startTime"] = start_time
        if end_time is not None:
            params["endTime"] = end_time

        resp = requests.get(
            f"{self.base_url}/api/v3/klines",
            params=params,
            timeout=10,
        )
        resp.raise_for_status()
        rows = resp.json()
        candles = [self._normalize_candle(pair, interval, symbol, row) for row in rows]
        if not only_closed:
            return candles

        now_ms = int(time.time() * 1000)
        return [candle for candle in candles if candle.close_time <= now_ms]

    def _to_binance_symbol(self, pair: str) -> str:
        if "/" not in pair:
            raise ValueError(f"Pair must look like BASE/QUOTE, got '{pair}'")
        base, quote = pair.upper().split("/", 1)
        if quote == "USD":
            quote = self.default_quote
        return f"{base}{quote}"

    @staticmethod
    def _normalize_candle(pair: str, interval: str, source_symbol: str, row: list[Any]) -> Candle:
        return Candle(
            pair=pair,
            interval=interval,
            open_time=int(row[0]),
            open=float(row[1]),
            high=float(row[2]),
            low=float(row[3]),
            close=float(row[4]),
            volume=float(row[5]),
            close_time=int(row[6]),
            quote_volume=float(row[7]),
            trade_count=int(row[8]),
            taker_buy_base_volume=float(row[9]),
            taker_buy_quote_volume=float(row[10]),
            source="binance",
            source_symbol=source_symbol,
        )


def get_market_data_provider():
    if MARKET_DATA_PROVIDER != "binance":
        raise ValueError(f"Unsupported market data provider '{MARKET_DATA_PROVIDER}'")
    return BinanceMarketDataProvider()
