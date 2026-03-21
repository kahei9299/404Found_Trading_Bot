"""
Order Execution Module
Handles placing and managing orders on the exchange
"""

import ccxt
from typing import Dict, Optional, List
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class OrderExecutor:
    """Executes trades on the exchange"""
    
    def __init__(self, exchange_id: str = 'binance'):
        """
        Initialize order executor.
        
        Args:
            exchange_id: Exchange to use (default: binance)
        """
        self.exchange_id = exchange_id
        try:
            self.exchange = getattr(ccxt, exchange_id)()
            logger.info(f"[SUCCESS] Initialized {exchange_id} exchange")
        except Exception as e:
            logger.error(f"❌ Failed to initialize exchange: {e}")
            raise
        
        self.order_history: List[Dict] = []
    
    def place_market_order(self,
                          symbol: str,
                          side: str,
                          amount: float) -> Optional[Dict]:
        """
        Place a market order.
        
        Args:
            symbol: Trading pair (e.g., 'BTC/USDT')
            side: 'buy' or 'sell'
            amount: Quantity to trade
            
        Returns:
            Order dict from exchange, or None if failed
        """
        try:
            logger.info(f"[ORDER] Placing {side.upper()} {amount:.4f} {symbol}...")
            
            order = self.exchange.create_market_order(
                symbol=symbol,
                side=side,
                amount=amount
            )
            
            self.order_history.append(order)
            logger.info(f"[SUCCESS] Order placed: {order['id']} @ avg {order.get('average', 'N/A')}")
            
            return order
            
        except ccxt.InsufficientBalance:
            logger.error(f"❌ Insufficient balance for {side} {amount} {symbol}")
            return None
        except ccxt.InvalidOrder:
            logger.error(f"❌ Invalid order: {side} {amount} {symbol}")
            return None
        except Exception as e:
            logger.error(f"❌ Order placement failed: {str(e)[:100]}")
            return None
    
    def place_limit_order(self,
                         symbol: str,
                         side: str,
                         amount: float,
                         price: float) -> Optional[Dict]:
        """
        Place a limit order.
        
        Args:
            symbol: Trading pair
            side: 'buy' or 'sell'
            amount: Quantity
            price: Limit price
            
        Returns:
            Order dict, or None if failed
        """
        try:
            logger.info(f"[ORDER] Placing limit {side.upper()} {amount:.4f} {symbol} @ ${price:,.2f}...")
            
            order = self.exchange.create_limit_order(
                symbol=symbol,
                side=side,
                amount=amount,
                price=price
            )
            
            self.order_history.append(order)
            logger.info(f"[SUCCESS] Limit order placed: {order['id']}")
            
            return order
            
        except Exception as e:
            logger.error(f"❌ Limit order failed: {str(e)[:100]}")
            return None
    
    def cancel_order(self, order_id: str, symbol: str) -> bool:
        """
        Cancel an open order.
        
        Args:
            order_id: Order ID to cancel
            symbol: Trading pair
            
        Returns:
            True if cancelled, False otherwise
        """
        try:
            logger.info(f"[CANCEL] Cancelling order {order_id} ({symbol})...")
            self.exchange.cancel_order(order_id, symbol)
            logger.info(f"[SUCCESS] Order {order_id} cancelled")
            return True
        except Exception as e:
            logger.error(f"❌ Cancel failed: {str(e)[:100]}")
            return False
    
    def get_order_status(self, order_id: str, symbol: str) -> Optional[Dict]:
        """
        Get order status.
        
        Args:
            order_id: Order ID
            symbol: Trading pair
            
        Returns:
            Order dict, or None if not found
        """
        try:
            order = self.exchange.fetch_order(order_id, symbol)
            return order
        except Exception as e:
            logger.error(f"❌ Failed to fetch order: {str(e)[:100]}")
            return None
    
    def get_balance(self) -> Optional[Dict]:
        """
        Get account balance.
        
        Returns:
            Balance dict with free/used per currency
        """
        try:
            balance = self.exchange.fetch_balance()
            return balance
        except Exception as e:
            logger.error(f"❌ Failed to fetch balance: {str(e)[:100]}")
            return None
    
    def get_ticker(self, symbol: str) -> Optional[Dict]:
        """
        Get current ticker for a symbol.
        
        Args:
            symbol: Trading pair
            
        Returns:
            Ticker dict with bid/ask/last, or None if failed
        """
        try:
            ticker = self.exchange.fetch_ticker(symbol)
            return ticker
        except Exception as e:
            logger.error(f"❌ Failed to fetch ticker: {str(e)[:100]}")
            return None
    
    def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict]:
        """
        Get all open orders.
        
        Args:
            symbol: Optional symbol to filter by
            
        Returns:
            List of open order dicts
        """
        try:
            if symbol:
                orders = self.exchange.fetch_open_orders(symbol)
            else:
                orders = self.exchange.fetch_open_orders()
            return orders
        except Exception as e:
            logger.error(f"❌ Failed to fetch open orders: {str(e)[:100]}")
            return []
    
    def get_order_history(self, limit: int = 20) -> List[Dict]:
        """Get recent order history"""
        return self.order_history[-limit:]
