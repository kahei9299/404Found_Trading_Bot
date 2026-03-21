"""
Roostoo Trading Bot - Live Trading Loop

Main entry point for the autonomous trading bot.
Runs continuous loop that:
1. Fetches latest market data (30m candles)
2. Generates trading signals using CryptoFlux Dynamo strategy
3. Manages positions and P&L
4. Enforces risk limits
5. Logs all activity

Usage:
    python -m bot.main                    # Run the bot
    python -m bot.main --dry-run          # Test without placing orders
    python -m bot.main --status           # Show current status
"""

import time
import logging
import argparse
from datetime import datetime
from typing import Dict, List, Optional
import pandas as pd
import numpy as np

from bot.data import MarketData, Portfolio
from bot.strategy import StrategyManager
from bot.execution.execution import OrderExecutor
from bot.execution.order_manager import OrderManager
from bot.risk.risk_manager import RiskManager, RiskLimits
from bot.utils.helpers import (
    format_currency, format_percent, format_trade_summary,
    log_separator, get_timestamp_str
)

# Configuration
TRADING_PAIRS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'XRP/USDT']
TIMEFRAME = '30m'
INITIAL_CAPITAL = 1000000
SIGNAL_CHECK_INTERVAL_SECONDS = 60  # Check for signals every 1 minute

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(name)s | %(levelname)s | %(message)s',
    handlers=[
        logging.FileHandler('bot/logs/trading.log', mode='w'),  # 'w' = fresh file each time
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class TradingBot:
    """Main trading bot controller"""
    
    def __init__(self, 
                 pairs: List[str] = TRADING_PAIRS,
                 initial_capital: float = INITIAL_CAPITAL):
        """Initialize trading bot"""
        logger.info(f"\n{'='*70}")
        logger.info(f"TRADING BOT INITIALIZATION")
        logger.info(f"{'='*70}\n")
        
        self.pairs = pairs
        self.initial_capital = initial_capital
        
        # Initialize components
        logger.info("[MARKET] Initializing market data...")
        self.market_data = MarketData(timeframe=TIMEFRAME)
        
        logger.info("[STRATEGY] Initializing strategy...")
        self.strategy_manager = StrategyManager()
        for pair in pairs:
            self.strategy_manager.add_pair(pair)
        
        logger.info("[PORTFOLIO] Initializing portfolio...")
        self.portfolio = Portfolio(initial_capital=initial_capital)
        
        logger.info("[EXECUTION] Initializing order executor...")
        self.executor = OrderExecutor()
        
        logger.info("[EXECUTION] Initializing order manager...")
        self.order_manager = OrderManager()
        
        logger.info("[RISK] Initializing risk manager...")
        risk_limits = RiskLimits(
            max_daily_loss_pct=10.0,
            max_daily_trades=10,
            max_concurrent_positions=4,
            risk_per_trade_pct=2.0
        )
        self.risk_manager = RiskManager(limits=risk_limits)
        
        # State
        self.running = False
        self.session_trades: List[Dict] = []
        self.iteration = 0
        
        logger.info(f"\n[SUCCESS] Bot initialized!\n")
    
    def fetch_market_data(self) -> Dict[str, Optional[pd.DataFrame]]:
        """Fetch latest OHLCV data for all pairs"""
        data = self.market_data.fetch_multiple(self.pairs, limit=50)
        return data
    
    def check_position_exits(self, market_prices: Dict[str, float], market_data: Dict[str, pd.DataFrame]):
        """Check if any open positions should be exited"""
        for symbol, position in list(self.portfolio.get_open_positions().items()):
            if symbol not in market_prices or symbol not in market_data:
                continue
            
            current_price = market_prices[symbol]
            df = market_data[symbol]
            
            if df is None or len(df) < 14:
                continue
            
            # Calculate ATR
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
            atr = pd.Series(tr).rolling(14).mean().iloc[-1]
            
            if pd.notna(atr):
                self.portfolio.update_trailing_stop(symbol, current_price, atr)
            
            # Check exit conditions
            should_exit = False
            exit_reason = None
            
            if current_price <= position.trailing_stop:
                should_exit = True
                exit_reason = "Trailing Stop"
            elif current_price <= position.stop_loss:
                should_exit = True
                exit_reason = "Hard Stop"
            
            if should_exit:
                self._close_position(symbol, current_price, exit_reason)
    
    def check_entry_signals(self, market_data: Dict[str, pd.DataFrame]):
        """Check for entry signals and place orders"""
        for symbol in self.pairs:
            if symbol not in market_data or market_data[symbol] is None:
                continue
            
            df = market_data[symbol]
            if len(df) < 20:
                continue
            
            # Check if already have position
            if symbol in self.portfolio.get_open_positions():
                continue
            
            # Get signal from strategy
            signal = self.strategy_manager.get_signal(symbol, df)
            if not signal['entry']:
                continue
            
            # Check risk limits
            can_trade, reason = self.risk_manager.check_can_trade(
                current_equity=self.portfolio.current_balance,
                initial_equity=self.initial_capital,
                open_positions_count=len(self.portfolio.get_open_positions())
            )
            
            if not can_trade:
                    logger.warning(f"[WARNING] Cannot enter {symbol}: {reason}")
            
            # Enter position
            entry_price = df.iloc[-1]['close']
            atr = signal['atr']
            
            position = self.portfolio.enter_position(
                symbol=symbol,
                entry_price=entry_price,
                atr=atr
            )
            
            if position:
                logger.info(f"[BUY] Entry signal: {symbol} @ ${entry_price:,.2f}")
    
    def _close_position(self, symbol: str, exit_price: float, reason: str):
        """Close a position and record trade"""
        trade_result = self.portfolio.close_position(
            symbol=symbol,
            exit_price=exit_price,
            exit_reason=reason
        )
        
        if trade_result:
            self.risk_manager.record_trade(
                symbol=symbol,
                pnl=trade_result['pnl'],
                quantity=trade_result['quantity']
            )
            self.session_trades.append(trade_result)
            logger.info(f"\n{format_trade_summary(trade_result)}\n")
    
    def print_status(self):
        """Print current bot status"""
        # Get current prices
        market_prices = {}
        for symbol in self.pairs:
            ticker = self.executor.get_ticker(symbol)
            if ticker:
                market_prices[symbol] = ticker.get('last', ticker.get('close', 0))
        
        # Calculate equity
        current_equity = self.portfolio.get_equity(market_prices)
        
        logger.info(f"\n{log_separator()}")
        logger.info(f"STATUS - {get_timestamp_str()}")
        logger.info(f"{log_separator()}")
        logger.info(self.portfolio.get_summary(current_equity))
        logger.info(f"\n{self.risk_manager.get_summary(current_equity, self.initial_capital, len(self.portfolio.get_open_positions()))}")
        
        open_pos = self.portfolio.get_open_positions()
        if open_pos:
            logger.info(f"\nOpen Positions ({len(open_pos)}):")
            for symbol, position in open_pos.items():
                current_price = market_prices.get(symbol, position.entry_price)
                unrealized_pnl = (current_price - position.entry_price) * position.quantity
                logger.info(f"  {symbol:12} | Entry: ${position.entry_price:10,.2f} | Current: ${current_price:>10,.2f} | Up: {unrealized_pnl:+12,.0f}")
        
        if self.session_trades:
            logger.info(f"\nRecent Trades ({len(self.session_trades)}):")
            for trade in self.session_trades[-5:]:
                logger.info(f"  {format_trade_summary(trade)}")
        
        logger.info(f"\n{log_separator()}\n")
    
    def run(self, dry_run: bool = False):
        """Run the trading bot"""
        self.running = True
        logger.info(f"\n{'='*70}")
        logger.info(f"[START] TRADING BOT STARTED")
        logger.info(f"   Mode: {'DRY RUN (no orders)' if dry_run else 'LIVE TRADING'}")
        logger.info(f"   Pairs: {', '.join(self.pairs)}")
        logger.info(f"   Capital: {format_currency(self.initial_capital)}")
        logger.info(f"{'='*70}\n")
        
        try:
            while self.running:
                self.iteration += 1
                
                # Fetch market data
                market_data = self.fetch_market_data()
                
                if not market_data or not any(df is not None for df in market_data.values()):
                    logger.warning("[WARNING] Failed to fetch market data")
                    time.sleep(SIGNAL_CHECK_INTERVAL_SECONDS)
                    continue
                
                # Get current prices
                market_prices = {}
                for symbol, df in market_data.items():
                    if df is not None and len(df) > 0:
                        market_prices[symbol] = df.iloc[-1]['close']
                
                # Check exits
                self.check_position_exits(market_prices, market_data)
                
                # Check entries
                if not dry_run:
                    self.check_entry_signals(market_data)
                
                # Print status every 10 iterations (10 mins)
                if self.iteration % 10 == 0:
                    self.print_status()
                
                # Sleep until next check
                time.sleep(SIGNAL_CHECK_INTERVAL_SECONDS)
        
        except KeyboardInterrupt:
            logger.info("\n\n[STOP] Bot interrupted by user\n")
        except Exception as e:
            logger.error(f"\n\n[ERROR] Fatal error: {str(e)}\n", exc_info=True)
        finally:
            self.stop()
    
    def stop(self):
        """Stop the trading bot"""
        self.running = False
        self.print_status()
        logger.info(f"\n{'='*70}")
        logger.info(f"[STOP] TRADING BOT STOPPED")
        logger.info(f"{'='*70}\n")


def main():
    parser = argparse.ArgumentParser(prog="bot", description="Roostoo Trading Bot")
    parser.add_argument('--dry-run', action='store_true', help='Run without placing orders')
    parser.add_argument('--status', action='store_true', help='Show current bot status')
    
    args = parser.parse_args()
    
    # Initialize bot
    bot = TradingBot(pairs=TRADING_PAIRS, initial_capital=INITIAL_CAPITAL)
    
    if args.status:
        bot.print_status()
    else:
        try:
            bot.run(dry_run=args.dry_run)
        except Exception as e:
            logger.error(f"Fatal error: {e}", exc_info=True)
            raise


if __name__ == '__main__':
    main()
