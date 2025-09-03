from . import globals as G

def get_lot_size(exchange) -> float:
    try:
        m = exchange.markets.get(G.SYMBOL_FUTURES, {})
        lot = m.get("limits", {}).get("amount", {}).get("min")
        if lot:
            return float(lot)
    except Exception:
        pass
    return 10.0

def deviation(current_short_usd, desired_short_usd, total_usd):
    return (current_short_usd - desired_short_usd) / total_usd if total_usd else 0

def price_range(total_short_usd=None):
    up = G.REBALANCE_GAP / ((1 - G.SHORT_TARGET_RATIO) - G.REBALANCE_GAP)
    down = -G.REBALANCE_GAP / ((1 - G.SHORT_TARGET_RATIO) + G.REBALANCE_GAP)
    return down, up
