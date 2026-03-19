from __future__ import annotations

from dataclasses import asdict, dataclass, field

from bot.data.market_data import Candle
from bot.strategy.precision_sniper import (
    StrategyConfig,
    build_htf_bias_lookup,
    generate_precision_sniper_signal,
)


@dataclass(frozen=True)
class Fill:
    time: int
    price: float
    size_fraction: float
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Trade:
    direction: str
    entry_time: int
    exit_time: int
    entry_price: float
    exit_price: float
    pnl: float
    pnl_pct: float
    reason: str
    pair: str
    interval: str
    fills: list[Fill]

    def to_dict(self) -> dict:
        data = asdict(self)
        data["fills"] = [fill.to_dict() for fill in self.fills]
        return data


@dataclass(frozen=True)
class BacktestResult:
    pair: str
    interval: str
    bars: int
    trades: int
    wins: int
    losses: int
    win_rate: float
    total_pnl: float
    avg_pnl: float
    total_return_pct: float
    max_drawdown_pct: float
    open_trade_marked: bool
    htf_interval: str | None
    trade_log: list[Trade]

    def to_dict(self) -> dict:
        data = asdict(self)
        data["trade_log"] = [trade.to_dict() for trade in self.trade_log]
        return data


@dataclass
class Position:
    direction: str
    entry_time: int
    entry_price: float
    stop_loss: float
    initial_stop_loss: float
    take_profit_1: float
    take_profit_2: float
    take_profit_3: float
    pair: str
    interval: str
    remaining_size: float = 1.0
    hit_tp1: bool = False
    hit_tp2: bool = False
    hit_tp3: bool = False
    fills: list[Fill] = field(default_factory=list)


def run_precision_sniper_backtest(
    candles: list[Candle],
    config: StrategyConfig | None = None,
    htf_candles: list[Candle] | None = None,
) -> BacktestResult:
    config = config or StrategyConfig()
    if not candles:
        return BacktestResult(
            pair="",
            interval="",
            bars=0,
            trades=0,
            wins=0,
            losses=0,
            win_rate=0.0,
            total_pnl=0.0,
            avg_pnl=0.0,
            total_return_pct=0.0,
            max_drawdown_pct=0.0,
            open_trade_marked=False,
            htf_interval=config.htf_interval,
            trade_log=[],
        )

    trades: list[Trade] = []
    position: Position | None = None
    htf_bias_lookup = build_htf_bias_lookup(candles, htf_candles or [], config) if config.htf_interval else {}
    equity_curve = [0.0]
    realized_equity = 0.0

    for idx in range(1, len(candles)):
        candle = candles[idx]

        if position is not None and candle.open_time > position.entry_time:
            position, closed_trade = _process_position_candle(position, candle, config)
            if closed_trade is not None:
                trades.append(closed_trade)
                realized_equity += closed_trade.pnl
                equity_curve.append(realized_equity)

        if position is not None:
            continue

        signal = generate_precision_sniper_signal(
            candles[:idx],
            config=config,
            htf_bias_lookup=htf_bias_lookup,
        )
        if signal is None:
            continue

        entry_candle = candles[idx]
        entry_price = entry_candle.open
        risk_per_unit = abs(entry_price - signal.stop_loss)
        if risk_per_unit <= 0:
            continue

        if signal.direction == "LONG":
            tp1 = entry_price + (risk_per_unit * config.tp1_rr)
            tp2 = entry_price + (risk_per_unit * config.tp2_rr)
            tp3 = entry_price + (risk_per_unit * config.tp3_rr)
        else:
            tp1 = entry_price - (risk_per_unit * config.tp1_rr)
            tp2 = entry_price - (risk_per_unit * config.tp2_rr)
            tp3 = entry_price - (risk_per_unit * config.tp3_rr)

        position = Position(
            direction=signal.direction,
            entry_time=entry_candle.open_time,
            entry_price=entry_price,
            stop_loss=signal.stop_loss,
            initial_stop_loss=signal.stop_loss,
            take_profit_1=tp1,
            take_profit_2=tp2,
            take_profit_3=tp3,
            pair=signal.pair,
            interval=signal.interval,
        )

    open_trade_marked = False
    if position is not None:
        last_candle = candles[-1]
        closed_trade = _close_all_remaining(
            position=position,
            exit_time=last_candle.close_time,
            exit_price=last_candle.close,
            reason="MARK_TO_MARKET",
        )
        trades.append(closed_trade)
        realized_equity += closed_trade.pnl
        equity_curve.append(realized_equity)
        open_trade_marked = True

    wins = sum(1 for trade in trades if trade.pnl > 0)
    losses = sum(1 for trade in trades if trade.pnl < 0)
    total_pnl = sum(trade.pnl for trade in trades)
    trade_count = len(trades)
    avg_pnl = total_pnl / trade_count if trade_count else 0.0
    win_rate = (wins / trade_count) * 100 if trade_count else 0.0
    start_price = candles[0].open
    total_return_pct = (total_pnl / start_price) * 100 if start_price else 0.0
    max_drawdown_pct = _compute_max_drawdown_pct(equity_curve, start_price)

    return BacktestResult(
        pair=candles[0].pair,
        interval=candles[0].interval,
        bars=len(candles),
        trades=trade_count,
        wins=wins,
        losses=losses,
        win_rate=round(win_rate, 2),
        total_pnl=round(total_pnl, 6),
        avg_pnl=round(avg_pnl, 6),
        total_return_pct=round(total_return_pct, 4),
        max_drawdown_pct=round(max_drawdown_pct, 4),
        open_trade_marked=open_trade_marked,
        htf_interval=config.htf_interval,
        trade_log=trades,
    )


def _process_position_candle(
    position: Position,
    candle: Candle,
    config: StrategyConfig,
) -> tuple[Position | None, Trade | None]:
    stop_before_ratcheting = position.stop_loss

    tp_events = _tp_events(position, candle, config)
    for reason, price, size_fraction in tp_events:
        if position.remaining_size <= 0:
            break
        actual_size = min(size_fraction, position.remaining_size)
        if actual_size <= 0:
            continue
        position.fills.append(
            Fill(
                time=candle.open_time,
                price=round(price, 6),
                size_fraction=round(actual_size, 4),
                reason=reason,
            )
        )
        position.remaining_size = round(position.remaining_size - actual_size, 10)
        if reason == "TAKE_PROFIT_1":
            position.hit_tp1 = True
            if config.trail_to_break_even_after_tp1:
                position.stop_loss = position.entry_price
        elif reason == "TAKE_PROFIT_2":
            position.hit_tp2 = True
            if config.trail_to_tp1_after_tp2:
                position.stop_loss = position.take_profit_1
        elif reason == "TAKE_PROFIT_3":
            position.hit_tp3 = True
            if config.trail_to_tp2_after_tp3:
                position.stop_loss = position.take_profit_2

    if position.remaining_size <= 0:
        return None, _finalize_trade(position, candle.open_time, "ALL_TARGETS_FILLED")

    if _stop_hit(position.direction, stop_before_ratcheting, candle):
        position.fills.append(
            Fill(
                time=candle.open_time,
                price=round(stop_before_ratcheting, 6),
                size_fraction=round(position.remaining_size, 4),
                reason="STOP_LOSS",
            )
        )
        position.remaining_size = 0.0
        return None, _finalize_trade(position, candle.open_time, "STOP_LOSS")

    return position, None


def _tp_events(position: Position, candle: Candle, config: StrategyConfig) -> list[tuple[str, float, float]]:
    events: list[tuple[str, float, float]] = []
    if position.direction == "LONG":
        if not position.hit_tp1 and candle.high >= position.take_profit_1:
            events.append(("TAKE_PROFIT_1", position.take_profit_1, config.tp1_size_fraction))
        if not position.hit_tp2 and candle.high >= position.take_profit_2:
            events.append(("TAKE_PROFIT_2", position.take_profit_2, config.tp2_size_fraction))
        if not position.hit_tp3 and candle.high >= position.take_profit_3:
            events.append(("TAKE_PROFIT_3", position.take_profit_3, config.tp3_size_fraction))
    else:
        if not position.hit_tp1 and candle.low <= position.take_profit_1:
            events.append(("TAKE_PROFIT_1", position.take_profit_1, config.tp1_size_fraction))
        if not position.hit_tp2 and candle.low <= position.take_profit_2:
            events.append(("TAKE_PROFIT_2", position.take_profit_2, config.tp2_size_fraction))
        if not position.hit_tp3 and candle.low <= position.take_profit_3:
            events.append(("TAKE_PROFIT_3", position.take_profit_3, config.tp3_size_fraction))
    return events


def _stop_hit(direction: str, stop_price: float, candle: Candle) -> bool:
    if direction == "LONG":
        return candle.low <= stop_price
    return candle.high >= stop_price


def _close_all_remaining(position: Position, exit_time: int, exit_price: float, reason: str) -> Trade:
    if position.remaining_size > 0:
        position.fills.append(
            Fill(
                time=exit_time,
                price=round(exit_price, 6),
                size_fraction=round(position.remaining_size, 4),
                reason=reason,
            )
        )
        position.remaining_size = 0.0
    return _finalize_trade(position, exit_time, reason)


def _finalize_trade(position: Position, exit_time: int, reason: str) -> Trade:
    pnl = 0.0
    weighted_exit = 0.0
    for fill in position.fills:
        if position.direction == "LONG":
            pnl += (fill.price - position.entry_price) * fill.size_fraction
        else:
            pnl += (position.entry_price - fill.price) * fill.size_fraction
        weighted_exit += fill.price * fill.size_fraction

    exit_price = weighted_exit if weighted_exit else position.entry_price
    pnl_pct = (pnl / position.entry_price) * 100 if position.entry_price else 0.0
    return Trade(
        direction=position.direction,
        entry_time=position.entry_time,
        exit_time=exit_time,
        entry_price=round(position.entry_price, 6),
        exit_price=round(exit_price, 6),
        pnl=round(pnl, 6),
        pnl_pct=round(pnl_pct, 4),
        reason=reason,
        pair=position.pair,
        interval=position.interval,
        fills=list(position.fills),
    )


def _compute_max_drawdown_pct(equity_curve: list[float], start_price: float) -> float:
    if not equity_curve or start_price == 0:
        return 0.0
    peak = equity_curve[0]
    max_drawdown = 0.0
    for equity in equity_curve:
        if equity > peak:
            peak = equity
        drawdown = peak - equity
        if drawdown > max_drawdown:
            max_drawdown = drawdown
    return (max_drawdown / start_price) * 100
