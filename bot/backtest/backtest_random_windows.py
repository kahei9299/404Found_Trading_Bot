"""
CryptoFlux Backtest - Multiple Random 10-Day Windows
Tests strategy across different market conditions over the past year.
Runs 36 random 10-day windows from 365-day history.
"""

import logging
import sys
import ccxt
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict
import random

# Setup logging
log_dir = Path('bot/logs')
log_dir.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[
        logging.FileHandler('bot/logs/backtest_random_windows.log', mode='w'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

sys.path.insert(0, '.')
from bot.strategy.cryptoflux import CryptoFluxDynamo


def fetch_binance_data(symbol: str, timeframe: str = '30m', days: int = 365) -> pd.DataFrame:
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


def get_random_windows(df: pd.DataFrame, window_days: int = 10, num_windows: int = 36) -> list:
    """Generate random non-overlapping 10-day windows from data"""
    # Approximate candles per day (at 30m intervals: 48 candles/day)
    candles_per_window = window_days * 48
    available_windows = len(df) // candles_per_window
    
    if available_windows < num_windows:
        num_windows = available_windows
        logger.warning(f"[WARNING] Only {available_windows} windows available, reducing from {num_windows}")
    
    # Generate random starting positions
    window_indices = []
    for _ in range(num_windows):
        max_start = len(df) - candles_per_window
        start_idx = random.randint(0, max_start)
        window_indices.append((start_idx, start_idx + candles_per_window))
    
    return window_indices


def run_backtest_window(symbol: str, df_window: pd.DataFrame, initial_capital: float = 1000000) -> dict:
    """Run backtest on single 10-day window"""
    if len(df_window) < 105:  # Need at least 100 candles for indicators
        return {
            'symbol': symbol,
            'period': f"{df_window['timestamp'].min().date()} to {df_window['timestamp'].max().date()}",
            'trades': 0,
            'return_pct': 0,
            'pnl_dollars': 0,
            'final_equity': initial_capital,
            'win_rate': 0,
            'status': 'INSUFFICIENT_DATA'
        }
    
    strategy = CryptoFluxDynamo(min_signal_strength=50.0)
    
    trades = []
    position = None
    equity = initial_capital
    
    for i in range(100, len(df_window)):
        window = df_window.iloc[max(0, i-100):i+1]
        current_close = df_window.iloc[i]['close']
        
        # Check exit
        if position:
            should_exit, _ = strategy.check_exit(window, position['direction'])
            
            if should_exit:
                exit_price = current_close
                pnl = (exit_price - position['entry']) * position['quantity']
                pnl_pct = (pnl / (position['entry'] * position['quantity'])) * 100
                equity += pnl
                
                trade = {
                    'pnl': pnl,
                    'pnl_pct': pnl_pct
                }
                trades.append(trade)
                position = None
        
        # Check entry
        if not position:
            signal = strategy.get_signal(symbol, window)
            
            if signal.entry and signal.direction == 'long' and signal.confidence in ['strong', 'medium']:
                entry_price = current_close
                atr = strategy.calculate_atr(window, strategy.atr_period, strategy.atr_smooth).iloc[-1]
                
                risk_amount = equity * (strategy.risk_per_trade / 100)
                stop_distance = atr * signal.stop_multiplier
                quantity = risk_amount / stop_distance if stop_distance > 0 else 0
                
                max_quantity = (equity * (strategy.max_exposure / 100)) / entry_price
                quantity = min(quantity, max_quantity)
                
                if quantity > 0.001:
                    position = {
                        'entry': entry_price,
                        'quantity': quantity,
                        'direction': signal.direction
                    }
    
    # Close any open position
    if position:
        exit_price = df_window.iloc[-1]['close']
        pnl = (exit_price - position['entry']) * position['quantity']
        pnl_pct = (pnl / (position['entry'] * position['quantity'])) * 100
        equity += pnl
        trades.append({'pnl': pnl, 'pnl_pct': pnl_pct})
    
    # Calculate metrics
    total_pnl = equity - initial_capital
    
    if len(trades) == 0:
        return {
            'symbol': symbol,
            'period': f"{df_window['timestamp'].min().date()} to {df_window['timestamp'].max().date()}",
            'trades': 0,
            'return_pct': 0,
            'pnl_dollars': 0,
            'final_equity': initial_capital,
            'win_rate': 0,
            'status': 'NO_TRADES'
        }
    
    wins = len([t for t in trades if t['pnl'] > 0])
    win_rate = (wins / len(trades) * 100) if len(trades) > 0 else 0
    return_pct = ((equity - initial_capital) / initial_capital) * 100
    
    return {
        'symbol': symbol,
        'period': f"{df_window['timestamp'].min().date()} to {df_window['timestamp'].max().date()}",
        'trades': len(trades),
        'wins': wins,
        'return_pct': return_pct,
        'pnl_dollars': total_pnl,
        'final_equity': equity,
        'win_rate': win_rate,
        'status': 'OK'
    }


def main():
    symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'XRP/USDT']
    num_windows = 36
    
    logger.info("="*90)
    logger.info("CRYPTOFLUX DYNAMO - RANDOM 10-DAY WINDOW BACKTEST")
    logger.info("="*90)
    logger.info(f"Configuration:")
    logger.info(f"  - Testing period: Past 365 days")
    logger.info(f"  - Window size: 10 days")
    logger.info(f"  - Number of windows: {num_windows} (randomly selected, non-overlapping)")
    logger.info(f"  - Signal threshold: 50.0 (strict mode)")
    logger.info(f"  - Symbols: {', '.join(symbols)}")
    logger.info("="*90)
    
    all_results = defaultdict(list)
    
    for symbol in symbols:
        logger.info(f"\n[SYMBOL] {symbol}")
        
        # Fetch 365 days of data
        df = fetch_binance_data(symbol, '30m', 365)
        if df is None:
            logger.error(f"[ERROR] Could not fetch data for {symbol}")
            continue
        
        # Get random windows
        windows = get_random_windows(df, window_days=10, num_windows=num_windows)
        logger.info(f"[INFO] Running {len(windows)} random 10-day windows...")
        
        # Run backtest on each window
        for idx, (start, end) in enumerate(windows, 1):
            df_window = df.iloc[start:end].reset_index(drop=True)
            result = run_backtest_window(symbol, df_window)
            all_results[symbol].append(result)
            
            if idx % 6 == 0:
                logger.info(f"  Progress: {idx}/{len(windows)} windows completed")
        
        logger.info(f"[COMPLETE] {symbol} finished ({len(windows)} windows)")
    
    # Print summary
    logger.info("\n" + "="*90)
    logger.info("DETAILED RESULTS BY SYMBOL")
    logger.info("="*90)
    
    symbol_stats = {}
    for symbol in symbols:
        results = all_results[symbol]
        if not results:
            continue
        
        successful = [r for r in results if r['status'] == 'OK']
        if not successful:
            logger.info(f"\n{symbol}: NO SUCCESSFUL WINDOWS")
            continue
        
        total_trades = sum([r['trades'] for r in successful])
        total_wins = sum([r['wins'] for r in successful if 'wins' in r])
        total_pnl = sum([r['pnl_dollars'] for r in successful])
        avg_return = np.mean([r['return_pct'] for r in successful])
        avg_win_rate = np.mean([r['win_rate'] for r in successful])
        win_count = len([r for r in successful if r['pnl_dollars'] > 0])
        avg_pnl = np.mean([r['pnl_dollars'] for r in successful])
        
        symbol_stats[symbol] = {
            'windows_tested': len(results),
            'successful': len(successful),
            'total_trades': total_trades,
            'total_wins': total_wins,
            'avg_return': avg_return,
            'avg_win_rate': avg_win_rate,
            'profitable_windows': win_count,
            'total_pnl': total_pnl,
            'avg_pnl': avg_pnl
        }
        
        logger.info(f"\n{symbol}:")
        logger.info(f"  Windows tested: {len(results)}")
        logger.info(f"  Successful windows: {len(successful)}")
        logger.info(f"  Total trades across all windows: {total_trades}")
        logger.info(f"  Total wins: {total_wins}")
        logger.info(f"  TOTAL PROFIT (36 windows): ${total_pnl:,.2f}")
        logger.info(f"  Average profit per window: ${avg_pnl:,.2f}")
        logger.info(f"  Average return per window: {avg_return:+.2f}%")
        logger.info(f"  Average win rate: {avg_win_rate:.1f}%")
        logger.info(f"  Profitable windows: {win_count}/{len(successful)} ({win_count/len(successful)*100:.1f}%)")
    
    # Aggregate statistics
    logger.info("\n" + "="*90)
    logger.info("AGGREGATE STATISTICS (ALL SYMBOLS & ALL WINDOWS)")
    logger.info("="*90)
    
    if symbol_stats:
        total_windows = sum([s['windows_tested'] for s in symbol_stats.values()])
        total_successful = sum([s['successful'] for s in symbol_stats.values()])
        total_trades_all = sum([s['total_trades'] for s in symbol_stats.values()])
        total_wins_all = sum([s['total_wins'] for s in symbol_stats.values()])
        total_pnl_all = sum([s['total_pnl'] for s in symbol_stats.values()])
        avg_pnl_all = np.mean([s['avg_pnl'] for s in symbol_stats.values()])
        avg_return_all = np.mean([s['avg_return'] for s in symbol_stats.values()])
        profitable_windows_all = sum([s['profitable_windows'] for s in symbol_stats.values()])
        
        logger.info(f"Total windows tested: {total_windows}")
        logger.info(f"Successful windows: {total_successful}")
        logger.info(f"Total trades: {total_trades_all}")
        logger.info(f"Total wins: {total_wins_all}")
        logger.info(f"\nTOTAL PROFIT (ALL 144 WINDOWS): ${total_pnl_all:,.2f}")
        logger.info(f"Average profit per window: ${avg_pnl_all:,.2f}")
        logger.info(f"\nAverage return per window (all symbols): {avg_return_all:+.2f}%")
        logger.info(f"Profitable windows: {profitable_windows_all}/{total_successful} ({profitable_windows_all/total_successful*100:.1f}%)")
        logger.info(f"Win rate (trades): {(total_wins_all/total_trades_all*100):.1f}%")
        
        logger.info("\n[SUCCESS] Random window backtest complete!")
    
    logger.info("="*90)


if __name__ == '__main__':
    main()
