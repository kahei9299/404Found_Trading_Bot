"""
Market Data Module
Handles OHLCV data fetching and caching from Roostoo exchange
"""

import pandas as pd
import numpy as np
import ccxt
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class MarketData:
    """Manages market data fetching and caching from Roostoo exchange"""
    
    def __init__(self, exchange_id: str = 'binance', timeframe: str = '30m'):
        """
        Initialize market data handler.
        
        Args:
            exchange_id: Exchange to use (default: binance via ccxt proxy)
            timeframe: Candlestick timeframe (default: 30m)
        """
        self.timeframe = timeframe
        self.exchange_id = exchange_id
        
        # Initialize exchange
        try:
            self.exchange = getattr(ccxt, exchange_id)()
            logger.info(f"[SUCCESS] Initialized {exchange_id} exchange")
        except Exception as e:
            logger.error(f"❌ Failed to initialize exchange: {e}")
            raise
        
        # Data cache: {symbol: DataFrame}
        self.data_cache: Dict[str, pd.DataFrame] = {}
        self.last_update: Dict[str, datetime] = {}
        self.cache_ttl_seconds = 60  # Refresh cache every 60 seconds
    
    def fetch_ohlcv(self, 
                    symbol: str, 
                    limit: int = 100,
                    force_refresh: bool = False) -> Optional[pd.DataFrame]:
        """
        Fetch OHLCV data for a symbol.
        
        Args:
            symbol: Trading pair (e.g., 'BTC/USDT')
            limit: Number of candles to fetch (default: 100)
            force_refresh: Ignore cache and fetch fresh data
            
        Returns:
            DataFrame with columns [timestamp, open, high, low, close, volume]
            or None if fetch fails
        """
        try:
            # Check cache first
            if not force_refresh and symbol in self.data_cache:
                if self._is_cache_valid(symbol):
                    logger.debug(f"📦 Using cached data for {symbol}")
                    return self.data_cache[symbol].copy()
            
            logger.info(f"[FETCH] Fetching OHLCV for {symbol}...")
            
            # Fetch from exchange
            ohlcv_data = self.exchange.fetch_ohlcv(symbol, self.timeframe, limit=limit)
            
            if not ohlcv_data:
                logger.warning(f"⚠️  No data received for {symbol}")
                return None
            
            # Convert to DataFrame
            df = pd.DataFrame(
                ohlcv_data,
                columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
            )
            
            # Convert timestamp to datetime
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df = df.sort_values('timestamp').reset_index(drop=True)
            
            # Cache it
            self.data_cache[symbol] = df.copy()
            self.last_update[symbol] = datetime.utcnow()
            
            logger.info(f"[SUCCESS] Fetched {len(df)} candles for {symbol}")
            return df
            
        except Exception as e:
            logger.error(f"❌ Error fetching {symbol}: {str(e)[:100]}")
            # Return cached data if available, even if stale
            if symbol in self.data_cache:
                logger.warning(f"⚠️  Returning stale cached data for {symbol}")
                return self.data_cache[symbol].copy()
            return None
    
    def fetch_multiple(self, 
                      symbols: List[str], 
                      limit: int = 100) -> Dict[str, Optional[pd.DataFrame]]:
        """
        Fetch OHLCV data for multiple symbols.
        
        Args:
            symbols: List of trading pairs
            limit: Number of candles per pair
            
        Returns:
            Dict mapping symbol -> DataFrame
        """
        results = {}
        for symbol in symbols:
            results[symbol] = self.fetch_ohlcv(symbol, limit=limit)
        return results
    
    def _is_cache_valid(self, symbol: str) -> bool:
        """Check if cached data is still fresh"""
        if symbol not in self.last_update:
            return False
        
        age_seconds = (datetime.utcnow() - self.last_update[symbol]).total_seconds()
        return age_seconds < self.cache_ttl_seconds
    
    def clear_cache(self, symbol: Optional[str] = None):
        """
        Clear cache for a symbol or all symbols.
        
        Args:
            symbol: Specific symbol to clear, or None to clear all
        """
        if symbol:
            if symbol in self.data_cache:
                del self.data_cache[symbol]
                del self.last_update[symbol]
                logger.info(f"[CLEAR] Cleared cache for {symbol}")
        else:
            self.data_cache.clear()
            self.last_update.clear()
            logger.info(f"[CLEAR] Cleared all cached data")
    
    def get_latest_price(self, symbol: str) -> Optional[float]:
        """Get latest close price for a symbol"""
        df = self.fetch_ohlcv(symbol, limit=1)
        if df is not None and len(df) > 0:
            return df.iloc[-1]['close']
        return None
    
    def get_latest_candle(self, symbol: str) -> Optional[pd.Series]:
        """Get the latest complete candle"""
        df = self.fetch_ohlcv(symbol, limit=1)
        if df is not None and len(df) > 0:
            return df.iloc[-1]
        return None
    
    def get_ohlcv_range(self, 
                       symbol: str, 
                       lookback_bars: int = 50) -> Optional[pd.DataFrame]:
        """
        Get OHLCV data for the last N bars.
        
        Args:
            symbol: Trading pair
            lookback_bars: Number of bars to retrieve
            
        Returns:
            DataFrame with last N candles
        """
        df = self.fetch_ohlcv(symbol, limit=max(lookback_bars, 100))
        if df is not None:
            return df.tail(lookback_bars).reset_index(drop=True)
        return None


class RealTimeDataBuffer:
    """
    Buffers real-time OHLCV data for strategy processing.
    Maintains rolling window of recent candles per symbol.
    """
    
    def __init__(self, lookback_bars: int = 50):
        """
        Initialize data buffer.
        
        Args:
            lookback_bars: Number of recent bars to maintain
        """
        self.lookback_bars = lookback_bars
        self.buffers: Dict[str, pd.DataFrame] = {}
    
    def update(self, symbol: str, df: pd.DataFrame):
        """
        Update buffer with new OHLCV data.
        
        Args:
            symbol: Trading pair
            df: DataFrame with new candles
        """
        if symbol not in self.buffers or self.buffers[symbol] is None:
            self.buffers[symbol] = df.tail(self.lookback_bars).copy()
        else:
            # Combine and keep only latest lookback_bars
            combined = pd.concat([self.buffers[symbol], df], ignore_index=True)
            combined = combined.drop_duplicates(subset=['timestamp'], keep='last')
            self.buffers[symbol] = combined.tail(self.lookback_bars).reset_index(drop=True)
    
    def get(self, symbol: str) -> Optional[pd.DataFrame]:
        """Get buffered data for a symbol"""
        return self.buffers.get(symbol, None)
    
    def get_all(self) -> Dict[str, pd.DataFrame]:
        """Get all buffered data"""
        return self.buffers.copy()
