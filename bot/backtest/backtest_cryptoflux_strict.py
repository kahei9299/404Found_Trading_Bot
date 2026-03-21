"""
Stricter CryptoFlux Backtest - High-Confidence Signals Only
Enforces daily trade limit: max 10 trades/day
Targets: ~300 trades in 60 days, higher win rate
"""

import logging
import sys
import ccxt
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

# Setup logging
log_dir = Path('bot/logs')
log_dir.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[
        logging.FileHandler('bot/logs/backtest_cryptoflux_strict.log', mode='w'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

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


def run_backtest_strict(symbol: str, df: pd.DataFrame, initial_capital: float = 1000000) -> dict:
    """Run STRICT CryptoFlux backtest with high-confidence signals only"""
    logger.info(f"\n[START] Backtest: {symbol} (STRICT MODE)")
    logger.info(f"  Period: {df['timestamp'].min().date()} to {df['timestamp'].max().date()}")
    logger.info(f"  Candles: {len(df)}")
    
    # STRICTNESS SETTINGS:
    strategy = CryptoFluxDynamo(min_signal_strength=50.0)  # Increased from 20.0 to 50.0
    
    trades = []
    position = None
    equity = initial_capital
    max_equity = initial_capital
    daily_trades = defaultdict(int)  # Track trades per day
    
    for i in range(100, len(df)):
        window = df.iloc[max(0, i-100):i+1]
        current_close = df.iloc[i]['close']
        current_date = df.iloc[i]['timestamp'].date()
        
        # Check daily trade limit (10 per day maximum)
        if daily_trades[current_date] >= 10:
            continue
        
        # Check exit
        if position:
            should_exit, exit_reason = strategy.check_exit(window, position['direction'])
            
            if should_exit:
                exit_price = current_close
                if position['direction'] == 'long':
                    pnl = (exit_price - position['entry']) * position['quantity']
                else:  # should never happen (shorts disabled)
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
                    'signal_score': position['signal_score'],
                    'regime': position['regime']
                }
                trades.append(trade)
                position = None
        
        # Check entry - ONLY HIGH CONFIDENCE SIGNALS
        if not position:
            signal = strategy.get_signal(symbol, window)
            
            # STRICT FILTER #1: Score threshold (50+ instead of 20)
            # STRICT FILTER #2: Only 'strong' or 'medium' confidence
            if (signal.entry and 
                signal.direction == 'long' and 
                signal.confidence in ['strong', 'medium']):
                
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
                        'target': entry_price + (atr * signal.target_multiplier),
                        'stop': entry_price - (atr * signal.stop_multiplier)
                    }
                    
                    daily_trades[current_date] += 1  # Increment daily counter
                    
                    if len(trades) % 50 == 0:
                        logger.info(f"  [ENTRY #{len(trades)+1}] {signal.direction.upper()} @ ${entry_price:,.2f} | "
                                   f"Score: {signal.score:.0f} | Confidence: {signal.confidence} | Regime: {signal.regime}")
        
        # Update max equity for drawdown calculation
        if equity > max_equity:
            max_equity = equity
    
    # Close any open position at end
    if position:
        exit_price = df.iloc[-1]['close']
        pnl = (exit_price - position['entry']) * position['quantity']
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
            'signal_score': position['signal_score'],
            'regime': position['regime']
        }
        trades.append(trade)
    
    # Calculate metrics
    if len(trades) == 0:
        return {
            'symbol': symbol,
            'trades': 0,
            'wins': 0,
            'losses': 0,
            'win_rate': 0,
            'return_pct': 0,
            'profit_factor': 0,
            'max_drawdown': 0,
            'avg_win': 0,
            'avg_loss': 0,
            'final_equity': equity
        }
    
    wins = len([t for t in trades if t['pnl'] > 0])
    losses = len([t for t in trades if t['pnl'] < 0])
    win_rate = (wins / len(trades) * 100) if len(trades) > 0 else 0
    
    total_profit = sum([t['pnl'] for t in trades if t['pnl'] > 0])
    total_loss = sum([abs(t['pnl']) for t in trades if t['pnl'] < 0])
    profit_factor = total_profit / total_loss if total_loss > 0 else 0
    
    max_drawdown = ((min([equity for equity in [initial_capital] + 
                         [initial_capital + sum([t['pnl'] for t in trades[:i+1]]) 
                          for i in range(len(trades))]]) - initial_capital) / initial_capital) * 100
    
    avg_win = total_profit / wins if wins > 0 else 0
    avg_loss = total_loss / losses if losses > 0 else 0
    
    return_pct = ((equity - initial_capital) / initial_capital) * 100
    
    logger.info(f"  [RESULT] Trades: {len(trades)} | Return: {return_pct:+.2f}% | Win Rate: {win_rate:.1f}% | "
               f"Max DD: {max(0, max_drawdown):.2f}%")
    
    return {
        'symbol': symbol,
        'trades': len(trades),
        'wins': wins,
        'losses': losses,
        'win_rate': win_rate,
        'return_pct': return_pct,
        'profit_factor': profit_factor,
        'max_drawdown': max(0, max_drawdown),
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'final_equity': equity
    }


def main():
    symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'XRP/USDT']
    
    logger.info("="*80)
    logger.info("CRYPTOFLUX DYNAMO BACKTEST - STRICT MODE (High-Confidence Signals Only)")
    logger.info("="*80)
    logger.info(f"Configuration:")
    logger.info(f"  - Signal threshold: 50.0 (increased from 20.0)")
    logger.info(f"  - Confidence filter: Only 'strong' or 'medium'")
    logger.info(f"  - Daily trade limit: 10 per day (enforced)")
    logger.info(f"  - Expected trades: ~300 over 60 days")
    logger.info("="*80)
    
    results = []
    
    for symbol in symbols:
        df = fetch_binance_data(symbol, '30m', 60)
        if df is None:
            continue
        
        result = run_backtest_strict(symbol, df)
        results.append(result)
    
    # Summary
    logger.info("\n" + "="*80)
    logger.info("SUMMARY - ALL PAIRS (60 DAYS)")
    logger.info("="*80)
    
    print("\n  Symbol     Trades  Wins  Losses Win %  Return % Profit Factor Max DD %  Avg Win  Avg Loss  Final $")
    for r in results:
        print(f"{r['symbol']:>8}  {r['trades']:>6}  {r['wins']:>4}  {r['losses']:>6}  {r['win_rate']:>5.1f}%  "
              f"{r['return_pct']:>7.2f}%  {r['profit_factor']:>12.2f}  {r['max_drawdown']:>6.2f}%  "
              f"${r['avg_win']:>8,.0f}  ${r['avg_loss']:>8,.0f}  ${r['final_equity']:>12,.0f}")
    
    total_trades = sum([r['trades'] for r in results])
    total_wins = sum([r['wins'] for r in results])
    avg_win_rate = np.mean([r['win_rate'] for r in results])
    avg_return = np.mean([r['return_pct'] for r in results])
    avg_dd = np.mean([r['max_drawdown'] for r in results])
    
    logger.info("\n" + "="*80)
    logger.info("AGGREGATE STATISTICS")
    logger.info("="*80)
    logger.info(f"Total Trades: {total_trades} ({total_wins} wins)")
    logger.info(f"Average Win Rate: {avg_win_rate:.1f}%")
    logger.info(f"Average Return: {avg_return:+.2f}%")
    logger.info(f"Average Max Drawdown: {avg_dd:.2f}%")
    logger.info(f"\n[SUCCESS] Strict backtest complete!")
    logger.info("="*80)


if __name__ == '__main__':
    main()
