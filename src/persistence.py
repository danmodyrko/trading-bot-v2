from __future__ import annotations

import csv
import sqlite3
from pathlib import Path
from typing import Dict, Iterable, List

from .config import DATA_DIR, ensure_data_dir

DB_PATH = DATA_DIR / "trades.db"
ML_LOG_PATH = DATA_DIR / "logs" / "ml_training.csv"
ML_SCHEMA_VERSION = 2


class Persistence:
    def __init__(self) -> None:
        ensure_data_dir()
        self.conn = sqlite3.connect(DB_PATH)
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT,
                symbol TEXT,
                side TEXT,
                price REAL,
                size REAL,
                status TEXT,
                mode TEXT
            )
            """
        )
        self.conn.commit()

    def add_trade(self, trade: Dict) -> None:
        self.conn.execute(
            "INSERT INTO trades(ts, symbol, side, price, size, status, mode) VALUES(?,?,?,?,?,?,?)",
            (
                trade.get("ts"),
                trade.get("symbol"),
                trade.get("side"),
                trade.get("price"),
                trade.get("size"),
                trade.get("status"),
                trade.get("mode", "SIMPLE"),
            ),
        )
        self.conn.commit()

    def list_trades(self, limit: int = 500) -> List[tuple]:
        cur = self.conn.execute(
            "SELECT ts,symbol,side,price,size,status,mode FROM trades ORDER BY id DESC LIMIT ?", (limit,)
        )
        return cur.fetchall()


def append_ml_log(rows: Iterable[Dict]) -> None:
    ensure_data_dir()
    file_exists = Path(ML_LOG_PATH).exists()
    with open(ML_LOG_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "schema_version",
                "ts",
                "symbol",
                "side",
                "impulse_pct",
                "mfe_pct",
                "target_retrace_pct",
                "win",
            ],
        )
        if not file_exists:
            writer.writeheader()
        for row in rows:
            writer.writerow({"schema_version": ML_SCHEMA_VERSION, **row})


def model_winrate() -> float:
    if not Path(ML_LOG_PATH).exists():
        return 0.0
    wins = 0
    total = 0
    with open(ML_LOG_PATH, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            total += 1
            win_value = row.get("win")
            if win_value is None:
                # legacy schema fallback: derive win from mfe_pct and target
                try:
                    mfe = float(row.get("mfe_pct", "0"))
                    target = float(row.get("target_retrace_pct", "0.5"))
                    if mfe >= target:
                        wins += 1
                except ValueError:
                    pass
            elif str(win_value).lower() in {"1", "true", "yes"}:
                wins += 1
    if total == 0:
        return 0.0
    return (wins / total) * 100
