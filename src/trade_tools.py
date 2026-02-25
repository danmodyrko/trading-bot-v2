from __future__ import annotations

import time
from datetime import datetime
from typing import List, Optional

from .models import Signal, TradeToolRow


class TradeToolsManager:
    def __init__(self):
        self.rows: List[TradeToolRow] = [TradeToolRow() for _ in range(8)]

    def push_signal(self, signal: Signal, mode: str, tp_pct: float, sl_pct: float) -> int:
        idx = 0
        oldest = float("inf")
        for i, row in enumerate(self.rows):
            if row.symbol == "-":
                idx = i
                break
            if row.entry_deadline < oldest:
                oldest = row.entry_deadline
                idx = i
        self.rows[idx] = TradeToolRow(
            symbol=signal.symbol,
            direction=signal.side,
            entry_text="ENTER NOW",
            entry_deadline=time.time() + 5,
            entry_price=signal.price,
            status="PENDING",
            mode=mode,
            ts=datetime.utcnow().strftime("%H:%M:%S"),
            tp_pct=tp_pct,
            sl_pct=sl_pct,
        )
        return idx

    def update_price(self, symbol: str, price: float) -> None:
        now = time.time()
        for row in self.rows:
            if row.symbol != symbol:
                continue
            if row.entry_text == "ENTER NOW" and now > row.entry_deadline:
                row.entry_text = f"MISSED {datetime.utcnow().strftime('%H:%M:%S')}"
            if row.status == "PENDING" and row.entry_price:
                delta = ((price - row.entry_price) / row.entry_price) * 100
                if row.direction == "SHORT":
                    delta = -delta
                if delta >= row.tp_pct:
                    row.status = "WIN"
                elif delta <= -row.sl_pct:
                    row.status = "LOSS"

    def copy_ticker(self, index: int) -> Optional[str]:
        if 0 <= index < len(self.rows):
            return self.rows[index].symbol if self.rows[index].symbol != "-" else None
        return None
