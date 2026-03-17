"""Roostoo trading bot CLI.

Usage:
    python -m bot.main balance
    python -m bot.main price [PAIR]
    python -m bot.main pairs
    python -m bot.main buy PAIR QUANTITY [--limit PRICE]
    python -m bot.main sell PAIR QUANTITY [--limit PRICE]
    python -m bot.main orders [--pair PAIR] [--pending]
    python -m bot.main order ORDER_ID
    python -m bot.main cancel ORDER_ID PAIR
"""

import argparse
import json
import sys
from bot.execution.client import (
    get_balance, get_ticker, get_exchange_info,
    place_order, query_order, cancel_order, get_pending_count,
)


def fmt(data):
    print(json.dumps(data, indent=2))


def cmd_balance(args):
    data = get_balance()
    wallet = data.get("SpotWallet", {})
    print("=== Balance ===")
    for coin, amounts in wallet.items():
        free = amounts.get("Free", 0)
        lock = amounts.get("Lock", 0)
        if free or lock:
            print(f"  {coin}: {free} (locked: {lock})")


def cmd_price(args):
    pair = args.pair
    data = get_ticker(pair)
    prices = data.get("Data", {})
    print("=== Prices ===")
    for name, info in prices.items():
        print(f"  {name}: ${info['LastPrice']:,.2f}  (bid: {info['MaxBid']}, ask: {info['MinAsk']}, 24h: {info['Change']:+.2%})")


def cmd_pairs(args):
    data = get_exchange_info()
    pairs = data.get("TradePairs", {})
    print("=== Trading Pairs ===")
    for name, p in pairs.items():
        print(f"  {name}  min_order: {p['MiniOrder']}  price_precision: {p['PricePrecision']}  amount_precision: {p['AmountPrecision']}")


def cmd_buy(args):
    order_type = "LIMIT" if args.limit else "MARKET"
    result = place_order(args.pair, "BUY", order_type, args.quantity, args.limit)
    detail = result.get("OrderDetail", {})
    status = detail.get("Status", "UNKNOWN")
    print(f"BUY {args.pair} | {order_type} | qty: {args.quantity} | status: {status}")
    if status == "FILLED":
        print(f"  filled @ ${detail['FilledAverPrice']:,.2f} | cost: ${detail['UnitChange']:,.2f} | fee: ${detail['CommissionChargeValue']}")
    elif status == "PENDING":
        print(f"  order_id: {detail['OrderID']} | limit price: {args.limit}")
    if not result.get("Success"):
        print(f"  error: {result.get('ErrMsg')}")


def cmd_sell(args):
    order_type = "LIMIT" if args.limit else "MARKET"
    result = place_order(args.pair, "SELL", order_type, args.quantity, args.limit)
    detail = result.get("OrderDetail", {})
    status = detail.get("Status", "UNKNOWN")
    print(f"SELL {args.pair} | {order_type} | qty: {args.quantity} | status: {status}")
    if status == "FILLED":
        print(f"  filled @ ${detail['FilledAverPrice']:,.2f} | received: ${detail['UnitChange']:,.2f} | fee: ${detail['CommissionChargeValue']}")
    elif status == "PENDING":
        print(f"  order_id: {detail['OrderID']} | limit price: {args.limit}")
    if not result.get("Success"):
        print(f"  error: {result.get('ErrMsg')}")


def cmd_orders(args):
    data = query_order(pair=args.pair, pending_only=args.pending)
    orders = data.get("Orders", [])
    print(f"=== Orders ({len(orders)}) ===")
    for o in orders:
        print(f"  #{o['OrderID']} {o['Side']} {o['Pair']} | {o['Type']} | qty: {o['Quantity']} | status: {o['Status']}")


def cmd_order(args):
    data = query_order(order_id=args.order_id)
    fmt(data)


def cmd_cancel(args):
    result = cancel_order(args.order_id, args.pair)
    if result.get("Success"):
        print(f"Cancelled order #{args.order_id}")
    else:
        print(f"Failed: {result.get('ErrMsg')}")


def main():
    parser = argparse.ArgumentParser(prog="bot", description="Roostoo Trading Bot")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("balance", help="Show wallet balance")

    p_price = sub.add_parser("price", help="Get ticker prices")
    p_price.add_argument("pair", nargs="?", default=None, help="e.g. BTC/USD (omit for all)")

    sub.add_parser("pairs", help="List available trading pairs")

    p_buy = sub.add_parser("buy", help="Buy a coin")
    p_buy.add_argument("pair", help="e.g. BTC/USD")
    p_buy.add_argument("quantity", help="Amount to buy")
    p_buy.add_argument("--limit", help="Limit price (omit for market order)")

    p_sell = sub.add_parser("sell", help="Sell a coin")
    p_sell.add_argument("pair", help="e.g. BTC/USD")
    p_sell.add_argument("quantity", help="Amount to sell")
    p_sell.add_argument("--limit", help="Limit price (omit for market order)")

    p_orders = sub.add_parser("orders", help="List orders")
    p_orders.add_argument("--pair", help="Filter by pair")
    p_orders.add_argument("--pending", action="store_true", help="Only pending orders")

    p_order = sub.add_parser("order", help="Get order details")
    p_order.add_argument("order_id", help="Order ID")

    p_cancel = sub.add_parser("cancel", help="Cancel a pending order")
    p_cancel.add_argument("order_id", help="Order ID")
    p_cancel.add_argument("pair", help="Trading pair")

    args = parser.parse_args()

    commands = {
        "balance": cmd_balance,
        "price": cmd_price,
        "pairs": cmd_pairs,
        "buy": cmd_buy,
        "sell": cmd_sell,
        "orders": cmd_orders,
        "order": cmd_order,
        "cancel": cmd_cancel,
    }

    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
