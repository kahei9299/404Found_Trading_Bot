# Strategy Module

Trading strategies for Roostoo exchange bot.

## Available Strategies

### Mean-Reversion Strategy (`strategy.py`)

Captures oversold bounces by identifying exhaustion in selling pressure.

**Entry Conditions:**
1. Price down 1.5-5% over last 5 bars (oversold zone)
2. Price up in last 2 bars (momentum reversal signal)
3. Trading near 5-bar low (confirmation)

**Exit Conditions:**
- Price closes above 5-bar high (mean reversion captured)
- Trailing stop at 11× ATR (profit protection)
- Hard stop at entry - 11× ATR (risk management)

**Parameters:**
- `atr_period`: 14 bars
- `atr_multiplier`: 11.0
- `lookback_period`: 5 bars
- `min_price_change`: -5.0%
- `max_price_change`: -1.5%

**Backtest Results (30 days, 4 pairs):**
- Total Trades: 21
- Win Rate: 42.86%
- Return: 5.88%
- Sharpe Ratio: 1.913
- Sortino Ratio: 5.779
- Max Drawdown: -9.06%

## Usage

```python
from bot.strategy import MeanReversionStrategy, StrategyManager

# Single pair
strategy = MeanReversionStrategy()
signals = strategy.get_ohlcv_signals(df)

# Multiple pairs
manager = StrategyManager()
manager.add_pair('BTC/USDT')
manager.add_pair('ETH/USDT')
signal = manager.get_signal('BTC/USDT', df)
```

## Strategy Classes

### MeanReversionStrategy
Core strategy implementation with signal generation and position tracking.

**Methods:**
- `get_ohlcv_signals(df)` - Generate entry/exit signals
- `calculate_atr(high, low, close)` - Calculate ATR
- `update_trailing_stop(price, atr)` - Update trailing stop
- `check_exit(price, signal, hard_stop)` - Check exit conditions

### StrategyManager
Manages multiple strategy instances for different trading pairs.

**Methods:**
- `add_pair(symbol)` - Initialize strategy for pair
- `get_signal(symbol, df)` - Get signals for pair
- `update_position(symbol, position)` - Track open positions
- `close_position(symbol)` - Close position

## Integration with Bot

The strategy is integrated into the main bot via:

```python
from bot.strategy import StrategyManager
from bot.execution import Executor

manager = StrategyManager()
executor = Executor(api_key, api_secret)

# For each bar of OHLCV data:
signal = manager.get_signal(symbol, df)
if signal['entry']:
    executor.place_order(symbol, 'BUY', quantity)
```

## Notes

- Tested on 30m timeframe
- Works across multiple cryptocurrency pairs
- Uses 2% risk per trade
- Position sizing based on ATR and account equity
- Trailing stop adjusts dynamically with price movement
