from __future__ import annotations

from bot.execution.execution import ExecutionAdapter
from bot.runtime.models import FillRecord, OrderIntent, PositionState
from bot.storage.sqlite import SQLiteStorage


class OrderManager:
    def __init__(self, execution_adapter: ExecutionAdapter, storage: SQLiteStorage):
        self.execution_adapter = execution_adapter
        self.storage = storage

    def open_position(self, signal, quantity: float) -> PositionState:
        side = "BUY" if signal.direction == "LONG" else "SELL"
        intent = OrderIntent(
            pair=signal.pair,
            interval=signal.interval,
            side=side,
            quantity=quantity,
            order_type="MARKET",
            price=signal.entry,
            stop_loss=signal.stop_loss,
            take_profit_1=signal.take_profit_1,
            take_profit_2=signal.take_profit_2,
            take_profit_3=signal.take_profit_3,
            signal_time=signal.open_time,
        )
        result = self.execution_adapter.place_order(intent)
        self.storage.save_order(
            client_order_id=result.client_order_id,
            pair=intent.pair,
            side=intent.side,
            order_type=intent.order_type,
            quantity=result.filled_quantity,
            price=result.filled_price,
            status=result.status,
            exchange_order_id=result.exchange_order_id,
        )
        position = PositionState(
            pair=signal.pair,
            interval=signal.interval,
            direction=signal.direction,
            status="OPEN",
            entry_time=result.timestamp,
            entry_price=result.filled_price,
            quantity=result.filled_quantity,
            remaining_quantity=result.filled_quantity,
            stop_loss=signal.stop_loss,
            take_profit_1=signal.take_profit_1,
            take_profit_2=signal.take_profit_2,
            take_profit_3=signal.take_profit_3,
            signal_time=signal.open_time,
            fills=[
                FillRecord(
                    time=result.timestamp,
                    price=result.filled_price,
                    quantity=result.filled_quantity,
                    reason="ENTRY",
                )
            ],
        )
        self.storage.upsert_position(position)
        return position

    def close_position(self, position: PositionState) -> None:
        self.storage.close_position(position.pair, position)
