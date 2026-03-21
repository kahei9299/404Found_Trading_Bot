"""
CryptoFlux Dynamo Backtest Runner
Tests the strategy on real Binance 30m data
"""

import logging
import sys
import ccxt
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path

# Setup logging
log_dir = Path('bot/logs')
log_dir.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[
        logging.FileHandler('bot/logs/backtest_cryptoflux.log', mode='w'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Import strategy
sys.path.insert(0, '.')
from bot.strategy.cryptoflux import CryptoFluxDynamo


def fetch_binance_data(symbol: str, timeframe: str = '30m', days: int = 60) -> pd.DataFrame:
    """Fetch real OHLCV data from Binance via CCXT"""
    logger.info(f"[FETCH] Downloading {days} days of {timeframe} data for {symbol}...")
    
    exchange = ccxt.binance()
    since = exchange.parse8601((datetime.utcnow() - timedelta(days=days)).isoformat() + 'Z')
    
    all_candles = []
    target_time = exchange.milliseconds()
    
    while since < target_time:
        try:
            candles = exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=1000)
            if not candles:
                break
            all_candles.extend(candles)
            since = candles[-1][0] + 1
            logger.info(f"  Downloaded {len(all_candles)} candles so far...")
        except Exception as e:
            logger.warning(f"[WARNING] {str(e)[:100]}")
            break
    
    if not all_candles:
        logger.error(f"[ERROR] No data fetched for {symbol}")
        return None
    
    df = pd.DataFrame(
        all_candles,
        columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
    )
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df = df.sort_values('timestamp').reset_index(drop=True)
    df = df.drop_duplicates(subset=['timestamp'], keep='first')
    
    logger.info(f"[SUCCESS] Downloaded {len(df)} candles ({df['timestamp'].min().date()} to {df['timestamp'].max().date()})")
    return df


def run_backtest(symbol: str, df: pd.DataFrame, initial_capital: float = 1000000) -> dict:
    """Run CryptoFlux backtest on a symbol"""
    logger.info(f"\n[START] Backtest: {symbol}")
    logger.info(f"  Period: {df['timestamp'].min().date()} to {df['timestamp'].max().date()}")
    logger.info(f"  Candles: {len(df)}")
    
    strategy = CryptoFluxDynamo(min_signal_strength=20.0)  # Optimized threshold based on actual signal distribution
    
    trades = []
    position = None
    equity = initial_capital
    max_equity = initial_capital
    
    for i in range(100, len(df)):  # Need at least 100 bars for proper indicator calculation
        window = df.iloc[max(0, i-100):i+1]
        current_close = df.iloc[i]['close']
        
        # Check exit
        if position:
            should_exit, exit_reason = strategy.check_exit(window, position['direction'])
            
            if should_exit:
                exit_price = current_close
                if position['direction'] == 'long':
                    pnl = (exit_price - position['entry']) * position['quantity']
                else:  # short
                    pnl = (position['entry'] - exit_price) * position['quantity']
                
                pnl_pct = (pnl / (position['entry'] * position['quantity'])) * 100
                equity += pnl
                
                trade = {
                    'entry_date': position['entry_date'],
                    'exit_date': df.iloc[i]['timestamp'],
                    'entry_price': position['entry'],
                    'exit_price': exit_price,
                    'quantity': position['quantity'],
                    'direction': position['direction'],
                    'pnl': pnl,
                    'pnl_pct': pnl_pct,
                    'exit_reason': exit_reason,
                    'signal_score': position['signal_score'],
                    'regime': position['regime']
                }
                trades.append(trade)
                
                if (i - 100) % 200 == 0:
                    logger.info(f"  [EXIT] {position['direction'].upper()} @ ${exit_price:,.2f} | P&L: ${pnl:,.0f} ({pnl_pct:+.2f}%) | Score: {position['signal_score']:.0f}")
                
                position = None
        
        # Check entry
        if not position:
            signal = strategy.get_signal(symbol, window)
            
            if signal.entry and signal.direction != 'none':
                entry_price = current_close
                atr = strategy.calculate_atr(window, strategy.atr_period, strategy.atr_smooth).iloc[-1]
                
                # Position sizing: 0.65% risk per trade
                risk_amount = equity * (strategy.risk_per_trade / 100)
                stop_distance = atr * signal.stop_multiplier
                quantity = risk_amount / stop_distance if stop_distance > 0 else 0
                
                # Cap exposure at 12%
                max_quantity = (equity * (strategy.max_exposure / 100)) / entry_price
                quantity = min(quantity, max_quantity)
                
                if quantity > 0.001:  # Only enter if meaningful position
                    position = {
                        'entry': entry_price,
                        'entry_date': df.iloc[i]['timestamp'],
                        'quantity': quantity,
                        'direction': signal.direction,
                        'signal_score': signal.score,
                        'regime': signal.regime,
                        'atr': atr,
                        'target': entry_price + (atr * signal.target_multiplier) if signal.direction == 'long' else entry_price - (atr * signal.target_multiplier),
                        'stop': entry_price - (atr * signal.stop_multiplier) if signal.direction == 'long' else entry_price + (atr * signal.stop_multiplier)
                    }
                    
                    if (i - 100) % 200 == 0:
                        logger.info(f"  [ENTRY] {signal.direction.upper()} @ ${entry_price:,.2f} | Qty: {quantity:.4f} | Score: {signal.score:.0f} | Regime: {signal.regime}")
        
        # Update max equity for drawdown calculation
        if equity > max_equity:
            max_equity = equity
    
    # Close any open position at end
    if position:
        exit_price = df.iloc[-1]['close']
        if position['direction'] == 'long':
            pnl = (exit_price - position['entry']) * position['quantity']
        else:  # short
            pnl = (position['entry'] - exit_price) * position['quantity']
        
        pnl_pct = (pnl / (position['entry'] * position['quantity'])) * 100
        equity += pnl
        
        trade = {
            'entry_date': position['entry_date'],
            'exit_date': df.iloc[-1]['timestamp'],
            'entry_price': position['entry'],
            'exit_price': exit_price,
            'quantity': position['quantity'],
            'direction': position['direction'],
            'pnl': pnl,
            'pnl_pct': pnl_pct,
            'exit_reason': 'end_of_backtest',
            'signal_score': position['signal_score'],
            'regime': position['regime']
        }
        trades.append(trade)
    
    # Calculate metrics
    result = {
        'symbol': symbol,
        'trades': trades,
        'equity': equity,
        'return_pct': (equity / initial_capital - 1) * 100,
        'num_trades': len(trades),
        'initial_capital': initial_capital,
    }
    
    if trades:
        trades_df = pd.DataFrame(trades)
        
        # Win rate
        wins = trades_df[trades_df['pnl'] > 0]
        result['win_rate'] = len(wins) / len(trades) * 100 if len(trades) > 0 else 0
        result['num_wins'] = len(wins)
        result['num_losses'] = len(trades) - len(wins)
        
        # Averages
        result['avg_win'] = wins['pnl'].mean() if len(wins) > 0 else 0
        result['avg_loss'] = trades_df[trades_df['pnl'] <= 0]['pnl'].mean() if len(trades_df[trades_df['pnl'] <= 0]) > 0 else 0
        result['profit_factor'] = abs(wins['pnl'].sum() / trades_df[trades_df['pnl'] < 0]['pnl'].sum()) if len(trades_df[trades_df['pnl'] < 0]) > 0 else 0
        
        # Max drawdown
        equity_curve = [initial_capital]
        for trade in trades:
            equity_curve.append(equity_curve[-1] + trade['pnl'])
        
        result['max_drawdown'] = calculate_max_drawdown(equity_curve)
        result['largest_win'] = wins['pnl'].max() if len(wins) > 0 else 0
        result['largest_loss'] = trades_df[trades_df['pnl'] < 0]['pnl'].min() if len(trades_df[trades_df['pnl'] < 0]) > 0 else 0
    else:
        result['win_rate'] = 0
        result['num_wins'] = 0
        result['num_losses'] = 0
        result['avg_win'] = 0
        result['avg_loss'] = 0
        result['profit_factor'] = 0
        result['max_drawdown'] = 0
        result['largest_win'] = 0
        result['largest_loss'] = 0
    
    logger.info(f"  [RESULT] Trades: {len(trades)} | Return: {result['return_pct']:+.2f}% | Win Rate: {result['win_rate']:.1f}% | Max DD: {result['max_drawdown']:.2f}%")
    return result


def calculate_max_drawdown(equity_curve):
    """Calculate maximum drawdown"""
    if len(equity_curve) < 2:
        return 0
    cumax = np.maximum.accumulate(equity_curve)
    drawdown = (np.array(equity_curve) - cumax) / cumax
    return abs(drawdown.min()) * 100


def main():
    logger.info("=" * 80)
    logger.info("CRYPTOFLUX DYNAMO BACKTEST")
    logger.info("=" * 80)
    
    pairs = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'XRP/USDT']
    results = []
    
    for symbol in pairs:
        try:
            # Download data (last 60 days)
            df = fetch_binance_data(symbol, timeframe='30m', days=60)
            
            if df is None or len(df) < 100:
                logger.warning(f"[SKIP] {symbol}: Insufficient data")
                continue
            
            # Run backtest
            result = run_backtest(symbol, df)
            results.append(result)
            
        except Exception as e:
            logger.error(f"[ERROR] {symbol}: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            continue
    
    # Aggregate results
    logger.info("\n" + "=" * 80)
    logger.info("SUMMARY - ALL PAIRS (60 DAYS)")
    logger.info("=" * 80)
    
    if results:
        summary_df = pd.DataFrame([{
            'Symbol': r['symbol'],
            'Trades': r['num_trades'],
            'Wins': r['num_wins'],
            'Losses': r['num_losses'],
            'Win %': f"{r['win_rate']:.1f}%",
            'Return %': f"{r['return_pct']:+.2f}%",
            'Profit Factor': f"{r['profit_factor']:.2f}",
            'Max DD %': f"{r['max_drawdown']:.2f}%",
            'Avg Win': f"${r['avg_win']:,.0f}",
            'Avg Loss': f"${r['avg_loss']:,.0f}",
            'Final $': f"${r['equity']:,.0f}"
        } for r in results])
        
        logger.info("\n" + summary_df.to_string(index=False))
        
        total_return = sum(r['return_pct'] for r in results) / len(results)
        avg_win_rate = sum(r['win_rate'] for r in results) / len(results)
        total_trades = sum(r['num_trades'] for r in results)
        total_wins = sum(r['num_wins'] for r in results)
        
        logger.info("\n" + "=" * 80)
        logger.info("AGGREGATE STATISTICS")
        logger.info("=" * 80)
        logger.info(f"Total Trades: {total_trades} ({total_wins} wins)")
        logger.info(f"Average Win Rate: {avg_win_rate:.1f}%")
        logger.info(f"Average Return: {total_return:+.2f}%")
        logger.info(f"\n[SUCCESS] Backtest complete!")
    else:
        logger.error("[ERROR] No successful backtests")
    
    logger.info("=" * 80)


if __name__ == '__main__':
    main()
