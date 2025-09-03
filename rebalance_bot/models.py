from dataclasses import dataclass
from enum import Enum
from typing import Optional

class ProcessState(Enum):
    WAITMATCH = 0
    REBALANCING = 1
    WAITMATCHPRE = 2

@dataclass
class BotConfig:
    symbol_futures: str
    rebalance_gap: float
    short_target_ratio: float
    interval_seconds: int
    max_leverage: float
    initial_asset: float

@dataclass
class OrderStatus:
    order_id: str
    side: str
    contracts: float
    price: float
    status: str
    filled: float = 0
    average_price: Optional[float] = None

    @staticmethod
    def normalize_status(status: str) -> str:
        status = (status or "").lower()
        if status in ["closed", "filled"]:
            return "FILLED"
        if status in ["open", "new"]:
            return "OPEN"
        if status in ["partial", "partially_filled", "partially-filled"]:
            return "PARTIAL"
        if status in ["canceled", "cancelled", "expired", "rejected"]:
            return "CANCELLED"
        return "CANCELLED"

    @classmethod
    def from_ccxt_order(cls, order: dict) -> "OrderStatus":
        return cls(
            order_id=str(order.get("id", "")),
            side=order.get("side", "").upper(),
            contracts=float(order.get("amount", 0)),
            price=float(order.get("price", 0)),
            status=cls.normalize_status(order.get("status", "")),
            filled=float(order.get("filled", 0)),
            average_price=order.get("average", order.get("average_price", None)),
        )
