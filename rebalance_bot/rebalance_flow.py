from .logging_utils import log_and_print
from . import globals as G
from .market_utils import get_lot_size, deviation
from .exchange_client import get_price, get_futures_position, get_limit_price, retry_ccxt
from .models import ProcessState, OrderStatus
from .orders import place_boundary_orders

def rebalance(exchange):
    log_and_print("[REBALANCE] Checking portfolio...", "info")
    price = get_price(exchange)
    if not price or price <= 0:
        log_and_print("⚠️ Invalid price received. Skipping rebalance cycle.", "warning")
        return

    lot_size = get_lot_size(exchange)
    short_amt, _, _ = get_futures_position(exchange)
    short_usd = abs(short_amt)
    total_usd = G.current_balance_asset * price

    G.current_short_usd = short_usd
    desired_short_usd = total_usd * G.SHORT_TARGET_RATIO
    dev = deviation(G.current_short_usd, desired_short_usd, total_usd)

    log_and_print(f"[CHECK] Spot {G.SYMBOL}: {G.current_balance_asset:.6f} | Short: {short_amt:.0f} USD | Deviation: {dev*100:.2f}% | BTC Price : {price:.2f}", "info")

    if abs(dev) > G.REBALANCE_GAP:
        diff = desired_short_usd - short_usd
        current_leverage = abs(short_usd + diff) / (G.current_balance_asset * price)
        if current_leverage > G.MAX_LEVERAGE:
            log_and_print(f"⚠️ Leverage would exceed {G.MAX_LEVERAGE}x after this trade. Skipping.", "warning")
            return

        contracts = max(lot_size, round(abs(diff) / lot_size) * lot_size)
        if contracts >= lot_size:
            if diff > 0:
                price_limit = get_limit_price(exchange, 'sell')
                order = retry_ccxt()(exchange.create_limit_sell_order)(G.SYMBOL_FUTURES, contracts, price_limit, {"post_only": True})
            else:
                price_limit = get_limit_price(exchange, 'buy')
                order = retry_ccxt()(exchange.create_limit_buy_order)(G.SYMBOL_FUTURES, contracts, price_limit, {"post_only": True, "reduce_only": True})
            try:
                verified_order = retry_ccxt()(exchange.fetch_order)(order['id'], G.SYMBOL_FUTURES)
                G.order_ids.append(OrderStatus.from_ccxt_order(verified_order))
            except Exception:
                G.order_ids.append(OrderStatus.from_ccxt_order(order))
            log_and_print(f"[{'SHORT' if diff>0 else 'COVER'}] Placing {'sell' if diff>0 else 'buy'} order for {contracts} contracts at {price_limit:.2f}", "info")
            G.state = ProcessState.WAITMATCH
        else:
            log_and_print(f"🔕 Too small order: {contracts:.2f} contracts (min lot)", "info")
    else:
        place_boundary_orders(exchange, price, total_usd, dev)
        log_and_print("✅ Portfolio is balanced. OCO boundary orders placed.", "info")
