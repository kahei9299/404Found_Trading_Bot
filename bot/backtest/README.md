# Backtest Module

Mean-reversion strategy backtesting framework.

## Overview

This module provides a complete backtesting system for the mean-reversion strategy deployed on the Roostoo exchange.

## Files

- `backtest_simple.py` — Main backtesting engine
  - Generates mock OHLCV data
  - Calculates technical indicators (ATR)
  - Generates trading signals (mean-reversion)
  - Executes backtest simulation
  - Calculates performance metrics (Sharpe, Sortino, Calmar)
  - Generates visualizations (6-panel dashboard)

## Usage

```bash
cd bot/backtest
python backtest_simple.py
```

## Strategy Logic

**Entry Conditions:**
1. Price down 1.5-5% over last 5 bars (oversold)
2. Price up in last 2 bars (momentum reversal)
3. Trading near 5-bar low

**Exit Conditions:**
- Close above 5-bar high (mean reversion captured)
- Trailing stop (11× ATR)
- Hard stop

## Output

- `../logs/backtest_results.png` — Performance dashboard (6 charts)
- `../logs/trade_log.csv` — Detailed trade log with entry/exit data

## Key Metrics

| Metric | Target |
|--------|--------|
| Total Trades | 20-50+ |
| Win Rate | 40%+ |
| Sharpe Ratio | >1.5 |
| Sortino Ratio | >3.0 |
| Max Drawdown | <15% |
| Profit Factor | >1.3 |

## Configuration

Edit the `if __name__ == "__main__"` section to adjust:
- Trading pairs: `symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'XRP/USDT']`
- Backtest period: `days=30`
- Initial capital: `initial_capital=1000000`
- Risk per trade: `risk_per_trade=0.02`

## Notes

- Uses mock data generation for quick testing
- For live backtesting, modify `fetch_ohlcv()` to fetch real Binance data via ccxt
- Trailing stop set to 11× ATR per Mutanabby_AI strategy
- Position sizing based on risk percentage (default 2% per trade)
