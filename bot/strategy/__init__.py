"""
Strategy Module
CryptoFlux Dynamo - momentum-based trading strategy for the Roostoo trading bot
"""

from .strategy import StrategyManager
from .cryptoflux import CryptoFluxDynamo

__all__ = [
    'CryptoFluxDynamo',
    'StrategyManager'
]
