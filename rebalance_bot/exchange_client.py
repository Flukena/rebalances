import time
import ccxt
import configparser
from functools import wraps
from .logging_utils import log_and_print
from . import globals as G

def retry_ccxt(max_retries=3, delay=2):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except (ccxt.NetworkError, ccxt.ExchangeNotAvailable, ccxt.RequestTimeout) as e:
                    log_and_print(f"⚠️ Retry {attempt+1}/{max_retries} for {func.__name__}: {e}", "warning")
                    time.sleep(delay)
            raise Exception(f"Failed after {max_retries} retries: {func.__name__}")
        return wrapper
    return decorator

def load_config(key):
    config = configparser.ConfigParser()
    config.read(G.CONFIG_PATH)
    return config[key][f'{key}_API_KEY'], config[key][f'{key}_API_SECRET']

def connect_exchange(api_key, api_secret):
    exchange = ccxt.deribit({'apiKey': api_key, 'secret': api_secret, 'enableRateLimit': True})
    try:
        exchange.fetch_balance()
        log_and_print("✅ Successfully connected to Deribit exchange", "info")
    except Exception as e:
        log_and_print(f"❌ Failed to connect to Deribit: {e}", "error")
    return exchange

@retry_ccxt()
def get_target_symbol_balance(exchange, symbol='BTC'):
    balance = retry_ccxt()(exchange.fetch_balance)()
    return balance['total'].get(symbol, 0)

@retry_ccxt()
def get_price(exchange):
    return retry_ccxt()(exchange.fetch_ticker)(G.SYMBOL_FUTURES)['last']

@retry_ccxt()
def get_futures_position(exchange):
    try:
        positions = retry_ccxt()(exchange.fetch_positions)()
        for pos in positions:
            if pos['symbol'] == G.SYMBOL_FUTURES or pos['info'].get('instrument_name') == G.SYMBOL_FUTURES:
                size = float(pos['info'].get('size', '0'))
                entry = float(pos.get('entryPrice', 0))
                unrealized = float(pos.get('unrealizedPnl', 0))
                return size, entry, unrealized
    except Exception as e:
        log_and_print(f"fetch_positions failed: {str(e)}", "error")
    return 0.0, 0.0, 0.0

@retry_ccxt()
def get_limit_price(exchange, side):
    book = retry_ccxt()(exchange.fetch_order_book)(G.SYMBOL_FUTURES)
    if side.lower() == 'buy':
        return book['bids'][0][0] if book['bids'] else None
    else:
        return book['asks'][0][0] if book['asks'] else None

@retry_ccxt()
def getPerpetualSymbols(exchange):
    perpetual_symbols = []
    markets = exchange.load_markets()
    for symbol, market in markets.items():
        if (market.get("contract") is True and
            market.get("settle") in ["USD","USDT","USDC","BTC","ETH"] and
            market.get("swap", False)):
            perpetual_symbols.append(symbol)
    return perpetual_symbols
