from __future__ import annotations

import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass

from bot.runtime.models import OrderIntent


@dataclass(frozen=True)
class ExecutionResult:
    client_order_id: str
    exchange_order_id: str
    status: str
    filled_price: float
    filled_quantity: float
    timestamp: int


class ExecutionAdapter(ABC):
    @abstractmethod
    def place_order(self, intent: OrderIntent) -> ExecutionResult:
        raise NotImplementedError


class PaperExecutionAdapter(ExecutionAdapter):
    def place_order(self, intent: OrderIntent) -> ExecutionResult:
        now_ms = int(time.time() * 1000)
        client_order_id = f"paper-{uuid.uuid4().hex[:12]}"
        return ExecutionResult(
            client_order_id=client_order_id,
            exchange_order_id=client_order_id,
            status="FILLED",
            filled_price=round(intent.price, 6),
            filled_quantity=round(intent.quantity, 8),
            timestamp=now_ms,
        )
