import os
import uuid
import time
import ccxt
import configparser
from .logging_utils import log_and_print
from . import globals as G
from .models import BotConfig, ProcessState
from .exchange_client import load_config, connect_exchange, getPerpetualSymbols, retry_ccxt, get_target_symbol_balance
from .portfolio import setup_portfolio
from .rebalance_flow import rebalance
from .orders import handle_order_status, cancel_all_orders

PARAMETER_FILE = os.path.join(os.path.dirname(__file__), "..", G.CONFIG_FOLDER, "rebalance_parameters.ini")

def save_config(config: BotConfig):
    G.UNIQUE_KEY = uuid.uuid4().hex[:8]
    log_and_print(f"🔑 Bot Key: {G.UNIQUE_KEY}", "info")
    config_parser = configparser.ConfigParser()
    config_parser['bot'] = {
        'symbol_futures': config.symbol_futures,
        'rebalance_gap': str(config.rebalance_gap),
        'short_target_ratio': str(config.short_target_ratio),
        'interval_seconds': str(config.interval_seconds),
        'max_leverage': str(config.max_leverage),
        'initial_asset': str(config.initial_asset)
    }
    os.makedirs(os.path.join(os.path.dirname(__file__), "..", G.CONFIG_FOLDER), exist_ok=True)
    path = os.path.join(os.path.dirname(__file__), "..", G.CONFIG_FOLDER, f"rebalance_parameters_{G.UNIQUE_KEY}.ini")
    with open(path, 'w') as f:
        config_parser.write(f)
    log_and_print(f"✅ Configuration saved to {path}", "info")
    global PARAMETER_FILE
    PARAMETER_FILE = path

def load_config_from_file(file_path: str, force_update: bool = False) -> BotConfig:
    config_parser = configparser.ConfigParser()
    if not os.path.exists(file_path):
        log_and_print(f"❌ Configuration file {file_path} not found. Stopping bot...", "error")
        raise SystemExit(1)
    config_parser.read(file_path)
    if 'bot' not in config_parser:
        log_and_print(f"❌ Configuration file {file_path} is missing 'bot' section. Stopping bot...", "error")
        raise SystemExit(1)
    config = config_parser['bot']
    bot_config = BotConfig(
        symbol_futures=config.get('symbol_futures', 'BTC/USD:BTC'),
        rebalance_gap=float(config.get('rebalance_gap', 0.01)),
        short_target_ratio=float(config.get('short_target_ratio', 0.5)),
        interval_seconds=int(config.get('interval_seconds', 5)),
        max_leverage=float(config.get('max_leverage', 1.0)),
        initial_asset=float(config.get('initial_asset', 0.0))
    )
    log_and_print(f"🔧 Loaded configuration: {bot_config}", "info")
    if force_update:
        update_config_from_file(bot_config)
    return bot_config

def update_config_from_file(config: BotConfig):
    if config.max_leverage <= 0:
        log_and_print("❌ MAX_LEVERAGE must be greater than 0. Stopping bot...", "error")
        raise SystemExit(1)
    if not (0.05 <= config.short_target_ratio <= 0.95):
        log_and_print("❌ SHORT_TARGET_RATIO must be between 0.05 and 0.95. Stopping bot...", "error")
        raise SystemExit(1)
    if config.rebalance_gap <= 0:
        log_and_print("❌ REBALANCE_GAP must be greater than 0. Stopping bot...", "error")
        raise SystemExit(1)
    if config.interval_seconds <= 0:
        log_and_print("❌ INTERVAL_SECONDS must be greater than 0. Stopping bot...", "error")
        raise SystemExit(1)

    G.REBALANCE_GAP = config.rebalance_gap
    G.SHORT_TARGET_RATIO = config.short_target_ratio
    G.INTERVAL_SECONDS = config.interval_seconds
    G.MAX_LEVERAGE = config.max_leverage
    G.SYMBOL_FUTURES = config.symbol_futures
    G.SYMBOL = G.SYMBOL_FUTURES.split(':')[-1]
    log_and_print(f"🔄 Updated global parameters from config: REBALANCE_GAP={G.REBALANCE_GAP}, SHORT_TARGET_RATIO={G.SHORT_TARGET_RATIO}, INTERVAL_SECONDS={G.INTERVAL_SECONDS}, MAX_LEVERAGE={G.MAX_LEVERAGE}, SYMBOL_FUTURES={G.SYMBOL_FUTURES}", "info")

def get_bot_config_from_terminal() -> BotConfig:
    log_and_print("Insert Key API KEY: ")
    exchange_key = input("Input Exchange Key: ").strip()
    api_key, api_secret = load_config(exchange_key)
    G.CONFIG_KEY = exchange_key
    ex = connect_exchange(api_key, api_secret)
    def get_input(prompt, default, cast_fn=float):
        try:
            user_input = input(f"{prompt} (default = {default}): ").strip()
            return cast_fn(user_input) if user_input else default
        except Exception as e:
            log_and_print(f"⚠️ Invalid input: {e}. Using default = {default}", "warning")
            return default

    log_and_print("Perpetual Futures Symbols:", "info")
    perpetual_symbols = getPerpetualSymbols(ex)
    log_and_print(", ".join(perpetual_symbols) if perpetual_symbols else "No perpetual futures symbols found.", "info")
    symbol_futures = input("SYMBOL_FUTURES (default = 'BTC/USD:BTC'): ").strip() or "BTC/USD:BTC"
    rebalance_gap = get_input("REBALANCE_GAP", 0.01, float)
    short_target_ratio = get_input("SHORT_TARGET_RATIO", 0.5, float)
    interval_seconds = get_input("INTERVAL_SECONDS", 5, int)
    initial_asset_default = 0.0
    if symbol_futures:
        symbol = symbol_futures.split(':')[0].split("/")[0]
        log_and_print(f"Fetching initial asset default value for {symbol}...", "info")
        initial_asset_default = get_target_symbol_balance(ex, symbol)
        log_and_print(f"Initial asset default value set to {initial_asset_default:.6f} {symbol} based on current balance.", "info")
    max_leverage = get_input("MAX_LEVERAGE", 1.0, float)
    initial_asset = get_input("INITIAL_ASSET", initial_asset_default)

    return BotConfig(
        symbol_futures=symbol_futures,
        rebalance_gap=rebalance_gap,
        short_target_ratio=short_target_ratio,
        interval_seconds=interval_seconds,
        max_leverage=max_leverage,
        initial_asset=initial_asset
    )

def run_bot():
    api_key, api_secret = load_config(G.CONFIG_KEY)
    ex = connect_exchange(api_key, api_secret)
    try:
        markets = ex.load_markets()
        if G.SYMBOL_FUTURES not in markets:
            log_and_print(f"❌ SYMBOL_FUTURES '{G.SYMBOL_FUTURES}' not found on exchange. Stopping bot...", "error")
            raise SystemExit(1)
    except Exception as e:
        log_and_print(f"❌ Error loading markets or validating symbol: {e}. Stopping bot...", "error")
        raise SystemExit(1)

    setup_portfolio(ex)
    log_and_print(f"📡 Rebalancing bot started. Running every {G.INTERVAL_SECONDS} seconds...", "info")

    try:
        while True:
            try:
                if G.state == ProcessState.REBALANCING:
                    load_config_from_file(PARAMETER_FILE)
                    rebalance(ex)
                if G.order_ids:
                    handle_order_status(ex)
                time.sleep(G.INTERVAL_SECONDS)
            except ccxt.NetworkError as ne:
                log_and_print(f"🌐 Network error: {ne}. Retrying in 10 seconds...", "warning")
                time.sleep(10)
    except KeyboardInterrupt:
        log_and_print("🛑 Bot stopped by user.", "info")
        cancel_all_orders(ex)
    except ccxt.RateLimitExceeded as re:
        log_and_print(f"⚠️ Rate limit hit: {str(re)}. Retrying in 60 sec...", "warning")
        time.sleep(60)
    except Exception as e:
        log_and_print(f"❌ Unexpected error: {str(e)}", "error")
        cancel_all_orders(ex)
