from .logging_utils import log_and_print
from . import globals as G
from .exchange_client import get_target_symbol_balance, get_futures_position
from .orders import cancel_all_orders

def setup_portfolio(exchange):
    cancel_all_orders(exchange)
    symbol_assets = get_target_symbol_balance(exchange, G.SYMBOL)
    G.initial_balance_asset = G.current_balance_asset = symbol_assets
    short_amt, _, _ = get_futures_position(exchange)
    G.initial_short_usd = G.current_short_usd = abs(short_amt)
    log_and_print(f"[SETUP] Initial {G.SYMBOL} Balance: {G.initial_balance_asset:.6f}, Initial Short USD: {G.initial_short_usd:.2f}", "info")
