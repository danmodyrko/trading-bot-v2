from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List

from .models import Position


@dataclass
class PaperAccount:
    wallet_balance: float = 1000.0
    positions: List[Position] = field(default_factory=list)
    active_orders: int = 0

    def place_market(self, symbol: str, side: str, price: float, size_usdt: float) -> Position:
        pos = Position(symbol=symbol, side=side, size_usdt=size_usdt, entry_price=price, opened_at=datetime.utcnow())
        self.positions.append(pos)
        return pos

    def mark(self, prices: Dict[str, float]) -> float:
        pnl = 0.0
        for p in self.positions:
            mark = prices.get(p.symbol)
            if mark:
                pnl += p.size_usdt * (p.pnl_pct(mark) / 100.0)
        return pnl
