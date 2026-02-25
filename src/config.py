from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

DATA_DIR = Path("data")
SETTINGS_FILE = DATA_DIR / "settings.json"
APP_STATE_FILE = DATA_DIR / "app_state.json"

DEFAULT_SETTINGS: Dict[str, Any] = {
    "mode": "DEMO",
    "exchange": "BINANCE_FUTURES",
    "min_24h_volume_m": 25.0,
    "api": {
        "real_key": "",
        "real_secret": "",
        "demo_key": "",
        "demo_secret": "",
        "real_unlock": False,
    },
    "strategy": {
        "algorithm": "Impulse Scalp (V1)",
        "entry_mode": "SIMPLE",
        "ml_tolerance": 0.50,
        "target_retrace_pct": 0.50,
    },
    "risk_profile": "MEDIUM",
    "risk": {
        "position_size_usdt": 100.0,
        "stop_loss_pct": 0.30,
        "take_profit_pct": 0.50,
    },
}

DEFAULT_APP_STATE: Dict[str, Any] = {
    "geometry": "1380x860+100+60",
    "page": "TERMINAL",
}


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "logs").mkdir(parents=True, exist_ok=True)


def _load_json(path: Path, default: Dict[str, Any]) -> Dict[str, Any]:
    if not path.exists():
        return default.copy()
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default.copy()


def _save_json(path: Path, payload: Dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_settings() -> Dict[str, Any]:
    ensure_data_dir()
    return _load_json(SETTINGS_FILE, DEFAULT_SETTINGS)


def save_settings(settings: Dict[str, Any]) -> None:
    ensure_data_dir()
    _save_json(SETTINGS_FILE, settings)


def load_app_state() -> Dict[str, Any]:
    ensure_data_dir()
    return _load_json(APP_STATE_FILE, DEFAULT_APP_STATE)


def save_app_state(state: Dict[str, Any]) -> None:
    ensure_data_dir()
    _save_json(APP_STATE_FILE, state)
