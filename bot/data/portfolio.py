from __future__ import annotations

from dataclasses import dataclass

from bot.runtime.models import PositionState


@dataclass(frozen=True)
class PortfolioSnapshot:
    open_positions: list[PositionState]
    realized_pnl: float

    @property
    def open_position_count(self) -> int:
        return len(self.open_positions)
