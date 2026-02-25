from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Deque, Dict, Optional, Tuple

from .models import Candle, Signal


class CandleBuilder:
    def __init__(self, seconds: int):
        self.seconds = seconds
        self.current: Dict[str, Candle] = {}

    def on_trade(self, symbol: str, ts: float, price: float, qty: float) -> Candle:
        bucket = ts - (ts % self.seconds)
        prev = self.current.get(symbol)
        if prev and prev.open_time == bucket:
            prev.update(price, qty)
            return prev
        new_candle = Candle(symbol=symbol, interval=f"{self.seconds}s", open_time=bucket, open=price, high=price, low=price, close=price, volume=qty)
        self.current[symbol] = new_candle
        return new_candle


@dataclass
class ReversalState:
    start_ts: float
    entry_price: float
    side: str


class ReversalMeter:
    """
    Deterministic formula:
      progress = clamp((abs(price-entry)/entry) / target_pct, 0, 1)
      time_decay = clamp(1 - elapsed/60, 0, 1)
      readiness = int(progress * 100 * time_decay)
    Meter is active for 60 seconds after entry and then inactive.
    """

    def __init__(self, target_pct: float = 0.50):
        self.target_pct = target_pct
        self.state: Dict[str, ReversalState] = {}

    def arm(self, symbol: str, side: str, entry_price: float, ts: float) -> None:
        self.state[symbol] = ReversalState(start_ts=ts, entry_price=entry_price, side=side)

    def readiness(self, symbol: str, price: float, ts: float) -> Tuple[int, bool]:
        s = self.state.get(symbol)
        if not s:
            return 0, False
        elapsed = ts - s.start_ts
        if elapsed > 60:
            return 0, False
        move_pct = abs((price - s.entry_price) / s.entry_price) * 100
        target = max(self.target_pct, 0.01)
        progress = min(max(move_pct / target, 0.0), 1.0)
        time_decay = max(0.0, 1.0 - (elapsed / 60.0))
        return int(progress * 100 * time_decay), True


class ImpulseSignalEngine:
    def __init__(self, cooldown_seconds: int = 10):
        self.trades: Dict[str, Deque[Tuple[float, float]]] = defaultdict(deque)
        self.last_signal_ts: Dict[str, float] = defaultdict(float)
        self.last_direction: Dict[str, str] = {}
        self.cooldown_seconds = cooldown_seconds

    def on_trade(self, symbol: str, ts: float, price: float) -> Optional[Signal]:
        dq = self.trades[symbol]
        dq.append((ts, price))
        while dq and ts - dq[0][0] > 5:
            dq.popleft()
        if len(dq) < 12:
            return None

        first = dq[0][1]
        pct = ((price - first) / first) * 100
        if abs(pct) < 0.22:
            return None

        side = "LONG" if pct > 0 else "SHORT"
        if ts - self.last_signal_ts[symbol] < self.cooldown_seconds:
            return None
        # only stack same direction until opposite direction appears after cooldown
        prev = self.last_direction.get(symbol)
        if prev and prev != side and ts - self.last_signal_ts[symbol] < (self.cooldown_seconds * 2):
            return None

        self.last_signal_ts[symbol] = ts
        self.last_direction[symbol] = side
        return Signal(symbol=symbol, side=side, ts=ts, impulse_pct=pct, trade_count_5s=len(dq), price=price)
