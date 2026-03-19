# 404Found_Trading_Bot

Trading bot scaffold with:
- Roostoo mock exchange execution in `bot/execution/client.py`
- Binance public market data integration in `bot/data/market_data.py`
- Precision Sniper-style signal engine in `bot/strategy/precision_sniper.py`

## Setup

Install dependencies:

```bash
./.venv/bin/pip install -r requirements.txt
```

Optional environment variables:

```bash
RST_API_KEY=...
RST_SECRET_KEY=...
MARKET_DATA_PROVIDER=binance
MARKET_DATA_BASE_URL=https://api.binance.com
MARKET_DATA_DEFAULT_QUOTE=USDT
```

`MARKET_DATA_DEFAULT_QUOTE` controls how repo pairs like `BTC/USD` are translated for Binance. By default, `BTC/USD` maps to `BTCUSDT`.

## Usage

Roostoo mock execution:

```bash
./.venv/bin/python -m bot.main pairs
./.venv/bin/python -m bot.main price BTC/USD
```

Binance public candles:

```bash
./.venv/bin/python -m bot.main candles BTC/USD --interval 1h --limit 10
```

Precision Sniper signal check:

```bash
./.venv/bin/python -m bot.main signal BTC/USD --interval 1h --limit 250
```

Backtest the current strategy implementation:

```bash
./.venv/bin/python -m bot.main backtest BTC/USD --interval 1h --limit 500
```

You can control how many recent trades are shown in the JSON output:

```bash
./.venv/bin/python -m bot.main backtest BTC/USD --interval 15m --limit 1000 --trades 20
```

## Strategy Notes

The current `Precision Sniper` implementation is a Python approximation of the public TradingView description for:
`https://www.tradingview.com/script/IZj18oYZ-Precision-Sniper-WillyAlgoTrader/`

Implemented now:
- 10-factor confluence scoring
- EMA crossover trigger
- RSI, MACD, VWAP, volume, ADX/DI confirmation
- true higher-timeframe EMA bias using separately fetched HTF candles
- ATR and structure-based stop loss
- TP1, TP2, TP3 calculation
- partial exits and trail ratcheting after TP1 and TP2 in the backtest engine
- closed-candle evaluation only

Not implemented yet:
- TradingView-exact Pine behavior and visuals
- runner beyond TP3

Backtest assumptions:
- entries happen on the next candle open after a confirmed signal
- exits use candle OHLC only; TP checks are processed before the stop check using the pre-ratchet stop level for that bar
- TP1, TP2, and TP3 can each partially scale out of the position
- the remaining stop ratchets to breakeven after TP1 and to TP1 after TP2
