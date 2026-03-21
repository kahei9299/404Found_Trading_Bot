"""
Backtest Module
Backtesting framework for trading strategies
"""

from .backtest_simple import (
    generate_mock_ohlcv,
    calculate_atr,
    calculate_strategy_signals,
    backtest_strategy,
    calculate_metrics,
    create_visualizations
)

__all__ = [
    'generate_mock_ohlcv',
    'calculate_atr',
    'calculate_strategy_signals',
    'backtest_strategy',
    'calculate_metrics',
    'create_visualizations'
]
