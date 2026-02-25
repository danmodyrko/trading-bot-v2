from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Callable, Dict, List, Optional

import aiohttp
import websockets


class BinanceFuturesService:
    WS_URL = "wss://fstream.binance.com/stream"
    REST_24H = "https://fapi.binance.com/fapi/v1/ticker/24hr"

    def __init__(self, logger, min_24h_volume_m: float):
        self.logger = logger
        self.min_24h_volume_m = min_24h_volume_m
        self.last_msg_ts = 0.0
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self.symbols: List[str] = []
        self.on_event: Optional[Callable[[Dict[str, Any]], None]] = None

    async def refresh_watchlist(self) -> List[str]:
        async with aiohttp.ClientSession() as session:
            async with session.get(self.REST_24H, timeout=20) as r:
                data = await r.json()
        symbols = []
        for row in data:
            symbol = row.get("symbol", "")
            if not symbol.endswith("USDT"):
                continue
            vol = float(row.get("quoteVolume", 0.0)) / 1_000_000
            if vol >= self.min_24h_volume_m:
                symbols.append(symbol.lower())
        self.symbols = symbols[:40]
        self.logger.info("Watchlist refreshed: %d symbols", len(self.symbols))
        return self.symbols

    async def start(self, on_event: Callable[[Dict[str, Any]], None]) -> None:
        if self._running:
            return
        self.on_event = on_event
        self._running = True
        if not self.symbols:
            await self.refresh_watchlist()
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def _run(self) -> None:
        backoff = 1
        while self._running:
            streams = []
            for sym in self.symbols[:30]:
                streams.append(f"{sym}@aggTrade")
                streams.append(f"{sym}@bookTicker")
            url = f"{self.WS_URL}?streams={'/'.join(streams)}"
            try:
                self.logger.info("Connecting websocket")
                async with websockets.connect(url, ping_interval=15, ping_timeout=10) as ws:
                    self.last_msg_ts = time.time()
                    backoff = 1
                    while self._running:
                        try:
                            msg = await asyncio.wait_for(ws.recv(), timeout=2)
                            payload = json.loads(msg)
                            self.last_msg_ts = time.time()
                            if self.on_event:
                                self.on_event(payload)
                        except asyncio.TimeoutError:
                            if time.time() - self.last_msg_ts > 8:
                                self.logger.warning("stale (>8s)")
                                raise ConnectionError("stale")
            except Exception as exc:
                self.logger.warning("WS reconnect in %ss (%s)", backoff, exc)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)


import contextlib
