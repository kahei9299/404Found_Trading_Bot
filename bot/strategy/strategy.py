"""
CryptoFlux Dynamo Strategy
High-confidence momentum-based trading strategy for cryptocurrency pairs.
Enforces competition constraints: max 10 trades/day, no short selling, long-only.
"""

import pandas as pd
from typing import Dict, Optional
from .cryptoflux import CryptoFluxDynamo


class StrategyManager:
    """Manages CryptoFlux Dynamo strategy instances for different pairs."""
    
    def __init__(self):
        self.strategies: Dict[str, CryptoFluxDynamo] = {}
        self.positions: Dict[str, Dict] = {}
    
    def add_pair(self, symbol: str) -> CryptoFluxDynamo:
        """Add a new trading pair with CryptoFlux Dynamo instance."""
        if symbol not in self.strategies:
            # Use strict signal threshold (50.0) to comply with competition constraints:
            # - max 10 trades per day limit (Roostoo rules)
            # - This threshold generates ~2.77 trades/day (well within limit)
            # - Previous threshold of 20.0 generated 31 trades/day (violation)
            # - Backtest shows: 166 trades over 60 days, +0.79% return with strict threshold
            self.strategies[symbol] = CryptoFluxDynamo(min_signal_strength=50.0)
            self.positions[symbol] = None
        return self.strategies[symbol]
    
    def get_signal(self, symbol: str, df: pd.DataFrame) -> Dict:
        """Get trading signal from CryptoFlux Dynamo."""
        if symbol not in self.strategies:
            self.add_pair(symbol)
        
        strategy = self.strategies[symbol]
        signal = strategy.get_signal(symbol, df)
        
        # Convert CryptoFluxSignal to dict format for compatibility
        return {
            'entry': signal.entry,
            'direction': signal.direction,
            'score': signal.score,
            'regime': signal.regime,
            'stop_multiplier': signal.stop_multiplier,
            'target_multiplier': signal.target_multiplier,
            'confidence': signal.confidence
        }
    
    def update_position(self, symbol: str, position: Dict):
        """Update position for a pair."""
        self.positions[symbol] = position
    
    def get_position(self, symbol: str) -> Optional[Dict]:
        """Get current position for a pair."""
        return self.positions.get(symbol)
    
    def close_position(self, symbol: str):
        """Close position for a pair."""
        self.positions[symbol] = None
        if symbol in self.strategies:
            self.strategies[symbol].reset_position()
