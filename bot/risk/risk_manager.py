from __future__ import annotations

from dataclasses import dataclass

from bot.data.market_data import Candle
from bot.runtime.models import BotConfig, PositionState, RiskDecision


@dataclass(frozen=True)
class AccountSnapshot:
    available_balance: float


class RiskManager:
    def __init__(self, config: BotConfig, account_snapshot: AccountSnapshot | None = None):
        self.config = config
        self.account_snapshot = account_snapshot or AccountSnapshot(available_balance=config.max_trade_notional * 10)

    def evaluate_signal(self, signal, open_positions: list[PositionState], latest_candle: Candle | None = None) -> RiskDecision:
        if signal.direction == "LONG" and not self.config.allow_longs:
            return RiskDecision(approved=False, reason="LONGS_DISABLED")
        if signal.direction == "SHORT" and not self.config.allow_shorts:
            return RiskDecision(approved=False, reason="SHORTS_DISABLED")
        if len(open_positions) >= self.config.max_open_positions:
            return RiskDecision(approved=False, reason="MAX_OPEN_POSITIONS")
        if any(position.pair == signal.pair for position in open_positions):
            return RiskDecision(approved=False, reason="PAIR_ALREADY_OPEN")
        if self.account_snapshot.available_balance < self.config.min_balance:
            return RiskDecision(approved=False, reason="INSUFFICIENT_BALANCE")
        if self.config.enable_kill_switch and self.config.max_daily_loss <= 0:
            return RiskDecision(approved=False, reason="KILL_SWITCH_ACTIVE")
        if latest_candle is not None and latest_candle.close_time < latest_candle.open_time:
            return RiskDecision(approved=False, reason="STALE_MARKET_DATA")

        quantity = round(self.config.max_trade_notional / signal.entry, 8) if signal.entry > 0 else 0.0
        if quantity <= 0:
            return RiskDecision(approved=False, reason="INVALID_SIZE")
        return RiskDecision(
            approved=True,
            reason="APPROVED",
            size=quantity,
            notional=round(quantity * signal.entry, 6),
        )
