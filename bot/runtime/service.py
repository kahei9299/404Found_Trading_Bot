from __future__ import annotations

import time

from bot.data.market_data import Candle
from bot.execution.order_manager import OrderManager
from bot.logs.logger import get_logger
from bot.risk.risk_manager import RiskManager
from bot.runtime.models import BotConfig, FillRecord, HeartbeatRecord, PositionState, SignalRecord, TradingPairConfig
from bot.storage.sqlite import SQLiteStorage
from bot.strategy.precision_sniper import (
    StrategyConfig,
    build_htf_bias_lookup,
    generate_precision_sniper_signal,
    infer_htf_interval,
)


class TradingService:
    def __init__(self, config: BotConfig, market_data_provider, storage: SQLiteStorage, order_manager: OrderManager, risk_manager: RiskManager):
        self.config = config
        self.market_data_provider = market_data_provider
        self.storage = storage
        self.order_manager = order_manager
        self.risk_manager = risk_manager
        self.logger = get_logger("bot.runtime.service")

    def run_cycle(self) -> dict:
        cycle_results = []
        for pair_config in self.config.pairs:
            cycle_results.append(self._run_pair_cycle(pair_config))

        summary = {
            "pairs": cycle_results,
            "open_positions": len(self.storage.list_open_positions()),
            "timestamp": int(time.time() * 1000),
        }
        self.storage.save_heartbeat(
            HeartbeatRecord(
                component="runner",
                status="ok",
                message=f"Processed {len(cycle_results)} pair(s)",
                timestamp=summary["timestamp"],
            )
        )
        self.logger.info("cycle_complete extra=%s", summary)
        return summary

    def _run_pair_cycle(self, pair_config: TradingPairConfig) -> dict:
        strategy_config = StrategyConfig(
            htf_interval=pair_config.htf_interval or infer_htf_interval(pair_config.interval)
        )
        candles = self.market_data_provider.get_candles(
            pair=pair_config.pair,
            interval=pair_config.interval,
            limit=pair_config.candle_limit,
        )
        open_position = self.storage.get_open_position(pair_config.pair)
        if open_position is not None:
            self._process_open_position(open_position, candles[-1])

        signal = self._generate_signal(pair_config, strategy_config, candles)
        if signal is None:
            return {"pair": pair_config.pair, "signal": "NONE"}

        signal_record = SignalRecord(
            pair=signal.pair,
            interval=signal.interval,
            open_time=signal.open_time,
            direction=signal.direction,
            score=signal.score,
            entry=signal.entry,
            stop_loss=signal.stop_loss,
            take_profit_1=signal.take_profit_1,
            take_profit_2=signal.take_profit_2,
            take_profit_3=signal.take_profit_3,
            payload=signal.to_dict(),
        )
        if self.storage.has_signal(signal.pair, signal.interval, signal.open_time):
            if open_position is not None:
                return {"pair": pair_config.pair, "signal": signal.direction, "action": "SKIP_EXISTING_POSITION"}
            return {"pair": pair_config.pair, "signal": signal.direction, "action": "SKIP_DUPLICATE_SIGNAL"}
        self.storage.save_signal(signal_record)

        if open_position is None:
            decision = self.risk_manager.evaluate_signal(signal, self.storage.list_open_positions())
            if not decision.approved:
                self.logger.info("signal_rejected pair=%s reason=%s", signal.pair, decision.reason)
                return {"pair": pair_config.pair, "signal": signal.direction, "action": "REJECTED", "reason": decision.reason}

            position = self.order_manager.open_position(signal, decision.size)
            return {
                "pair": pair_config.pair,
                "signal": signal.direction,
                "action": "OPENED",
                "quantity": position.quantity,
            }

        return {"pair": pair_config.pair, "signal": signal.direction, "action": "IGNORED"}

    def _generate_signal(self, pair_config: TradingPairConfig, strategy_config: StrategyConfig, candles: list[Candle]):
        htf_bias_lookup = {}
        if strategy_config.htf_interval:
            htf_candles = self.market_data_provider.get_candles(
                pair=pair_config.pair,
                interval=strategy_config.htf_interval,
                limit=max(100, pair_config.candle_limit // 2),
            )
            htf_bias_lookup = build_htf_bias_lookup(candles, htf_candles, strategy_config)
        return generate_precision_sniper_signal(candles, config=strategy_config, htf_bias_lookup=htf_bias_lookup)

    def _process_open_position(self, position: PositionState, candle: Candle) -> None:
        if candle.close_time <= position.last_candle_close_time:
            return

        exit_price = None
        exit_reason = None
        if position.direction == "LONG":
            if candle.low <= position.stop_loss:
                exit_price = position.stop_loss
                exit_reason = "STOP_LOSS"
            elif candle.high >= position.take_profit_3:
                exit_price = position.take_profit_3
                exit_reason = "TAKE_PROFIT_3"
            elif candle.high >= position.take_profit_2:
                exit_price = position.take_profit_2
                exit_reason = "TAKE_PROFIT_2"
            elif candle.high >= position.take_profit_1:
                exit_price = position.take_profit_1
                exit_reason = "TAKE_PROFIT_1"
        else:
            if candle.high >= position.stop_loss:
                exit_price = position.stop_loss
                exit_reason = "STOP_LOSS"
            elif candle.low <= position.take_profit_3:
                exit_price = position.take_profit_3
                exit_reason = "TAKE_PROFIT_3"
            elif candle.low <= position.take_profit_2:
                exit_price = position.take_profit_2
                exit_reason = "TAKE_PROFIT_2"
            elif candle.low <= position.take_profit_1:
                exit_price = position.take_profit_1
                exit_reason = "TAKE_PROFIT_1"

        position.last_candle_close_time = candle.close_time
        if exit_price is None:
            self.storage.upsert_position(position)
            return

        fill = FillRecord(
            time=candle.close_time,
            price=round(exit_price, 6),
            quantity=round(position.remaining_quantity, 8),
            reason=exit_reason,
        )
        position.fills.append(fill)
        position.realized_pnl = round(_compute_pnl(position.direction, position.entry_price, exit_price, position.remaining_quantity), 6)
        position.remaining_quantity = 0.0
        self.order_manager.close_position(position)


def _compute_pnl(direction: str, entry_price: float, exit_price: float, quantity: float) -> float:
    if direction == "LONG":
        return (exit_price - entry_price) * quantity
    return (entry_price - exit_price) * quantity
