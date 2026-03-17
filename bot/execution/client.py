import hashlib
import hmac
import time
import requests
from bot.config.settings import API_KEY, SECRET_KEY, BASE_URL


def _get_timestamp():
    """Get current timestamp in milliseconds."""
    return str(int(time.time() * 1000))


def _sign(params: dict) -> str:
    """Generate HMAC SHA256 signature from sorted params."""
    sorted_params = sorted(params.items())
    query_string = "&".join(f"{k}={v}" for k, v in sorted_params)
    signature = hmac.new(
        SECRET_KEY.encode("utf-8"),
        query_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return signature


def _headers(signature: str) -> dict:
    return {
        "RST-API-KEY": API_KEY,
        "MSG-SIGNATURE": signature,
    }


def get_server_time() -> dict:
    resp = requests.get(f"{BASE_URL}/v3/serverTime")
    resp.raise_for_status()
    return resp.json()


def get_exchange_info() -> dict:
    resp = requests.get(f"{BASE_URL}/v3/exchangeInfo")
    resp.raise_for_status()
    return resp.json()


def get_ticker(pair: str = None) -> dict:
    params = {"timestamp": _get_timestamp()}
    if pair:
        params["pair"] = pair
    resp = requests.get(f"{BASE_URL}/v3/ticker", params=params)
    resp.raise_for_status()
    return resp.json()


def get_balance() -> dict:
    params = {"timestamp": _get_timestamp()}
    signature = _sign(params)
    resp = requests.get(
        f"{BASE_URL}/v3/balance",
        params=params,
        headers=_headers(signature),
    )
    resp.raise_for_status()
    return resp.json()


def get_pending_count() -> dict:
    params = {"timestamp": _get_timestamp()}
    signature = _sign(params)
    resp = requests.get(
        f"{BASE_URL}/v3/pending_count",
        params=params,
        headers=_headers(signature),
    )
    resp.raise_for_status()
    return resp.json()


def query_order(order_id: str = None, pair: str = None, pending_only: bool = False) -> dict:
    params = {"timestamp": _get_timestamp()}
    if order_id:
        params["order_id"] = order_id
    else:
        if pair:
            params["pair"] = pair
        if pending_only:
            params["pending_only"] = "true"

    signature = _sign(params)
    headers = _headers(signature)
    headers["Content-Type"] = "application/x-www-form-urlencoded"

    resp = requests.post(
        f"{BASE_URL}/v3/query_order",
        data=params,
        headers=headers,
    )
    resp.raise_for_status()
    return resp.json()


def cancel_order(order_id: str, pair: str) -> dict:
    params = {
        "order_id": order_id,
        "pair": pair,
        "timestamp": _get_timestamp(),
    }
    signature = _sign(params)
    headers = _headers(signature)
    headers["Content-Type"] = "application/x-www-form-urlencoded"

    resp = requests.post(
        f"{BASE_URL}/v3/cancel_order",
        data=params,
        headers=headers,
    )
    resp.raise_for_status()
    return resp.json()


def place_order(pair: str, side: str, order_type: str, quantity: str, price: str = None) -> dict:
    params = {
        "pair": pair,
        "side": side,
        "type": order_type,
        "quantity": quantity,
        "timestamp": _get_timestamp(),
    }
    if order_type == "LIMIT" and price:
        params["price"] = price

    signature = _sign(params)
    headers = _headers(signature)
    headers["Content-Type"] = "application/x-www-form-urlencoded"

    resp = requests.post(
        f"{BASE_URL}/v3/place_order",
        data=params,
        headers=headers,
    )
    resp.raise_for_status()
    return resp.json()
