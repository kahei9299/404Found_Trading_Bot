"""
CryptoFlux Dynamo Strategy [JOAT]
Momentum-based scalping strategy with regime-adaptive signal filtering
Ported from TradingView Pine Script to Python

Key Components:
- ATR-based volatility regime classification (Compression/Expansion/Velocity)
- EMA ribbon trend detection (8/21/34)
- Adaptive MACD with momentum confirmation
- RSI + MFI dual confirmation
- Bollinger Bands + Keltner Channels squeeze detection
- Volume impulse filtering
- Composite scoring system (55+ points to enter)
- Regime-adaptive stops and targets
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass


@dataclass
class CryptoFluxSignal:
    """Signal output from the strategy"""
    entry: bool
    direction: str  # 'long', 'short', or 'none'
    score: float  # Composite signal strength (0-100)
    regime: str  # Current volatility regime
    stop_multiplier: float
    target_multiplier: float
    confidence: str  # 'weak', 'medium', 'strong'


class CryptoFluxDynamo:
    """
    CryptoFlux Dynamo momentum-based scalping strategy
    Designed for 5-minute BTC/ETH perpetuals
    """
    
    def __init__(self,
                 min_signal_strength: float = 55.0,
                 risk_per_trade: float = 0.65,
                 max_exposure: float = 12.0,
                 enable_btc_dominance: bool = False):
        """
        Initialize CryptoFlux Dynamo strategy
        
        Args:
            min_signal_strength: Minimum composite score to enter (default: 55)
            risk_per_trade: Risk % per trade (default: 0.65%)
            max_exposure: Maximum exposure % (default: 12%)
            enable_btc_dominance: Use BTC.D filter (default: False)
        """
        # Configuration
        self.min_signal_strength = min_signal_strength
        self.risk_per_trade = risk_per_trade
        self.max_exposure = max_exposure
        self.enable_btc_dominance = enable_btc_dominance
        
        # Regime thresholds (ATR as % of price)
        self.compression_threshold = 0.008  # < 0.8%
        self.expansion_threshold = 0.016    # 0.8% - 1.6%
        # > 1.6% = Velocity
        
        # EMA periods
        self.ema_fast = 8
        self.ema_mid = 21
        self.ema_slow = 34
        
        # MACD periods
        self.macd_fast = 8
        self.macd_slow = 21
        self.macd_signal = 5
        
        # Other indicator periods
        self.atr_period = 21
        self.atr_smooth = 13
        self.rsi_period = 21
        self.mfi_period = 21
        self.bb_period = 20
        self.bb_mult = 1.5
        self.kc_period = 20
        self.kc_mult = 1.8
        
        # Signal parameters
        self.rsi_trigger = 55  # For longs
        self.mfi_trigger = 55  # For longs
        self.macd_sensitivity = 1.15
        self.structure_lookback = 10
        self.volume_impulse_mult = 1.15
        self.cycle_period = 55
        self.cycle_threshold = 0.0015  # 0.15%
        
    def calculate_atr(self, df: pd.DataFrame, period: int = 14, smooth: int = 13) -> pd.Series:
        """Calculate ATR with smoothing"""
        high = df['high'].values
        low = df['low'].values
        close = df['close'].values
        
        tr = np.maximum(
            high - low,
            np.maximum(
                np.abs(high - np.roll(close, 1)),
                np.abs(low - np.roll(close, 1))
            )
        )
        
        atr = pd.Series(tr).rolling(window=period).mean()
        atr_smooth = atr.ewm(span=smooth).mean()
        return atr_smooth
    
    def get_volatility_regime(self, df: pd.DataFrame) -> Tuple[str, float]:
        """
        Classify volatility regime using normalized ATR
        Returns: (regime_name, atr_pct)
        """
        atr = self.calculate_atr(df, self.atr_period, self.atr_smooth)
        close = df['close'].values
        atr_pct = atr.iloc[-1] / close[-1] if close[-1] > 0 else 0
        
        if atr_pct < self.compression_threshold:
            return 'compression', atr_pct
        elif atr_pct < self.expansion_threshold:
            return 'expansion', atr_pct
        else:
            return 'velocity', atr_pct
    
    def calculate_ema_ribbon(self, df: pd.DataFrame) -> Tuple[float, float, float, float]:
        """
        Calculate EMA ribbon (8/21/34)
        Returns: (ema_8, ema_21, ema_34, ema_21_slope_degrees)
        """
        close = df['close'].values
        
        ema_8 = pd.Series(close).ewm(span=self.ema_fast).mean().iloc[-1]
        ema_21 = pd.Series(close).ewm(span=self.ema_mid).mean().iloc[-1]
        ema_34 = pd.Series(close).ewm(span=self.ema_slow).mean().iloc[-1]
        
        # Calculate slope of EMA 21 over last 8 bars
        ema_21_series = pd.Series(close).ewm(span=self.ema_mid).mean()
        if len(ema_21_series) >= 8:
            slope = ema_21_series.iloc[-1] - ema_21_series.iloc[-8]
            slope_degrees = np.degrees(np.arctan(slope / (ema_21_series.iloc[-1] + 1e-10)))
        else:
            slope_degrees = 0
        
        return ema_8, ema_21, ema_34, slope_degrees
    
    def calculate_macd(self, df: pd.DataFrame) -> Tuple[float, float, float]:
        """
        Calculate MACD with adaptive baseline
        Returns: (macd_line, signal_line, histogram)
        """
        close = df['close'].values
        
        # Calculate MACD
        ema_fast = pd.Series(close).ewm(span=self.macd_fast).mean()
        ema_slow = pd.Series(close).ewm(span=self.macd_slow).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=self.macd_signal).mean()
        histogram = macd_line - signal_line
        
        # Smooth histogram
        histogram_smooth = histogram.ewm(span=3).mean()
        
        return macd_line.iloc[-1], signal_line.iloc[-1], histogram_smooth.iloc[-1]
    
    def calculate_rsi(self, df: pd.DataFrame, period: int = 14) -> float:
        """Calculate RSI"""
        close = df['close'].values
        deltas = np.diff(close)
        
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        avg_gain = pd.Series(gains).rolling(window=period).mean()
        avg_loss = pd.Series(losses).rolling(window=period).mean()
        
        rs = avg_gain / (avg_loss + 1e-10)
        rsi = 100 - (100 / (1 + rs))
        
        return rsi.iloc[-1]
    
    def calculate_mfi(self, df: pd.DataFrame, period: int = 14) -> float:
        """Calculate Money Flow Index"""
        high = df['high'].values
        low = df['low'].values
        close = df['close'].values
        volume = df['volume'].values
        
        # Typical price
        tp = (high + low + close) / 3
        
        # Money flow
        mf = tp * volume
        
        # Positive and negative money flow
        positive_mf = np.where(tp > np.roll(tp, 1), mf, 0)
        negative_mf = np.where(tp < np.roll(tp, 1), mf, 0)
        
        pmf = pd.Series(positive_mf).rolling(window=period).sum()
        nmf = pd.Series(negative_mf).rolling(window=period).sum()
        
        mfr = pmf / (nmf + 1e-10)
        mfi = 100 - (100 / (1 + mfr))
        
        return mfi.iloc[-1]
    
    def calculate_bollinger_bands(self, df: pd.DataFrame, period: int = 20, mult: float = 1.5) -> Tuple[float, float, float]:
        """Calculate Bollinger Bands"""
        close = df['close'].values
        
        sma = pd.Series(close).rolling(window=period).mean()
        std = pd.Series(close).rolling(window=period).std()
        
        upper = sma + (std * mult)
        lower = sma - (std * mult)
        
        return upper.iloc[-1], sma.iloc[-1], lower.iloc[-1]
    
    def calculate_keltner_channels(self, df: pd.DataFrame, period: int = 20, mult: float = 1.8) -> Tuple[float, float, float]:
        """Calculate Keltner Channels"""
        high = df['high'].values
        low = df['low'].values
        close = df['close'].values
        
        # Central line (EMA)
        hl_avg = (high + low) / 2
        center = pd.Series(hl_avg).ewm(span=period).mean()
        
        # ATR for width
        tr = np.maximum(
            high - low,
            np.maximum(
                np.abs(high - np.roll(close, 1)),
                np.abs(low - np.roll(close, 1))
            )
        )
        atr = pd.Series(tr).rolling(window=period).mean()
        
        upper = center + (atr * mult)
        lower = center - (atr * mult)
        
        return upper.iloc[-1], center.iloc[-1], lower.iloc[-1]
    
    def detect_squeeze(self, df: pd.DataFrame) -> bool:
        """
        Detect Bollinger Bands inside Keltner Channels (squeeze)
        """
        bb_upper, bb_mid, bb_lower = self.calculate_bollinger_bands(df, self.bb_period, self.bb_mult)
        kc_upper, kc_mid, kc_lower = self.calculate_keltner_channels(df, self.kc_period, self.kc_mult)
        
        # Squeeze when BB is inside KC
        squeeze = (bb_upper < kc_upper) and (bb_lower > kc_lower)
        return squeeze
    
    def detect_volume_impulse(self, df: pd.DataFrame) -> Tuple[bool, float]:
        """
        Detect volume impulse (volume spike)
        Returns: (has_impulse, volume_zscore)
        """
        volume = df['volume'].values
        
        vol_baseline = pd.Series(volume).rolling(window=34).mean()
        vol_std = pd.Series(volume).rolling(window=34).std()
        vol_zscore = (volume[-1] - vol_baseline.iloc[-1]) / (vol_std.iloc[-1] + 1e-10)
        
        has_impulse = (volume[-1] > vol_baseline.iloc[-1] * self.volume_impulse_mult) or (vol_zscore > 0.5)
        
        return has_impulse, vol_zscore
    
    def calculate_cycle_oscillator(self, df: pd.DataFrame) -> Tuple[float, str]:
        """
        Calculate cycle oscillator (price deviation from 55-period EMA)
        Returns: (cycle_deviation_pct, cycle_bias)
        """
        close = df['close'].values
        ema_55 = pd.Series(close).ewm(span=self.cycle_period).mean()
        
        deviation = (close[-1] - ema_55.iloc[-1]) / ema_55.iloc[-1]
        
        # More lenient thresholds: 0.05% instead of 0.15%
        if deviation > 0.0005:  # 0.05%
            return deviation, 'bullish'
        elif deviation < -0.0005:  # -0.05%
            return deviation, 'bearish'
        else:
            return deviation, 'neutral'
    
    def get_signal(self, symbol: str, df: pd.DataFrame) -> CryptoFluxSignal:
        """
        Generate CryptoFlux Dynamo signal
        Main entry point for strategy logic
        """
        if len(df) < self.ema_slow + 20:
            return CryptoFluxSignal(entry=False, direction='none', score=0, 
                                   regime='unknown', stop_multiplier=1.0, 
                                   target_multiplier=1.0, confidence='weak')
        
        # 1. Regime classification
        regime, atr_pct = self.get_volatility_regime(df)
        
        # 2. Calculate all indicators
        ema_8, ema_21, ema_34, ema_slope = self.calculate_ema_ribbon(df)
        macd_line, signal_line, histogram = self.calculate_macd(df)
        rsi = self.calculate_rsi(df, self.rsi_period)
        mfi = self.calculate_mfi(df, self.mfi_period)
        has_squeeze = self.detect_squeeze(df)
        has_volume_impulse, vol_zscore = self.detect_volume_impulse(df)
        cycle_dev, cycle_bias = self.calculate_cycle_oscillator(df)
        bb_upper, bb_mid, bb_lower = self.calculate_bollinger_bands(df, self.bb_period, self.bb_mult)
        kc_upper, kc_mid, kc_lower = self.calculate_keltner_channels(df, self.kc_period, self.kc_mult)
        
        atr = self.calculate_atr(df, self.atr_period, self.atr_smooth).iloc[-1]
        high_5 = df['high'].iloc[-self.structure_lookback:].max()
        low_5 = df['low'].iloc[-self.structure_lookback:].min()
        close = df['close'].values[-1]
        
        # 3. Signal pathway scoring
        score = 0
        direction = 'none'
        
        # Trend Structure (EMA Ribbon)
        bullish_ribbon = (ema_8 > ema_21 > ema_34)
        bearish_ribbon = (ema_8 < ema_21 < ema_34)
        
        # **LONG SIGNAL PATHWAYS**
        if bullish_ribbon:
            # Trend Break Pathway (20 points) - slightly relaxed
            if close > high_5 or ema_slope > 3:
                score += 20
            
            # Momentum Surge Pathway (25 points) - relaxed to OR logic
            if histogram > 0 or (macd_line > signal_line and rsi > 50 and mfi > 50):
                score += 25
            
            # Squeeze Release Pathway (20 points) - simplified
            if not has_squeeze:
                score += 20
            
            # EMA Ribbon itself (15 points) - reward for alignment
            if bullish_ribbon:
                score += 15
            
            # Volume & Regime Modifiers
            if has_volume_impulse:
                score += 5
            
            if regime == 'velocity':
                score += 8
            elif regime == 'expansion':
                score += 3
            
            if cycle_bias == 'bullish':
                score += 5
            
            direction = 'long'
        
        # SHORT SELLING DISABLED - Competition rules prohibit short selling
        # (Roostoo only allows spot trading, no leverage or shorting)
        else:
            direction = 'none'  # No short signals - long only strategy
        
        # Clamp score to 0-100
        score = max(0, min(100, score))
        
        # 4. Determine confidence level
        if score >= 75:
            confidence = 'strong'
        elif score >= 55:
            confidence = 'medium'
        else:
            confidence = 'weak'
        
        # 5. Regime-specific stop/target multipliers
        stop_mult_map = {'compression': 1.05, 'expansion': 1.55, 'velocity': 2.1}
        target_mult_map = {'compression': 2.6, 'expansion': 3.7, 'velocity': 5.8}
        
        stop_multiplier = stop_mult_map.get(regime, 1.55)
        target_multiplier = target_mult_map.get(regime, 3.7)
        
        # Entry decision
        # Removed strict cycle_bias requirement - allows more trading opportunities
        entry = (score >= self.min_signal_strength and direction != 'none')
        
        return CryptoFluxSignal(
            entry=entry,
            direction=direction,
            score=score,
            regime=regime,
            stop_multiplier=stop_multiplier,
            target_multiplier=target_multiplier,
            confidence=confidence
        )
    
    def check_exit(self, df: pd.DataFrame, position_direction: str) -> Tuple[bool, str]:
        """
        Check exit conditions (momentum fail-safe)
        """
        if len(df) < 5:
            return False, "insufficient_data"
        
        macd_line, signal_line, histogram = self.calculate_macd(df)
        ema_8, ema_21, ema_34, _ = self.calculate_ema_ribbon(df)
        
        # Long exits
        if position_direction == 'long':
            if histogram < 0:
                return True, "macd_reversal"
            if ema_8 < ema_21:
                return True, "ribbon_break"
        
        # Short exits
        elif position_direction == 'short':
            if histogram > 0:
                return True, "macd_reversal"
            if ema_8 > ema_21:
                return True, "ribbon_break"
        
        return False, "no_exit"
