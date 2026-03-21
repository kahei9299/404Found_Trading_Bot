"""
Utility Functions Module
Common helper functions used across the bot
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional


def format_currency(value: float, decimals: int = 2) -> str:
    """Format value as currency"""
    return f"${value:,.{decimals}f}"


def format_percent(value: float, decimals: int = 2) -> str:
    """Format value as percentage"""
    sign = '+' if value >= 0 else ''
    return f"{sign}{value:.{decimals}f}%"


def format_volume(value: float) -> str:
    """Format trading volume"""
    for unit in ['', 'K', 'M', 'B']:
        if abs(value) < 1000:
            return f"{value:.2f}{unit}"
        value /= 1000
    return f"{value:.2f}T"


def calculate_position_size(risk_per_trade_pct: float,
                           account_equity: float,
                           stop_distance: float) -> float:
    """
    Calculate position size based on risk.
    
    Args:
        risk_per_trade_pct: Risk per trade as percentage (e.g., 2.0 for 2%)
        account_equity: Current account equity
        stop_distance: Distance to stop loss in currency
        
    Returns:
        Position size (quantity)
    """
    risk_amount = account_equity * (risk_per_trade_pct / 100)
    if stop_distance == 0:
        return 0
    return risk_amount / stop_distance


def calculate_pnl(entry_price: float,
                 exit_price: float,
                 quantity: float,
                 commission_pct: float = 0.001) -> Tuple[float, float]:
    """
    Calculate P&L from a trade.
    
    Args:
        entry_price: Entry price
        exit_price: Exit price
        quantity: Trade quantity
        commission_pct: Commission percentage
        
    Returns:
        (pnl_dollars, pnl_percent)
    """
    gross_pnl = (exit_price - entry_price) * quantity
    commission = (entry_price * quantity * commission_pct) + \
                 (exit_price * quantity * commission_pct)
    net_pnl = gross_pnl - commission
    
    pnl_percent = (exit_price - entry_price) / entry_price if entry_price != 0 else 0
    
    return net_pnl, pnl_percent


def calculate_return_metrics(trades_df: pd.DataFrame,
                            initial_capital: float = 1000000) -> Dict:
    """
    Calculate comprehensive return metrics from trades.
    
    Args:
        trades_df: DataFrame with 'pnl' and 'pnl_pct' columns
        initial_capital: Starting capital
        
    Returns:
        Dict with all metrics
    """
    if len(trades_df) == 0:
        return {
            'total_return': 0,
            'total_return_pct': 0,
            'sharpe_ratio': 0,
            'sortino_ratio': 0,
            'max_drawdown': 0,
            'win_rate': 0,
            'profit_factor': 0,
            'avg_win': 0,
            'avg_loss': 0
        }
    
    returns = trades_df['pnl_pct'].values
    
    # Basic metrics
    total_return = trades_df['pnl'].sum()
    total_return_pct = (total_return / initial_capital) * 100
    
    # Win rate
    winning = (returns > 0).sum()
    losing = (returns < 0).sum()
    win_rate = (winning / len(returns)) * 100 if len(returns) > 0 else 0
    
    # Profit factor
    gross_profit = trades_df[trades_df['pnl'] > 0]['pnl'].sum()
    gross_loss = abs(trades_df[trades_df['pnl'] < 0]['pnl'].sum())
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
    
    # Averages
    avg_win = trades_df[trades_df['pnl'] > 0]['pnl'].mean() if winning > 0 else 0
    avg_loss = trades_df[trades_df['pnl'] < 0]['pnl'].mean() if losing > 0 else 0
    
    # Sharpe Ratio (252 trading days/year)
    sharpe = 0
    if len(returns) > 1 and np.std(returns) > 0:
        sharpe = (np.mean(returns) / np.std(returns)) * np.sqrt(252)
    
    # Sortino Ratio (only downside volatility)
    sortino = 0
    downside_returns = np.minimum(returns, 0)
    if len(downside_returns) > 1 and np.std(downside_returns) > 0:
        sortino = (np.mean(returns) / np.std(downside_returns)) * np.sqrt(252)
    
    # Max Drawdown
    max_drawdown = 0
    if len(trades_df) > 0:
        cumulative = trades_df['pnl'].cumsum()
        running_max = cumulative.expanding().max()
        drawdown = (cumulative - running_max) / running_max
        max_drawdown = drawdown.min() * 100
    
    return {
        'total_return': total_return,
        'total_return_pct': total_return_pct,
        'sharpe_ratio': sharpe,
        'sortino_ratio': sortino,
        'max_drawdown': max_drawdown,
        'win_rate': win_rate,
        'profit_factor': profit_factor,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'total_trades': len(trades_df),
        'winning_trades': int(winning),
        'losing_trades': int(losing)
    }


def get_market_hours(timezone: str = 'UTC') -> Tuple[int, int]:
    """
    Get market trading hours.
    
    Args:
        timezone: Timezone (currently supports 'UTC', 'NY', 'HK')
        
    Returns:
        (market_open_hour, market_close_hour) in 24-hour format
    """
    if timezone == 'NY':
        return (9, 16)  # 9:30 AM - 4:00 PM EST
    elif timezone == 'HK':
        return (9, 16)  # 9:30 AM - 4:00 PM HKT
    else:
        return (0, 24)  # Crypto trades 24/7


def is_market_hours(hour: int, timezone: str = 'UTC') -> bool:
    """Check if current hour is during market hours"""
    open_h, close_h = get_market_hours(timezone)
    return open_h <= hour < close_h


def time_to_next_signal(current_time: datetime,
                       signal_interval_minutes: int = 30) -> int:
    """
    Calculate minutes until next signal based on candlestick interval.
    
    Args:
        current_time: Current time
        signal_interval_minutes: Candlestick interval
        
    Returns:
        Minutes to wait
    """
    minutes_since_hour = current_time.minute
    minutes_in_interval = minutes_since_hour % signal_interval_minutes
    return signal_interval_minutes - minutes_in_interval


def format_trade_summary(trade: Dict) -> str:
    """Format trade summary for logging"""
    return (f"{trade['symbol']:12} | "
            f"Entry: ${trade['entry_price']:10,.2f} | "
            f"Exit: ${trade['exit_price']:10,.2f} | "
            f"PnL: {format_currency(trade['pnl']):>12} "
            f"({format_percent(trade['pnl_pct']*100):>8}) | "
            f"Reason: {trade['exit_reason']}")


def parse_symbol(symbol: str) -> Tuple[str, str]:
    """
    Parse symbol into base and quote asset.
    
    Args:
        symbol: Symbol string (e.g., 'BTC/USDT')
        
    Returns:
        (base_asset, quote_asset) e.g., ('BTC', 'USDT')
    """
    parts = symbol.split('/')
    if len(parts) == 2:
        return parts[0], parts[1]
    return symbol, None


def round_to_tick(price: float, tick_size: float = 0.01) -> float:
    """
    Round price to nearest tick size.
    
    Args:
        price: Price to round
        tick_size: Minimum price increment
        
    Returns:
        Rounded price
    """
    return round(price / tick_size) * tick_size


def get_timestamp_str(dt: Optional[datetime] = None) -> str:
    """Get ISO format timestamp string"""
    if dt is None:
        dt = datetime.utcnow()
    return dt.strftime('%Y-%m-%d %H:%M:%S')


def log_separator(width: int = 70, char: str = '=') -> str:
    """Create a separator line for logging"""
    return char * width
