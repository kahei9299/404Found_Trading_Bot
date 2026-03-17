"""Minimal Roostoo trading bot - places 1 market buy order."""

from bot.execution.client import get_server_time, get_exchange_info, get_ticker, get_balance, place_order
from bot.logs.logger import get_logger

log = get_logger("main")


def main():
    # 1. Verify connectivity
    server_time = get_server_time()
    log.info(f"Server time: {server_time}")

    # 2. Get exchange info to find valid pairs
    exchange_info = get_exchange_info()
    log.info(f"Exchange info keys: {list(exchange_info.keys())}")

    # 3. Check balance
    balance = get_balance()
    log.info(f"Balance: {balance}")

    # 4. Get ticker for BTC/USD
    pair = "BTC/USD"
    ticker = get_ticker(pair)
    log.info(f"Ticker {pair}: {ticker}")

    # 5. Place a small market buy order
    log.info(f"Placing MARKET BUY order for {pair}...")
    result = place_order(
        pair=pair,
        side="BUY",
        order_type="MARKET",
        quantity="0.001",
    )
    log.info(f"Order result: {result}")


if __name__ == "__main__":
    main()
