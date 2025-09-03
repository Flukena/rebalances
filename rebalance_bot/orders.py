import ccxt
import math
from .logging_utils import log_and_print
from . import globals as G
from .models import OrderStatus, ProcessState
from .exchange_client import retry_ccxt, get_futures_position
from .market_utils import price_range, get_lot_size

@retry_ccxt()
def cancel_all_orders(exchange):
    log_and_print("🗑️ Cancelling all open orders...", "info")
    try:
        if not G.order_ids:
            log_and_print("🔕 No tracked open orders. Attempting exchange-wide cancel for safety...", "info")
            try:
               retry_ccxt()(exchange.cancel_all_orders)(G.SYMBOL_FUTURES)
            except Exception as ee:
                log_and_print(f"⚠️ Exchange-wide cancel failed: {ee}", "warning")
            return
        remaining_orders = []
        for order_id in G.order_ids:
            try:
                result = retry_ccxt()(exchange.cancel_order)(order_id.order_id, G.SYMBOL_FUTURES)
                status = (result or {}).get("status", "").lower()
                if status not in ["canceled", "cancelled"]:
                    remaining_orders.append(order_id)
                else:
                    log_and_print(f"🗑️ Cancelled order {order_id.order_id}", "info")
            except ccxt.NetworkError as ne:
                log_and_print(f"🌐 Network error while cancelling order {order_id.order_id}: {ne}", "warning")
                remaining_orders.append(order_id)
            except Exception as e:
                log_and_print(f"⚠️ Failed to cancel order {order_id.order_id}: {e}", "error")
                remaining_orders.append(order_id)
        G.order_ids = remaining_orders
        log_and_print("✅ All open orders processed and cleaned.", "info")
    except Exception as e:
        log_and_print(f"⚠️ Error cancelling orders: {e}", "error")

def place_boundary_orders(exchange, price_now, total_short_usd, dev):
    log_and_print(f"[BOUNDARY] Placing boundary orders | dev={dev:.4f}", "info")
    lot_size = get_lot_size(exchange)
    down_pct, up_pct = price_range(total_short_usd)
    log_and_print(f"[BOUNDARY] Price now: {price_now:.2f}, Down pct: {down_pct:.4f}, Up pct: {up_pct:.4f}", "info")

    price_lower = price_now * (1 + down_pct)
    price_upper = price_now * (1 + up_pct)

    short_amt, entry, _ = get_futures_position(exchange)
    short_assets = abs(short_amt) / entry if entry > 0 else 0
    log_and_print(f"[BOUNDARY] Current short {G.SYMBOL}: {short_assets:.6f} at entry price {entry:.2f}", "info")

    total_port_up = G.current_balance_asset * price_upper
    desired_short_up = total_port_up * G.SHORT_TARGET_RATIO
    diff_up = desired_short_up - G.current_short_usd

    total_port_down = G.current_balance_asset * price_lower
    desired_short_down = total_port_down * G.SHORT_TARGET_RATIO
    diff_down = desired_short_down - G.current_short_usd

    contracts_up = abs(math.floor(abs(diff_up) / lot_size) * lot_size)
    contracts_down = abs(math.ceil(abs(diff_down) / lot_size) * lot_size)

    if contracts_up >= lot_size and contracts_down >= lot_size:
        try:
            order = retry_ccxt()(exchange.create_limit_sell_order)(G.SYMBOL_FUTURES, contracts_up, price_upper, {"post_only": True})
            try:
                verified_order = retry_ccxt()(exchange.fetch_order)(order['id'], G.SYMBOL_FUTURES)
                G.order_ids.append(OrderStatus.from_ccxt_order(verified_order))
            except Exception:
                G.order_ids.append(OrderStatus.from_ccxt_order(order))
            log_and_print(f"[UPPER] Sell {contracts_up} amount at {price_upper:.2f}", "info")

            order = retry_ccxt()(exchange.create_limit_buy_order)(G.SYMBOL_FUTURES, contracts_down, price_lower, {"post_only": True, "reduce_only": True})
            try:
                verified_order = retry_ccxt()(exchange.fetch_order)(order['id'], G.SYMBOL_FUTURES)
                G.order_ids.append(OrderStatus.from_ccxt_order(verified_order))
            except Exception:
                G.order_ids.append(OrderStatus.from_ccxt_order(order))
            log_and_print(f"[LOWER] Buy {contracts_down} amount at {price_lower:.2f}", "info")

            log_and_print(
                f"Placed boundary orders: UP {contracts_up} @ {price_upper:.2f}, DOWN {contracts_down} @ {price_lower:.2f}",
                "info",
            )
            G.state = ProcessState.WAITMATCHPRE
        except Exception as e:
            log_and_print(f"❌ Error placing boundary orders: {str(e)}", "error")
    else:
        G.state = ProcessState.REBALANCING

def handle_order_status(exchange):
    try:
        for order in G.order_ids:
            try:
                data = retry_ccxt()(exchange.fetch_order)(order.order_id, G.SYMBOL_FUTURES)
                order.status = OrderStatus.normalize_status(data['status'])
                order.filled = float(data.get('filled', 0))
                avg_price = data.get('average') or data.get('average_price')
                order.average_price = float(avg_price) if avg_price is not None else None
            except ccxt.OrderNotFound:
                log_and_print(f"⚠️ Order {order.order_id} not found.", "warning")
            except Exception as e:
                log_and_print(f"❌ Error fetching order {order.order_id}: {str(e)}", "error")

        filled_orders = [o for o in G.order_ids if o.status == "FILLED"]
        for filled in filled_orders:
            log_and_print(f"✅ Order {filled.order_id} filled: {filled.contracts} at {filled.price:.2f}", "info")
            try:
                pos_size, _, _ = get_futures_position(exchange)
                G.current_short_usd = abs(pos_size)
            except Exception as e:
                log_and_print(f"⚠️ Unable to refresh position after fill: {e}", "warning")
            log_and_print(f"💰 Updated balance: {G.SYMBOL}={G.current_balance_asset:.6f} ShortUSD={G.current_short_usd:.2f}", "info")
            G.order_ids.remove(filled)
        if filled_orders:
            G.state = ProcessState.REBALANCING
            cancel_all_orders(exchange)
            return

        cancelled_orders = [o for o in G.order_ids if o.status == "CANCELLED"]
        for cancelled in cancelled_orders:
            log_and_print(f"❌ Order {cancelled.order_id} cancelled: {cancelled.contracts} at {cancelled.price:.2f}", "info")
            G.order_ids.remove(cancelled)
        if cancelled_orders:
            try:
                pos_size, _, _ = get_futures_position(exchange)
                G.current_short_usd = abs(pos_size)
            except Exception as e:
                log_and_print(f"⚠️ Unable to refresh position after cancellations: {e}", "warning")
            if not G.order_ids:
                log_and_print("🔕 All orders cancelled, rebalancing...", "info")
            G.state = ProcessState.REBALANCING
            cancel_all_orders(exchange)
            return

        if G.state == ProcessState.WAITMATCH:
            open_order = next((o for o in G.order_ids if o.status == "OPEN"), None)
            if open_order:
                from .exchange_client import get_price
                price = get_price(exchange)
                if not price or price <= 0:
                    log_and_print("⚠️ Invalid price received while checking open orders.", "warning")
                    return
                diff_price = abs(open_order.price - price)
                log_and_print(f"Current price: {price:.2f}, Order price: {open_order.price:.2f}, Difference: {diff_price:.4f}", "info")
                if price > 0 and diff_price <= (0.001 * price):
                    log_and_print("⏳ Waiting for orders to fill...", "info")
                else:
                    cancel_all_orders(exchange)
                    log_and_print("🔕 No filled orders, cancelling all open orders.", "info")
                    G.state = ProcessState.REBALANCING
        log_and_print(f"[SETUP] {G.SYMBOL} Balance: {G.current_balance_asset:.6f}, Initial Short USD: {G.current_short_usd:.2f}", "info")
    except Exception as e:
        log_and_print(f"❌ Order status error: {str(e)}", "error")
