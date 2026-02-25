# Belevaku Trading Bot V2 (Desktop)

## How to run (Windows)
1. Install Python 3.11+ system-wide.
2. Double-click `run.bat`.
3. The launcher installs dependencies with system pip and starts the desktop app.

## Module map
- `run.bat` - Windows entrypoint for install + run.
- `requirements.txt` - Python dependencies.
- `src/main.py` - app entry module.
- `src/app.py` - ttkbootstrap desktop UI, page routing, wiring, async-safe updates.
- `src/binance_service.py` - Binance Futures watchlist + websocket streams + reconnect/stale handling.
- `src/signal_engine.py` - candle builders, impulse signal engine, reversal meter.
- `src/trade_tools.py` - 8-row trade tools and TP/SL result evaluation.
- `src/demo_trading.py` - realistic paper-trading model using live prices.
- `src/persistence.py` - SQLite trade history + ML schema-versioned CSV logs.
- `src/config.py` - settings/app-state load/save in `data/`.
- `src/logging_service.py` - structured file logging + live UI log queue.
- `src/models.py` - shared dataclasses.
