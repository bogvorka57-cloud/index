import logging
import json
import os
from datetime import datetime
from config import LOG_FILE

# Ensure the logs directory exists before creating FileHandler
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

# ── Консольный + файловый лог ──────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ]
)
logger = logging.getLogger("signal-bot")


def log_signal(signal, order_result: dict, tp_sl_result: dict):
    """Записать сделку в лог в удобном виде."""
    entry = {
        "time": datetime.utcnow().isoformat(),
        "symbol": signal.symbol,
        "direction": signal.direction,
        "entry_price": signal.entry,
        "tp1": signal.tp1,
        "sl": signal.sl,
        "order": order_result,
        "tp_sl": tp_sl_result,
    }
    logger.info("СДЕЛКА: " + json.dumps(entry, ensure_ascii=False))


def log_error(msg: str):
    logger.error(msg)


def log_info(msg: str):
    logger.info(msg)