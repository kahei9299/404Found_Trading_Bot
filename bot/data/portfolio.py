"""
Portfolio Module
Tracks positions, calculates P&L, manages account balance
"""

import pandas as pd
from typing import Dict, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class Position:
    """Represents an open trading position"""
    
    symbol: str
    entry_price: float
    quantity: float
    entry_time: datetime
    atr_at_entry: float
    stop_loss: float
    trailing_stop: float
    
    # Tracking
    highest_price: float = field(default=None)
    bars_held: int = field(default=0)
    pnl_at_close: float = field(default=0.0)
    pnl_pct_at_close: float = field(default=0.0)
    exit_reason: str = field(default=None)
    
    def __post_init__(self):
        if self.highest_price is None:
            self.highest_price = self.entry_price
    
    def update(self, current_price: float):
        """Update position with current market price"""
        self.highest_price = max(self.highest_price, current_price)
        self.bars_held += 1
    
    def calculate_pnl(self, exit_price: float, commission_pct: float = 0.001) -> tuple:
        """
        Calculate P&L on position close.
        
        Args:
            exit_price: Price at exit
            commission_pct: Commission percentage (0.1% = 0.001)
            
        Returns:
            (pnl_dollars, pnl_percent)
        """
        # Calculate gross P&L
        gross_pnl = (exit_price - self.entry_price) * self.quantity
        
        # Deduct commission (both entry and exit)
        commission = (self.entry_price * self.quantity * commission_pct) + \
                     (exit_price * self.quantity * commission_pct)
        
        # Net P&L
        net_pnl = gross_pnl - commission
        pnl_percent = (exit_price - self.entry_price) / self.entry_price
        
        self.pnl_at_close = net_pnl
        self.pnl_pct_at_close = pnl_percent
        
        return net_pnl, pnl_percent
    
    def to_dict(self) -> dict:
        """Convert position to dictionary"""
        return {
            'symbol': self.symbol,
            'entry_price': self.entry_price,
            'quantity': self.quantity,
            'entry_time': self.entry_time,
            'atr_at_entry': self.atr_at_entry,
            'stop_loss': self.stop_loss,
            'trailing_stop': self.trailing_stop,
            'highest_price': self.highest_price,
            'bars_held': self.bars_held,
            'pnl_at_close': self.pnl_at_close,
            'pnl_pct_at_close': self.pnl_pct_at_close,
            'exit_reason': self.exit_reason
        }


class Portfolio:
    """Manages trading portfolio and account."""
    
    def __init__(self, 
                 initial_capital: float = 1000000,
                 commission_pct: float = 0.001,
                 risk_per_trade_pct: float = 0.02):
        """
        Initialize portfolio.
        
        Args:
            initial_capital: Starting account balance ($)
            commission_pct: Trading commission (0.1% = 0.001)
            risk_per_trade_pct: Risk per trade as % of equity (2% = 0.02)
        """
        self.initial_capital = initial_capital
        self.current_balance = initial_capital
        self.commission_pct = commission_pct
        self.risk_per_trade_pct = risk_per_trade_pct
        
        # Positions
        self.open_positions: Dict[str, Position] = {}  # {symbol: Position}
        self.closed_trades: List[Position] = []
        
        # History
        self.balance_history = [initial_capital]
        self.equity_history = [initial_capital]
        self.timestamp_history = [datetime.utcnow()]
    
    def get_available_balance(self) -> float:
        """Get cash available for new trades"""
        return self.current_balance
    
    def get_equity(self, market_prices: Dict[str, float]) -> float:
        """
        Calculate total account equity.
        
        Args:
            market_prices: Dict of {symbol: current_price}
            
        Returns:
            Total equity = cash + unrealized P&L from open positions
        """
        equity = self.current_balance
        
        for symbol, position in self.open_positions.items():
            if symbol in market_prices:
                current_price = market_prices[symbol]
                unrealized_pnl = (current_price - position.entry_price) * position.quantity
                # Deduct commission
                commission = position.entry_price * position.quantity * self.commission_pct
                unrealized_pnl -= commission
                equity += unrealized_pnl
        
        return equity
    
    def get_total_return_pct(self, equity: float) -> float:
        """Calculate total return percentage"""
        if self.initial_capital == 0:
            return 0.0
        return (equity - self.initial_capital) / self.initial_capital * 100
    
    def enter_position(self,
                      symbol: str,
                      entry_price: float,
                      atr: float,
                      entry_time: datetime = None) -> Optional[Position]:
        """
        Enter a new position.
        
        Args:
            symbol: Trading pair
            entry_price: Entry price
            atr: Current ATR for stop calculation
            entry_time: Entry timestamp
            
        Returns:
            Position object, or None if trade size too large
        """
        if entry_time is None:
            entry_time = datetime.utcnow()
        
        # Check if already have position
        if symbol in self.open_positions:
            logger.warning(f"⚠️  {symbol} already has open position")
            return None
        
        # Calculate position size
        risk_amount = self.current_balance * self.risk_per_trade_pct
        stop_distance = atr * 11  # 11x ATR stop
        
        if stop_distance == 0:
            logger.warning(f"⚠️  Invalid stop distance for {symbol}")
            return None
        
        quantity = risk_amount / stop_distance
        
        # Check if we have enough balance
        position_cost = entry_price * quantity
        if position_cost > self.current_balance:
            logger.warning(f"⚠️  Insufficient balance for {symbol}: need ${position_cost:,.0f}, have ${self.current_balance:,.0f}")
            return None
        
        # Create position
        position = Position(
            symbol=symbol,
            entry_price=entry_price,
            quantity=quantity,
            entry_time=entry_time,
            atr_at_entry=atr,
            stop_loss=entry_price - stop_distance,
            trailing_stop=entry_price - stop_distance
        )
        
        self.open_positions[symbol] = position
        
        # Deduct position cost from balance
        commission = position_cost * self.commission_pct
        self.current_balance -= commission  # Only deduct commission (margin trading)
        
        logger.info(f"✅ Entered {symbol}: {quantity:.4f} @ ${entry_price:,.2f}, stop @ ${position.stop_loss:,.2f}")
        
        return position
    
    def update_trailing_stop(self, 
                            symbol: str,
                            current_price: float,
                            atr: float) -> Optional[float]:
        """
        Update trailing stop for a position.
        
        Args:
            symbol: Trading pair
            current_price: Current price
            atr: Current ATR
            
        Returns:
            New trailing stop level, or None if position not found
        """
        if symbol not in self.open_positions:
            return None
        
        position = self.open_positions[symbol]
        new_trailing = current_price - (atr * 11)
        position.trailing_stop = max(position.trailing_stop, new_trailing)
        
        return position.trailing_stop
    
    def close_position(self,
                      symbol: str,
                      exit_price: float,
                      exit_reason: str = "Manual",
                      exit_time: datetime = None) -> Optional[dict]:
        """
        Close an open position.
        
        Args:
            symbol: Trading pair
            exit_price: Exit price
            exit_reason: Reason for exit (Trailing Stop, Signal Exit, etc)
            exit_time: Exit timestamp
            
        Returns:
            Trade summary dict, or None if position not found
        """
        if symbol not in self.open_positions:
            logger.warning(f"⚠️  No open position for {symbol}")
            return None
        
        if exit_time is None:
            exit_time = datetime.utcnow()
        
        position = self.open_positions[symbol]
        
        # Calculate P&L
        pnl, pnl_pct = position.calculate_pnl(exit_price, self.commission_pct)
        position.exit_reason = exit_reason
        
        # Update balance
        self.current_balance += pnl
        
        # Move to closed trades
        del self.open_positions[symbol]
        self.closed_trades.append(position)
        
        # Log trade
        logger.info(f"❌ Closed {symbol}: {pnl:+,.0f} ({pnl_pct*100:+.2f}%) | {exit_reason}")
        
        return {
            'symbol': symbol,
            'entry_time': position.entry_time,
            'exit_time': exit_time,
            'entry_price': position.entry_price,
            'exit_price': exit_price,
            'quantity': position.quantity,
            'pnl': pnl,
            'pnl_pct': pnl_pct,
            'bars_held': position.bars_held,
            'exit_reason': exit_reason
        }
    
    def get_open_positions(self) -> Dict[str, Position]:
        """Get all open positions"""
        return self.open_positions.copy()
    
    def get_position(self, symbol: str) -> Optional[Position]:
        """Get specific position by symbol"""
        return self.open_positions.get(symbol)
    
    def get_closed_trades(self) -> List[Position]:
        """Get all closed trades"""
        return self.closed_trades.copy()
    
    def get_trade_stats(self) -> dict:
        """Calculate trade statistics"""
        if not self.closed_trades:
            return {
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0.0,
                'avg_win': 0.0,
                'avg_loss': 0.0,
                'profit_factor': 0.0,
                'gross_profit': 0.0,
                'gross_loss': 0.0
            }
        
        trades_df = pd.DataFrame([t.to_dict() for t in self.closed_trades])
        
        winning = trades_df[trades_df['pnl_at_close'] > 0]
        losing = trades_df[trades_df['pnl_at_close'] < 0]
        
        total_trades = len(trades_df)
        winning_trades = len(winning)
        losing_trades = len(losing)
        
        gross_profit = winning['pnl_at_close'].sum()
        gross_loss = abs(losing['pnl_at_close'].sum())
        
        return {
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': winning_trades / total_trades * 100 if total_trades > 0 else 0,
            'avg_win': winning['pnl_at_close'].mean() if len(winning) > 0 else 0.0,
            'avg_loss': losing['pnl_at_close'].mean() if len(losing) > 0 else 0.0,
            'profit_factor': gross_profit / gross_loss if gross_loss > 0 else 0.0,
            'gross_profit': gross_profit,
            'gross_loss': gross_loss
        }
    
    def get_summary(self, current_equity: float) -> str:
        """Get portfolio summary string"""
        total_return = self.get_total_return_pct(current_equity)
        stats = self.get_trade_stats()
        open_pos = len(self.open_positions)
        closed_trades = len(self.closed_trades)
        
        summary = f"""
╔════════════════════════════════════════╗
║         PORTFOLIO SUMMARY              ║
╠════════════════════════════════════════╣
║ Initial Capital:        ${self.initial_capital:>18,.0f}
║ Current Equity:         ${current_equity:>18,.0f}
║ Total Return:           {total_return:>18.2f}%
║ Cash Available:         ${self.current_balance:>18,.0f}
╠════════════════════════════════════════╣
║ Open Positions:         {open_pos:>18d}
║ Closed Trades:          {closed_trades:>18d}
║ Win Rate:               {stats['win_rate']:>18.1f}%
║ Profit Factor:          {stats['profit_factor']:>18.2f}
║ Gross Profit:           ${stats['gross_profit']:>18,.0f}
║ Gross Loss:             ${-stats['gross_loss']:>18,.0f}
╚════════════════════════════════════════╝
        """
        return summary.strip()
