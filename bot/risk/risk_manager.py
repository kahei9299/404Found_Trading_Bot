"""
Risk Management Module
Enforces risk limits and circuit breakers
"""

from typing import Optional, Dict, List
from datetime import datetime, timedelta
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class RiskLimits:
    """Risk limits configuration"""
    
    max_daily_loss_pct: float = 10.0  # Stop trading if down 10% in a day
    max_daily_trades: int = 10  # Max trades per day
    max_concurrent_positions: int = 4  # Max open positions
    max_position_size_pct: float = 25.0  # Max position size as % of equity
    risk_per_trade_pct: float = 2.0  # Risk per trade as % of equity
    max_account_leverage: float = 1.0  # Max leverage (1.0 = no leverage)
    trading_hours_only: bool = True  # Only trade during market hours


class RiskManager:
    """Enforces risk controls and circuit breakers"""
    
    def __init__(self, limits: Optional[RiskLimits] = None):
        """
        Initialize risk manager.
        
        Args:
            limits: RiskLimits configuration, defaults to RiskLimits()
        """
        self.limits = limits or RiskLimits()
        
        # Tracking
        self.daily_trades: List[Dict] = []
        self.daily_loss = 0.0
        self.daily_reset_time = datetime.utcnow().date()
        
        self.circuit_breaker_active = False
        self.breach_reason = None
    
    def _reset_daily_stats(self):
        """Reset daily statistics if day has changed"""
        today = datetime.utcnow().date()
        if today > self.daily_reset_time:
            self.daily_trades = []
            self.daily_loss = 0.0
            self.daily_reset_time = today
            self.circuit_breaker_active = False
            self.breach_reason = None
            logger.info("📅 Daily stats reset")
    
    def check_can_trade(self, 
                       current_equity: float,
                       initial_equity: float,
                       open_positions_count: int) -> tuple:
        """
        Check if trading is allowed.
        
        Args:
            current_equity: Current account equity
            initial_equity: Starting equity
            open_positions_count: Number of open positions
            
        Returns:
            (allowed: bool, reason: str)
        """
        self._reset_daily_stats()
        
        # Check circuit breaker
        if self.circuit_breaker_active:
            return False, f"Circuit breaker active: {self.breach_reason}"
        
        # Check daily loss limit
        daily_loss_pct = (initial_equity - current_equity) / initial_equity * 100
        if daily_loss_pct > self.limits.max_daily_loss_pct:
            self.circuit_breaker_active = True
            self.breach_reason = f"Daily loss {daily_loss_pct:.2f}% exceeds limit {self.limits.max_daily_loss_pct}%"
            logger.error(f"🛑 {self.breach_reason}")
            return False, self.breach_reason
        
        # Check daily trade count
        if len(self.daily_trades) >= self.limits.max_daily_trades:
            reason = f"Daily trade limit ({self.limits.max_daily_trades}) reached"
            logger.warning(f"⚠️  {reason}")
            return False, reason
        
        # Check concurrent positions
        if open_positions_count >= self.limits.max_concurrent_positions:
            reason = f"Max concurrent positions ({self.limits.max_concurrent_positions}) reached"
            logger.warning(f"⚠️  {reason}")
            return False, reason
        
        return True, "OK"
    
    def check_position_size(self,
                           position_size_usd: float,
                           current_equity: float) -> tuple:
        """
        Check if position size is within limits.
        
        Args:
            position_size_usd: Position size in USD
            current_equity: Current equity
            
        Returns:
            (allowed: bool, reason: str)
        """
        position_size_pct = (position_size_usd / current_equity) * 100 if current_equity > 0 else 0
        
        if position_size_pct > self.limits.max_position_size_pct:
            reason = f"Position size {position_size_pct:.1f}% exceeds limit {self.limits.max_position_size_pct}%"
            logger.warning(f"⚠️  {reason}")
            return False, reason
        
        return True, "OK"
    
    def record_trade(self, symbol: str, pnl: float, quantity: float):
        """
        Record a closed trade.
        
        Args:
            symbol: Trading pair
            pnl: Profit/loss from trade
            quantity: Trade quantity
        """
        self._reset_daily_stats()
        
        self.daily_trades.append({
            'symbol': symbol,
            'pnl': pnl,
            'quantity': quantity,
            'timestamp': datetime.utcnow()
        })
        
        if pnl < 0:
            self.daily_loss += abs(pnl)
        
        logger.debug(f"📊 Trade recorded: {symbol} {pnl:+,.0f}")
    
    def check_risk_per_trade(self,
                            risk_amount: float,
                            account_equity: float) -> tuple:
        """
        Check if risk per trade is within limits.
        
        Args:
            risk_amount: Amount at risk in this trade
            account_equity: Current account equity
            
        Returns:
            (allowed: bool, reason: str)
        """
        risk_pct = (risk_amount / account_equity) * 100 if account_equity > 0 else 0
        
        if risk_pct > self.limits.risk_per_trade_pct:
            reason = f"Trade risk {risk_pct:.2f}% exceeds limit {self.limits.risk_per_trade_pct}%"
            logger.warning(f"⚠️  {reason}")
            return False, reason
        
        return True, "OK"
    
    def check_leverage(self, total_position_value: float, account_equity: float) -> tuple:
        """
        Check if account leverage is within limits.
        
        Args:
            total_position_value: Sum of all open position values
            account_equity: Current account equity
            
        Returns:
            (allowed: bool, reason: str)
        """
        if account_equity == 0:
            return False, "Invalid account equity"
        
        leverage = total_position_value / account_equity
        
        if leverage > self.limits.max_account_leverage:
            reason = f"Leverage {leverage:.2f}x exceeds limit {self.limits.max_account_leverage}x"
            logger.warning(f"⚠️  {reason}")
            return False, reason
        
        return True, "OK"
    
    def get_daily_stats(self) -> Dict:
        """Get today's trading statistics"""
        self._reset_daily_stats()
        
        winning_trades = sum(1 for t in self.daily_trades if t['pnl'] > 0)
        losing_trades = sum(1 for t in self.daily_trades if t['pnl'] < 0)
        gross_profit = sum(t['pnl'] for t in self.daily_trades if t['pnl'] > 0)
        
        return {
            'trades_today': len(self.daily_trades),
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'gross_profit': gross_profit,
            'daily_loss': self.daily_loss,
            'circuit_breaker': self.circuit_breaker_active
        }
    
    def get_summary(self, 
                   current_equity: float,
                   initial_equity: float,
                   open_positions: int) -> str:
        """Get risk manager summary"""
        daily_loss_pct = (initial_equity - current_equity) / initial_equity * 100 if initial_equity > 0 else 0
        stats = self.get_daily_stats()
        
        summary = f"""
╔════════════════════════════════════════╗
║       RISK MANAGER SUMMARY             ║
╠════════════════════════════════════════╣
║ Daily Loss:             {daily_loss_pct:>18.2f}%
║ Daily Loss Limit:       {self.limits.max_daily_loss_pct:>18.1f}%
║ Trades Today:           {stats['trades_today']:>18d}/{self.limits.max_daily_trades}
║ Open Positions:         {open_positions:>18d}/{self.limits.max_concurrent_positions}
║ Circuit Breaker:        {str(self.circuit_breaker_active):>18s}
║ Daily Profit:           ${stats['gross_profit']:>18,.0f}
╚════════════════════════════════════════╝
        """
        return summary.strip()
