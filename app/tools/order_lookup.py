from __future__ import annotations

import json
import re
from pathlib import Path

from app.models.schemas import OrderItem, OrderLookupResult

_ORDER_ID_PATTERN = re.compile(r"^ORD-\d{4}$")
_STATUSES_HIDING_ETA = {"cancelled", "returned"}
_STATUSES_HIDING_CARRIER_AND_TRACKING = {"cancelled"}
_STATUSES_REQUIRING_HANDOFF = {"exception"}


_CUSTOMER_SAFE_TOP_LEVEL_FIELDS = {
    "order_id",
    "membership_tier",
    "placed_at",
    "status",
    "status_updated_at",
    "shipped_at",
    "delivered_at",
    "carrier",
    "tracking_number",
    "estimated_delivery",
    "customer_safe_message",
}


def _normalize_order_id(raw: str) -> str:

    cleaned = raw.strip().strip("\"'").strip()
    return cleaned.upper()


def _is_well_formed(order_id: str) -> bool:
    return bool(_ORDER_ID_PATTERN.match(order_id))


def load_orders(orders_path: str | Path = "data/orders.json") -> dict[str, dict]:
   
    path = Path(orders_path)
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    orders_by_id: dict[str, dict] = {}
    for order in data["orders"]:
        orders_by_id[order["order_id"]] = order
    return orders_by_id


def get_order_status(
    order_id_raw: str,
    orders_by_id: dict[str, dict],
) -> OrderLookupResult:
   
    if not order_id_raw or not order_id_raw.strip():
  
        return OrderLookupResult(
            order_id="",
            found=False,
            error="malformed_id",
            handoff_required=False,
        )

    normalized_id = _normalize_order_id(order_id_raw)

    if not _is_well_formed(normalized_id):
        return OrderLookupResult(
            order_id=normalized_id,
            found=False,
            error="malformed_id",
            handoff_required=False,
        )

    order = orders_by_id.get(normalized_id)

    if order is None:
        return OrderLookupResult(
            order_id=normalized_id,
            found=False,
            error="not_found",
            handoff_required=True,
            handoff_reason="Order ID was not found in the system.",
        )

    status = order["status"]

    estimated_delivery = order.get("estimated_delivery")
    carrier = order.get("carrier")
    tracking_number = order.get("tracking_number")

    if status in _STATUSES_HIDING_ETA:
        estimated_delivery = None

    if status in _STATUSES_HIDING_CARRIER_AND_TRACKING:
        carrier = None
        tracking_number = None

    handoff_required = status in _STATUSES_REQUIRING_HANDOFF
    handoff_reason = (
        "Shipment exception requires support review." if handoff_required else None
    )

    items = [
        OrderItem(
            name=item["name"],
            quantity=item["quantity"],
            final_sale=item["final_sale"],
        )
        for item in order.get("items", [])
    ]

    return OrderLookupResult(
        order_id=order["order_id"],
        found=True,
        membership_tier=order.get("membership_tier"),
        items=items,
        placed_at=order.get("placed_at"),
        status=status,
        status_updated_at=order.get("status_updated_at"),
        shipped_at=order.get("shipped_at"),
        delivered_at=order.get("delivered_at"),
        carrier=carrier,
        tracking_number=tracking_number,
        estimated_delivery=estimated_delivery,
        customer_safe_message=order.get("customer_safe_message"),
        handoff_required=handoff_required,
        handoff_reason=handoff_reason,
    )