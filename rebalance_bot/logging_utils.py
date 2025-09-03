import logging
from datetime import datetime
from . import globals as G

logging.basicConfig(
    filename=G.LOG_PATH,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def log_and_print(message: str, level: str = "info"):
    if level.lower() == "info":
        logging.info(f"[{G.UNIQUE_KEY}] " + message)
    elif level.lower() == "warning":
        logging.warning(f"[{G.UNIQUE_KEY}] " + message)
    elif level.lower() == "error":
        logging.error(f"[{G.UNIQUE_KEY}] " + message)
    elif level.lower() == "debug":
        logging.debug(f"[{G.UNIQUE_KEY}] " + message)
    else:
        logging.info(f"[{G.UNIQUE_KEY}] " + message)
    print(f"[{G.UNIQUE_KEY}] " + message)
