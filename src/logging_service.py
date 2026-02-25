from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from queue import Queue

from .config import DATA_DIR, ensure_data_dir


class QueueLogHandler(logging.Handler):
    def __init__(self, q: Queue):
        super().__init__()
        self.q = q

    def emit(self, record: logging.LogRecord) -> None:
        self.q.put(self.format(record))


def build_logger(ui_queue: Queue) -> logging.Logger:
    ensure_data_dir()
    logger = logging.getLogger("belevaku")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    stamp = datetime.utcnow().strftime("%Y%m%d")
    file_path = Path(DATA_DIR / "logs" / f"app_{stamp}.log")
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

    fh = logging.FileHandler(file_path, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    qh = QueueLogHandler(ui_queue)
    qh.setFormatter(fmt)
    logger.addHandler(qh)

    return logger
