from .models import ProcessState
from datetime import datetime
import os

UNIQUE_KEY = None
CONFIG_PATAMETERS_FOLDER = "CONFIG_PARAMETERS"
CONFIG_FOLDER = "CONFIG_API_KEY"
LOGS_FOLDER = "LOGS"
CONFIG_KEY = "deribit"
PARAMETER_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", CONFIG_PATAMETERS_FOLDER, "rebalance_parameters.ini"))
CONFIG_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", CONFIG_FOLDER, "config.ini"))
LOG_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", LOGS_FOLDER, f"rebalance_log_{datetime.now().strftime('%Y%m%d')}.log"))

SYMBOL_FUTURES = "BTC/USD:BTC"
SYMBOL = "BTC"
REBALANCE_GAP = 0.01
SHORT_TARGET_RATIO = 0.5
INTERVAL_SECONDS = 5
MAX_LEVERAGE = 1.0

order_ids = []
state = ProcessState.REBALANCING
initial_balance_asset = 0.0
current_balance_asset = 0.0
initial_short_usd = 0.0
current_short_usd = 0.0
