from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class TradingPairConfig:
    pair: str
    interval: str = "1h"
    candle_limit: int = 250
    htf_interval: str | None = None


@dataclass(frozen=True)
class BotConfig:
    mode: str = "paper"
    poll_seconds: int = 60
    db_path: str = "bot_state.sqlite3"
    pairs: tuple[TradingPairConfig, ...] = ()
    max_trade_notional: float = 1_000.0
    max_daily_loss: float = 250.0
    max_open_positions: int = 3
    min_balance: float = 100.0
    allow_longs: bool = True
    allow_shorts: bool = True
    enable_kill_switch: bool = True


@dataclass(frozen=True)
class SignalRecord:
    pair: str
    interval: str
    open_time: int
    direction: str
    score: float
    entry: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    take_profit_3: float
    payload: dict


@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    reason: str
    size: float = 0.0
    notional: float = 0.0


@dataclass(frozen=True)
class OrderIntent:
    pair: str
    interval: str
    side: str
    quantity: float
    order_type: str
    price: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    take_profit_3: float
    signal_time: int


@dataclass(frozen=True)
class FillRecord:
    time: int
    price: float
    quantity: float
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PositionState:
    pair: str
    interval: str
    direction: str
    status: str
    entry_time: int
    entry_price: float
    quantity: float
    remaining_quantity: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    take_profit_3: float
    signal_time: int
    last_candle_close_time: int = 0
    realized_pnl: float = 0.0
    fills: list[FillRecord] = field(default_factory=list)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["fills"] = [fill.to_dict() for fill in self.fills]
        return data


@dataclass(frozen=True)
class HeartbeatRecord:
    component: str
    status: str
    message: str
    timestamp: int

