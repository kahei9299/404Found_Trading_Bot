from __future__ import annotations

import math
from dataclasses import asdict, dataclass

from bot.data.market_data import Candle


@dataclass(frozen=True)
class StrategyConfig:
    ema_fast_length: int = 9
    ema_slow_length: int = 21
    ema_trend_length: int = 55
    rsi_length: int = 13
    atr_length: int = 14
    adx_length: int = 14
    volume_sma_length: int = 20
    min_confluence_score: float = 5.0
    atr_sl_multiplier: float = 1.5
    tp1_rr: float = 1.0
    tp2_rr: float = 2.0
    tp3_rr: float = 3.0
    swing_lookback: int = 10
    structure_sl_enabled: bool = True
    htf_interval: str | None = None
    htf_weight: float = 1.5
    close_above_fast_weight: float = 0.5
    volume_multiplier: float = 1.2
    adx_threshold: float = 20.0
    min_stop_atr_distance: float = 0.5
    structure_atr_padding: float = 0.2
    tp1_size_fraction: float = 0.33
    tp2_size_fraction: float = 0.33
    tp3_size_fraction: float = 0.34
    trail_to_break_even_after_tp1: bool = True
    trail_to_tp1_after_tp2: bool = True
    trail_to_tp2_after_tp3: bool = True


@dataclass(frozen=True)
class SignalResult:
    direction: str
    score: float
    entry: float
    stop_loss: float
    risk_per_unit: float
    take_profit_1: float
    take_profit_2: float
    take_profit_3: float
    pair: str
    interval: str
    source: str
    source_symbol: str
    open_time: int
    reasons: dict[str, bool]
    metrics: dict[str, float | str]

    def to_dict(self) -> dict:
        return asdict(self)


def infer_htf_interval(interval: str) -> str | None:
    mapping = {
        "1m": "5m",
        "3m": "15m",
        "5m": "15m",
        "15m": "1h",
        "30m": "2h",
        "1h": "4h",
        "2h": "6h",
        "4h": "1d",
        "6h": "1d",
        "8h": "1d",
        "12h": "1d",
        "1d": "1w",
        "3d": "1w",
        "1w": "1M",
    }
    return mapping.get(interval)


def build_htf_bias_lookup(
    base_candles: list[Candle],
    htf_candles: list[Candle],
    config: StrategyConfig | None = None,
) -> dict[int, str]:
    config = config or StrategyConfig()
    if not base_candles or not htf_candles:
        return {}

    htf_closes = [c.close for c in htf_candles]
    htf_fast = _ema(htf_closes, config.ema_fast_length)
    htf_slow = _ema(htf_closes, config.ema_slow_length)

    lookup: dict[int, str] = {}
    htf_idx = 0
    current_bias = "NEUTRAL"
    for candle in base_candles:
        while htf_idx < len(htf_candles) and htf_candles[htf_idx].close_time <= candle.close_time:
            fast = htf_fast[htf_idx]
            slow = htf_slow[htf_idx]
            if fast is not None and slow is not None:
                if fast > slow:
                    current_bias = "BULLISH"
                elif fast < slow:
                    current_bias = "BEARISH"
                else:
                    current_bias = "NEUTRAL"
            htf_idx += 1
        lookup[candle.open_time] = current_bias
    return lookup


def generate_precision_sniper_signal(
    candles: list[Candle],
    config: StrategyConfig | None = None,
    htf_bias_lookup: dict[int, str] | None = None,
) -> SignalResult | None:
    config = config or StrategyConfig()
    if len(candles) < _required_history(config):
        return None

    closes = [c.close for c in candles]
    highs = [c.high for c in candles]
    lows = [c.low for c in candles]
    volumes = [c.volume for c in candles]

    ema_fast = _ema(closes, config.ema_fast_length)
    ema_slow = _ema(closes, config.ema_slow_length)
    ema_trend = _ema(closes, config.ema_trend_length)
    rsi = _rsi(closes, config.rsi_length)
    macd_line, macd_signal, macd_hist = _macd(closes)
    atr = _atr(highs, lows, closes, config.atr_length)
    plus_di, minus_di, adx = _adx(highs, lows, closes, config.adx_length)
    volume_sma = _sma(volumes, config.volume_sma_length)
    vwap = _session_vwap(candles)

    idx = len(candles) - 1
    prev = idx - 1
    htf_bias = (htf_bias_lookup or {}).get(candles[idx].open_time, "NEUTRAL")

    required_values = [
        ema_fast[idx], ema_slow[idx], ema_trend[idx], rsi[idx], macd_line[idx],
        macd_signal[idx], macd_hist[idx], atr[idx], plus_di[idx], minus_di[idx],
        adx[idx], volume_sma[idx], vwap[idx], ema_fast[prev], ema_slow[prev],
    ]
    if any(value is None for value in required_values):
        return None

    bullish_reasons = {
        "ema_fast_gt_slow": ema_fast[idx] > ema_slow[idx],
        "close_gt_ema_trend": closes[idx] > ema_trend[idx],
        "rsi_bull_zone": 50 < rsi[idx] < 75,
        "macd_hist_positive": macd_hist[idx] > 0,
        "macd_line_gt_signal": macd_line[idx] > macd_signal[idx],
        "close_gt_vwap": closes[idx] > vwap[idx],
        "volume_gt_sma_mult": volumes[idx] > volume_sma[idx] * config.volume_multiplier,
        "adx_bull_pressure": adx[idx] > config.adx_threshold and plus_di[idx] > minus_di[idx],
        "htf_bias_bull": htf_bias == "BULLISH" if config.htf_interval else True,
        "close_gt_ema_fast": closes[idx] > ema_fast[idx],
    }
    bearish_reasons = {
        "ema_fast_lt_slow": ema_fast[idx] < ema_slow[idx],
        "close_lt_ema_trend": closes[idx] < ema_trend[idx],
        "rsi_bear_zone": 25 < rsi[idx] < 50,
        "macd_hist_negative": macd_hist[idx] < 0,
        "macd_line_lt_signal": macd_line[idx] < macd_signal[idx],
        "close_lt_vwap": closes[idx] < vwap[idx],
        "volume_gt_sma_mult": volumes[idx] > volume_sma[idx] * config.volume_multiplier,
        "adx_bear_pressure": adx[idx] > config.adx_threshold and minus_di[idx] > plus_di[idx],
        "htf_bias_bear": htf_bias == "BEARISH" if config.htf_interval else True,
        "close_lt_ema_fast": closes[idx] < ema_fast[idx],
    }

    bullish_score = _score(bullish_reasons, config)
    bearish_score = _score(bearish_reasons, config)

    bull_cross = ema_fast[prev] <= ema_slow[prev] and ema_fast[idx] > ema_slow[idx]
    bear_cross = ema_fast[prev] >= ema_slow[prev] and ema_fast[idx] < ema_slow[idx]
    bull_trigger = bull_cross and closes[idx] > ema_fast[idx] and closes[idx] > ema_slow[idx] and bullish_score >= config.min_confluence_score
    bear_trigger = bear_cross and closes[idx] < ema_fast[idx] and closes[idx] < ema_slow[idx] and bearish_score >= config.min_confluence_score

    if bull_trigger and not bear_trigger:
        return _build_signal("LONG", candles, idx, atr[idx], config, bullish_score, bullish_reasons, htf_bias)
    if bear_trigger and not bull_trigger:
        return _build_signal("SHORT", candles, idx, atr[idx], config, bearish_score, bearish_reasons, htf_bias)
    return None


def _build_signal(
    direction: str,
    candles: list[Candle],
    idx: int,
    atr_value: float,
    config: StrategyConfig,
    score: float,
    reasons: dict[str, bool],
    htf_bias: str,
) -> SignalResult:
    entry = candles[idx].close
    stop_loss = _calculate_stop_loss(direction, candles, idx, atr_value, config)
    risk_per_unit = abs(entry - stop_loss)

    if direction == "LONG":
        tp1 = entry + risk_per_unit * config.tp1_rr
        tp2 = entry + risk_per_unit * config.tp2_rr
        tp3 = entry + risk_per_unit * config.tp3_rr
    else:
        tp1 = entry - risk_per_unit * config.tp1_rr
        tp2 = entry - risk_per_unit * config.tp2_rr
        tp3 = entry - risk_per_unit * config.tp3_rr

    candle = candles[idx]
    return SignalResult(
        direction=direction,
        score=round(score, 2),
        entry=entry,
        stop_loss=stop_loss,
        risk_per_unit=risk_per_unit,
        take_profit_1=tp1,
        take_profit_2=tp2,
        take_profit_3=tp3,
        pair=candle.pair,
        interval=candle.interval,
        source=candle.source,
        source_symbol=candle.source_symbol,
        open_time=candle.open_time,
        reasons=reasons,
        metrics={
            "atr": round(atr_value, 6),
            "htf_bias": htf_bias,
        },
    )


def _calculate_stop_loss(
    direction: str,
    candles: list[Candle],
    idx: int,
    atr_value: float,
    config: StrategyConfig,
) -> float:
    entry = candles[idx].close
    atr_stop = entry - atr_value * config.atr_sl_multiplier if direction == "LONG" else entry + atr_value * config.atr_sl_multiplier
    if not config.structure_sl_enabled:
        return atr_stop

    start = max(0, idx - config.swing_lookback + 1)
    swing_lows = [c.low for c in candles[start:idx + 1]]
    swing_highs = [c.high for c in candles[start:idx + 1]]
    padding = atr_value * config.structure_atr_padding
    minimum_distance = atr_value * config.min_stop_atr_distance

    if direction == "LONG":
        structure_stop = min(swing_lows) - padding
        stop_loss = max(structure_stop, atr_stop)
        max_allowed_stop = entry - minimum_distance
        return min(stop_loss, max_allowed_stop)

    structure_stop = max(swing_highs) + padding
    stop_loss = min(structure_stop, atr_stop)
    min_allowed_stop = entry + minimum_distance
    return max(stop_loss, min_allowed_stop)


def _score(reasons: dict[str, bool], config: StrategyConfig) -> float:
    score = 0.0
    for key, passed in reasons.items():
        if not passed:
            continue
        if key.startswith("htf_bias"):
            score += config.htf_weight
        elif key.endswith("ema_fast"):
            score += config.close_above_fast_weight
        else:
            score += 1.0
    return score


def _required_history(config: StrategyConfig) -> int:
    return max(
        config.ema_trend_length + 2,
        config.rsi_length + 2,
        config.atr_length + 2,
        config.adx_length * 3,
        config.volume_sma_length + 2,
        config.swing_lookback + 2,
        60,
    )


def _sma(values: list[float], length: int) -> list[float | None]:
    result: list[float | None] = [None] * len(values)
    if length <= 0:
        return result
    window_sum = 0.0
    for idx, value in enumerate(values):
        window_sum += value
        if idx >= length:
            window_sum -= values[idx - length]
        if idx >= length - 1:
            result[idx] = window_sum / length
    return result


def _ema(values: list[float], length: int) -> list[float | None]:
    result: list[float | None] = [None] * len(values)
    if len(values) < length:
        return result
    multiplier = 2 / (length + 1)
    seed = sum(values[:length]) / length
    result[length - 1] = seed
    ema_value = seed
    for idx in range(length, len(values)):
        ema_value = (values[idx] - ema_value) * multiplier + ema_value
        result[idx] = ema_value
    return result


def _rsi(values: list[float], length: int) -> list[float | None]:
    result: list[float | None] = [None] * len(values)
    if len(values) <= length:
        return result

    gains = []
    losses = []
    for idx in range(1, len(values)):
        change = values[idx] - values[idx - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))

    avg_gain = sum(gains[:length]) / length
    avg_loss = sum(losses[:length]) / length
    rs = math.inf if avg_loss == 0 else avg_gain / avg_loss
    result[length] = 100 - (100 / (1 + rs))

    for idx in range(length + 1, len(values)):
        gain = gains[idx - 1]
        loss = losses[idx - 1]
        avg_gain = ((avg_gain * (length - 1)) + gain) / length
        avg_loss = ((avg_loss * (length - 1)) + loss) / length
        rs = math.inf if avg_loss == 0 else avg_gain / avg_loss
        result[idx] = 100 - (100 / (1 + rs))
    return result


def _macd(values: list[float], fast: int = 12, slow: int = 26, signal: int = 9):
    fast_ema = _ema(values, fast)
    slow_ema = _ema(values, slow)
    macd_line: list[float | None] = [None] * len(values)
    for idx in range(len(values)):
        if fast_ema[idx] is not None and slow_ema[idx] is not None:
            macd_line[idx] = fast_ema[idx] - slow_ema[idx]

    macd_values = [value for value in macd_line if value is not None]
    macd_signal_seed = _ema(macd_values, signal)
    signal_line: list[float | None] = [None] * len(values)
    hist: list[float | None] = [None] * len(values)

    seed_idx = 0
    for idx, value in enumerate(macd_line):
        if value is None:
            continue
        signal_value = macd_signal_seed[seed_idx]
        signal_line[idx] = signal_value
        if signal_value is not None:
            hist[idx] = value - signal_value
        seed_idx += 1
    return macd_line, signal_line, hist


def _atr(highs: list[float], lows: list[float], closes: list[float], length: int) -> list[float | None]:
    tr_values = [0.0] * len(highs)
    for idx in range(1, len(highs)):
        tr_values[idx] = max(
            highs[idx] - lows[idx],
            abs(highs[idx] - closes[idx - 1]),
            abs(lows[idx] - closes[idx - 1]),
        )

    result: list[float | None] = [None] * len(highs)
    if len(highs) <= length:
        return result

    atr_value = sum(tr_values[1:length + 1]) / length
    result[length] = atr_value
    for idx in range(length + 1, len(highs)):
        atr_value = ((atr_value * (length - 1)) + tr_values[idx]) / length
        result[idx] = atr_value
    return result


def _adx(highs: list[float], lows: list[float], closes: list[float], length: int):
    plus_dm = [0.0] * len(highs)
    minus_dm = [0.0] * len(highs)
    tr_values = [0.0] * len(highs)

    for idx in range(1, len(highs)):
        up_move = highs[idx] - highs[idx - 1]
        down_move = lows[idx - 1] - lows[idx]
        plus_dm[idx] = up_move if up_move > down_move and up_move > 0 else 0.0
        minus_dm[idx] = down_move if down_move > up_move and down_move > 0 else 0.0
        tr_values[idx] = max(
            highs[idx] - lows[idx],
            abs(highs[idx] - closes[idx - 1]),
            abs(lows[idx] - closes[idx - 1]),
        )

    plus_di: list[float | None] = [None] * len(highs)
    minus_di: list[float | None] = [None] * len(highs)
    adx: list[float | None] = [None] * len(highs)
    if len(highs) <= (length * 2):
        return plus_di, minus_di, adx

    smoothed_tr = sum(tr_values[1:length + 1])
    smoothed_plus_dm = sum(plus_dm[1:length + 1])
    smoothed_minus_dm = sum(minus_dm[1:length + 1])

    dx_values: list[float] = []
    for idx in range(length, len(highs)):
        if idx > length:
            smoothed_tr = smoothed_tr - (smoothed_tr / length) + tr_values[idx]
            smoothed_plus_dm = smoothed_plus_dm - (smoothed_plus_dm / length) + plus_dm[idx]
            smoothed_minus_dm = smoothed_minus_dm - (smoothed_minus_dm / length) + minus_dm[idx]

        if smoothed_tr == 0:
            plus = 0.0
            minus = 0.0
        else:
            plus = 100 * (smoothed_plus_dm / smoothed_tr)
            minus = 100 * (smoothed_minus_dm / smoothed_tr)
        plus_di[idx] = plus
        minus_di[idx] = minus
        di_sum = plus + minus
        dx = 0.0 if di_sum == 0 else 100 * abs(plus - minus) / di_sum
        dx_values.append(dx)

        if len(dx_values) == length:
            adx[idx] = sum(dx_values) / length
        elif len(dx_values) > length and adx[idx - 1] is not None:
            adx[idx] = ((adx[idx - 1] * (length - 1)) + dx) / length
    return plus_di, minus_di, adx


def _session_vwap(candles: list[Candle]) -> list[float | None]:
    result: list[float | None] = [None] * len(candles)
    cumulative_pv = 0.0
    cumulative_volume = 0.0
    current_day = None

    for idx, candle in enumerate(candles):
        day_bucket = candle.open_time // 86_400_000
        if day_bucket != current_day:
            current_day = day_bucket
            cumulative_pv = 0.0
            cumulative_volume = 0.0

        typical_price = (candle.high + candle.low + candle.close) / 3
        cumulative_pv += typical_price * candle.volume
        cumulative_volume += candle.volume
        if cumulative_volume > 0:
            result[idx] = cumulative_pv / cumulative_volume
    return result
