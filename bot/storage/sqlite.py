from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from bot.runtime.models import HeartbeatRecord, PositionState, SignalRecord


class SQLiteStorage:
    def __init__(self, path: str):
        self.path = Path(path)

    def init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS signals (
                    pair TEXT NOT NULL,
                    interval TEXT NOT NULL,
                    open_time INTEGER NOT NULL,
                    direction TEXT NOT NULL,
                    score REAL NOT NULL,
                    entry REAL NOT NULL,
                    stop_loss REAL NOT NULL,
                    take_profit_1 REAL NOT NULL,
                    take_profit_2 REAL NOT NULL,
                    take_profit_3 REAL NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    PRIMARY KEY (pair, interval, open_time)
                );

                CREATE TABLE IF NOT EXISTS positions (
                    pair TEXT PRIMARY KEY,
                    interval TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    status TEXT NOT NULL,
                    entry_time INTEGER NOT NULL,
                    entry_price REAL NOT NULL,
                    quantity REAL NOT NULL,
                    remaining_quantity REAL NOT NULL,
                    stop_loss REAL NOT NULL,
                    take_profit_1 REAL NOT NULL,
                    take_profit_2 REAL NOT NULL,
                    take_profit_3 REAL NOT NULL,
                    signal_time INTEGER NOT NULL,
                    last_candle_close_time INTEGER NOT NULL,
                    realized_pnl REAL NOT NULL,
                    fills_json TEXT NOT NULL,
                    updated_at INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS orders (
                    client_order_id TEXT PRIMARY KEY,
                    pair TEXT NOT NULL,
                    side TEXT NOT NULL,
                    order_type TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    price REAL NOT NULL,
                    status TEXT NOT NULL,
                    exchange_order_id TEXT,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS heartbeats (
                    component TEXT NOT NULL,
                    status TEXT NOT NULL,
                    message TEXT NOT NULL,
                    timestamp INTEGER NOT NULL
                );
                """
            )

    def save_signal(self, signal: SignalRecord) -> None:
        created_at = _now_ms()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO signals (
                    pair, interval, open_time, direction, score, entry, stop_loss,
                    take_profit_1, take_profit_2, take_profit_3, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    signal.pair,
                    signal.interval,
                    signal.open_time,
                    signal.direction,
                    signal.score,
                    signal.entry,
                    signal.stop_loss,
                    signal.take_profit_1,
                    signal.take_profit_2,
                    signal.take_profit_3,
                    json.dumps(signal.payload, sort_keys=True),
                    created_at,
                ),
            )

    def has_signal(self, pair: str, interval: str, open_time: int) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM signals WHERE pair = ? AND interval = ? AND open_time = ?",
                (pair, interval, open_time),
            ).fetchone()
        return row is not None

    def upsert_position(self, position: PositionState) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO positions (
                    pair, interval, direction, status, entry_time, entry_price, quantity,
                    remaining_quantity, stop_loss, take_profit_1, take_profit_2,
                    take_profit_3, signal_time, last_candle_close_time, realized_pnl,
                    fills_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(pair) DO UPDATE SET
                    interval = excluded.interval,
                    direction = excluded.direction,
                    status = excluded.status,
                    entry_time = excluded.entry_time,
                    entry_price = excluded.entry_price,
                    quantity = excluded.quantity,
                    remaining_quantity = excluded.remaining_quantity,
                    stop_loss = excluded.stop_loss,
                    take_profit_1 = excluded.take_profit_1,
                    take_profit_2 = excluded.take_profit_2,
                    take_profit_3 = excluded.take_profit_3,
                    signal_time = excluded.signal_time,
                    last_candle_close_time = excluded.last_candle_close_time,
                    realized_pnl = excluded.realized_pnl,
                    fills_json = excluded.fills_json,
                    updated_at = excluded.updated_at
                """,
                (
                    position.pair,
                    position.interval,
                    position.direction,
                    position.status,
                    position.entry_time,
                    position.entry_price,
                    position.quantity,
                    position.remaining_quantity,
                    position.stop_loss,
                    position.take_profit_1,
                    position.take_profit_2,
                    position.take_profit_3,
                    position.signal_time,
                    position.last_candle_close_time,
                    position.realized_pnl,
                    json.dumps([fill.to_dict() for fill in position.fills], sort_keys=True),
                    _now_ms(),
                ),
            )

    def get_open_position(self, pair: str) -> PositionState | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM positions WHERE pair = ? AND status = 'OPEN'",
                (pair,),
            ).fetchone()
        return self._row_to_position(row) if row else None

    def list_open_positions(self) -> list[PositionState]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM positions WHERE status = 'OPEN' ORDER BY pair").fetchall()
        return [self._row_to_position(row) for row in rows]

    def close_position(self, pair: str, position: PositionState) -> None:
        position.status = "CLOSED"
        self.upsert_position(position)

    def save_order(
        self,
        client_order_id: str,
        pair: str,
        side: str,
        order_type: str,
        quantity: float,
        price: float,
        status: str,
        exchange_order_id: str | None = None,
    ) -> None:
        now_ms = _now_ms()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO orders (
                    client_order_id, pair, side, order_type, quantity, price, status,
                    exchange_order_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(client_order_id) DO UPDATE SET
                    status = excluded.status,
                    exchange_order_id = excluded.exchange_order_id,
                    updated_at = excluded.updated_at
                """,
                (
                    client_order_id,
                    pair,
                    side,
                    order_type,
                    quantity,
                    price,
                    status,
                    exchange_order_id,
                    now_ms,
                    now_ms,
                ),
            )

    def save_heartbeat(self, heartbeat: HeartbeatRecord) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO heartbeats (component, status, message, timestamp) VALUES (?, ?, ?, ?)",
                (heartbeat.component, heartbeat.status, heartbeat.message, heartbeat.timestamp),
            )

    def get_last_heartbeat(self, component: str) -> HeartbeatRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT component, status, message, timestamp
                FROM heartbeats
                WHERE component = ?
                ORDER BY timestamp DESC
                LIMIT 1
                """,
                (component,),
            ).fetchone()
        return HeartbeatRecord(*row) if row else None

    def get_daily_realized_pnl(self) -> float:
        start_of_day = int(time.time() // 86_400) * 86_400 * 1000
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT realized_pnl FROM positions WHERE status = 'CLOSED' AND updated_at >= ?",
                (start_of_day,),
            ).fetchall()
        return round(sum(row[0] for row in rows), 6)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _row_to_position(row: sqlite3.Row) -> PositionState:
        from bot.runtime.models import FillRecord

        fills = [FillRecord(**item) for item in json.loads(row["fills_json"])]
        return PositionState(
            pair=row["pair"],
            interval=row["interval"],
            direction=row["direction"],
            status=row["status"],
            entry_time=row["entry_time"],
            entry_price=row["entry_price"],
            quantity=row["quantity"],
            remaining_quantity=row["remaining_quantity"],
            stop_loss=row["stop_loss"],
            take_profit_1=row["take_profit_1"],
            take_profit_2=row["take_profit_2"],
            take_profit_3=row["take_profit_3"],
            signal_time=row["signal_time"],
            last_candle_close_time=row["last_candle_close_time"],
            realized_pnl=row["realized_pnl"],
            fills=fills,
        )


def _now_ms() -> int:
    return int(time.time() * 1000)
