from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Candle:
    symbol: str
    interval: str
    open_time: float
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

    def update(self, price: float, qty: float) -> None:
        self.high = max(self.high, price)
        self.low = min(self.low, price)
        self.close = price
        self.volume += qty


@dataclass
class Signal:
    symbol: str
    side: str
    ts: float
    impulse_pct: float
    trade_count_5s: int
    price: float


@dataclass
class TradeToolRow:
    symbol: str = "-"
    direction: str = "-"
    entry_text: str = "-"
    entry_deadline: float = 0.0
    entry_price: float = 0.0
    status: str = "PENDING"
    mode: str = "SIMPLE"
    ts: str = "-"
    tp_pct: float = 0.5
    sl_pct: float = 0.3


@dataclass
class Position:
    symbol: str
    side: str
    size_usdt: float
    entry_price: float
    opened_at: datetime = field(default_factory=datetime.utcnow)
    closed: bool = False
    close_price: Optional[float] = None

    def pnl_pct(self, mark_price: float) -> float:
        if self.side == "LONG":
            return (mark_price - self.entry_price) / self.entry_price * 100
        return (self.entry_price - mark_price) / self.entry_price * 100
