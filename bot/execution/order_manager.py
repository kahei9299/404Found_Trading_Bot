"""
Order Manager Module
Tracks and manages all placed orders
"""

from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class Order:
    """Represents a placed order"""
    
    order_id: str
    symbol: str
    side: str  # 'buy' or 'sell'
    amount: float
    price: Optional[float]  # None for market orders
    order_type: str  # 'market' or 'limit'
    timestamp: datetime
    
    # Status
    status: str = 'open'  # 'open', 'closed', 'cancelled'
    filled: float = field(default=0.0)
    remaining: float = field(default=0.0)
    average_price: float = field(default=0.0)
    
    # Related trade
    position_id: Optional[str] = field(default=None)
    
    def is_closed(self) -> bool:
        """Check if order is fully filled or cancelled"""
        return self.status in ['closed', 'cancelled']
    
    def get_fill_percent(self) -> float:
        """Get percentage of order filled"""
        if self.amount == 0:
            return 0.0
        return (self.filled / self.amount) * 100
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            'order_id': self.order_id,
            'symbol': self.symbol,
            'side': self.side,
            'amount': self.amount,
            'price': self.price,
            'order_type': self.order_type,
            'timestamp': self.timestamp.isoformat(),
            'status': self.status,
            'filled': self.filled,
            'remaining': self.remaining,
            'average_price': self.average_price,
            'fill_percent': self.get_fill_percent()
        }


class OrderManager:
    """Manages order lifecycle and tracking"""
    
    def __init__(self):
        """Initialize order manager"""
        self.orders: Dict[str, Order] = {}  # {order_id: Order}
        self.orders_by_symbol: Dict[str, List[str]] = {}  # {symbol: [order_ids]}
        self.order_history: List[Order] = []
    
    def register_order(self,
                      order_id: str,
                      symbol: str,
                      side: str,
                      amount: float,
                      price: Optional[float] = None,
                      order_type: str = 'market',
                      position_id: Optional[str] = None) -> Order:
        """
        Register a new order.
        
        Args:
            order_id: Order ID from exchange
            symbol: Trading pair
            side: 'buy' or 'sell'
            amount: Order amount
            price: Limit price (None for market)
            order_type: 'market' or 'limit'
            position_id: Associated position ID
            
        Returns:
            Order object
        """
        order = Order(
            order_id=order_id,
            symbol=symbol,
            side=side,
            amount=amount,
            price=price,
            order_type=order_type,
            timestamp=datetime.utcnow(),
            position_id=position_id,
            remaining=amount
        )
        
        self.orders[order_id] = order
        
        if symbol not in self.orders_by_symbol:
            self.orders_by_symbol[symbol] = []
        self.orders_by_symbol[symbol].append(order_id)
        
        logger.info(f"✅ Registered order {order_id}: {side.upper()} {amount} {symbol}")
        
        return order
    
    def update_order_status(self,
                           order_id: str,
                           status: str,
                           filled: float = 0.0,
                           average_price: float = 0.0) -> Optional[Order]:
        """
        Update order status.
        
        Args:
            order_id: Order ID
            status: New status ('open', 'closed', 'cancelled')
            filled: Amount filled
            average_price: Average fill price
            
        Returns:
            Updated Order, or None if order not found
        """
        if order_id not in self.orders:
            logger.warning(f"⚠️  Order {order_id} not found")
            return None
        
        order = self.orders[order_id]
        order.status = status
        order.filled = filled
        order.remaining = max(0, order.amount - filled)
        order.average_price = average_price
        
        if order.is_closed():
            self.order_history.append(order)
            logger.info(f"✅ Order {order_id} {status}: {filled:.4f} filled @ ${average_price:,.2f}")
        
        return order
    
    def get_order(self, order_id: str) -> Optional[Order]:
        """Get order by ID"""
        return self.orders.get(order_id)
    
    def get_open_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """
        Get all open orders.
        
        Args:
            symbol: Optional symbol to filter
            
        Returns:
            List of open orders
        """
        if symbol:
            order_ids = self.orders_by_symbol.get(symbol, [])
            return [self.orders[oid] for oid in order_ids if self.orders[oid].status == 'open']
        else:
            return [o for o in self.orders.values() if o.status == 'open']
    
    def get_orders_by_symbol(self, symbol: str) -> List[Order]:
        """Get all orders for a symbol"""
        order_ids = self.orders_by_symbol.get(symbol, [])
        return [self.orders[oid] for oid in order_ids]
    
    def get_orders_by_position(self, position_id: str) -> List[Order]:
        """Get all orders related to a position"""
        return [o for o in self.orders.values() if o.position_id == position_id]
    
    def get_closed_orders(self) -> List[Order]:
        """Get all closed orders"""
        return self.order_history.copy()
    
    def cancel_order(self, order_id: str) -> Optional[Order]:
        """Mark order as cancelled"""
        if order_id not in self.orders:
            return None
        
        order = self.orders[order_id]
        order.status = 'cancelled'
        self.order_history.append(order)
        
        logger.info(f"❌ Cancelled order {order_id}")
        
        return order
    
    def get_summary(self) -> str:
        """Get order manager summary"""
        open_orders = self.get_open_orders()
        closed_orders = self.get_closed_orders()
        
        total_filled_value = sum(
            o.filled * o.average_price 
            for o in closed_orders 
            if o.average_price > 0
        )
        
        summary = f"""
╔════════════════════════════════════════╗
║         ORDER MANAGER SUMMARY          ║
╠════════════════════════════════════════╣
║ Open Orders:            {len(open_orders):>18d}
║ Closed Orders:          {len(closed_orders):>18d}
║ Total Executed Value:   ${total_filled_value:>18,.0f}
╚════════════════════════════════════════╝
        """
        return summary.strip()
