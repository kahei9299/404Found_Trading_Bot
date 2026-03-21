"""
404Found Trading Bot
Autonomous cryptocurrency trading bot for Roostoo competition
Uses CryptoFlux Dynamo momentum-based strategy
"""

__version__ = "1.0.0"
__author__ = "404Found Team"

# Package exports
from bot.data import MarketData, Portfolio
from bot.strategy import StrategyManager, CryptoFluxDynamo
from bot.execution import OrderExecutor, OrderManager
from bot.risk import RiskManager, RiskLimits

__all__ = [
    'MarketData',
    'Portfolio',
    'StrategyManager',
    'CryptoFluxDynamo',
    'OrderExecutor',
    'OrderManager',
    'RiskManager',
    'RiskLimits'
]
