"""POST /checkout: reserve stock and create a pending order in one transaction.

The inventory decrement and the order insert go into a single DynamoDB
TransactWriteItems call, so either both happen or neither does. The
inventory item has a `quantity >= :qty` condition, which prevents overselling
inside one region.

Idempotency: the order insert is conditional on `attribute_not_exists(order_id)`.
A client that retries with the same order_id after a timeout cannot decrement
stock twice, because the whole transaction is cancelled. On a replay we return
the original order (200) when the request matches it, or 409 when the order_id
was reused for something different.

Multi-region caveat (teaching point, not hidden): mrf-inventory is a DynamoDB
Global Table with last-writer-wins (LWW) replication. A transaction is atomic
only inside the region that handles it. If the same SKU is checked out in
us-east-1 and us-west-2 during replication lag (or a partition, which is what
failover is for), each region can see enough stock and accept its own
decrement. When replicas converge, LWW keeps one write to `quantity` and drops
the other, so the SKU can end up oversold even though every single-region
check passed. This example accepts that risk on purpose. A production design
needs one writer per SKU, per-region stock allocation (escrow), or a
reconciliation job.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from common import (
    SKU_PATTERN,
    RequestError,
    dynamodb_client,
    error_code,
    error_response,
    from_dynamo,
    json_response,
    log,
    parse_json_body,
    table_name,
    to_dynamo,
)

MAX_QUANTITY = 1000
ORDER_ID_PATTERN = re.compile(r"[A-Za-z0-9._:-]{1,128}")

PENDING = "pending"


def validate(body: dict[str, Any]) -> tuple[str, int, str]:
    """Return (sku, quantity, order_id) or raise RequestError."""
    sku = body.get("sku")
    if not isinstance(sku, str) or not SKU_PATTERN.fullmatch(sku):
        raise RequestError("invalid_sku", "sku must be 1-64 characters: letters, digits, '.', '_', '-'")

    quantity = body.get("quantity")
    # bool is a subclass of int in Python, so reject it explicitly.
    if isinstance(quantity, bool) or not isinstance(quantity, int) or not 1 <= quantity <= MAX_QUANTITY:
        raise RequestError("invalid_quantity", f"quantity must be an integer from 1 to {MAX_QUANTITY}")

    order_id = body.get("order_id")
    if order_id is None:
        order_id = str(uuid.uuid4())
    elif not isinstance(order_id, str) or not ORDER_ID_PATTERN.fullmatch(order_id):
        raise RequestError("invalid_order_id", "order_id must be 1-128 characters: letters, digits, '.', '_', '-', ':'")

    return sku, quantity, order_id


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    try:
        body = parse_json_body(event)
        sku, quantity, order_id = validate(body)
    except RequestError as exc:
        return error_response(400, exc.code, exc.message)

    orders_table = table_name("ORDERS_TABLE")
    inventory_table = table_name("INVENTORY_TABLE")
    order = {
        "order_id": order_id,
        "sku": sku,
        "quantity": quantity,
        "status": PENDING,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }

    try:
        dynamodb_client().transact_write_items(
            TransactItems=[
                {
                    "Update": {
                        "TableName": inventory_table,
                        "Key": {"sku": {"S": sku}},
                        "UpdateExpression": "SET quantity = quantity - :qty",
                        # attribute_exists stops a missing SKU from being
                        # created with a negative quantity.
                        "ConditionExpression": "attribute_exists(sku) AND quantity >= :qty",
                        "ExpressionAttributeValues": {":qty": {"N": str(quantity)}},
                    }
                },
                {
                    "Put": {
                        "TableName": orders_table,
                        "Item": to_dynamo(order),
                        "ConditionExpression": "attribute_not_exists(order_id)",
                    }
                },
            ]
        )
    except Exception as exc:  # noqa: BLE001 - re-raised below unless it is a transaction cancel
        if error_code(exc) != "TransactionCanceledException":
            raise
        return _cancelled(exc, orders_table, order)

    log(logging.INFO, "order_created", order_id=order_id, sku=sku, quantity=quantity)
    return json_response(201, order)


def _cancelled(exc: Exception, orders_table: str, order: dict[str, Any]) -> dict[str, Any]:
    """Map a cancelled transaction to a client response.

    CancellationReasons is positional, matching TransactItems: [0] is the
    inventory update, [1] is the order put.
    """
    reasons = getattr(exc, "response", {}).get("CancellationReasons", [])
    inventory_reason = reasons[0].get("Code") if len(reasons) > 0 else None
    order_reason = reasons[1].get("Code") if len(reasons) > 1 else None

    if order_reason == "ConditionalCheckFailed":
        # The order_id already exists, so this is a retry or a reused id.
        return _replay(orders_table, order)

    if inventory_reason == "ConditionalCheckFailed":
        # Covers insufficient stock and an unknown SKU (no item to update).
        log(logging.INFO, "insufficient_stock", sku=order["sku"], quantity=order["quantity"])
        return error_response(409, "insufficient_stock")

    # Throttling, TransactionConflict, etc. Nothing was written, so a retry is safe.
    log(logging.WARNING, "checkout_transient_failure", reasons=reasons)
    return error_response(503, "temporarily_unavailable", "retry the request")


def _replay(orders_table: str, requested: dict[str, Any]) -> dict[str, Any]:
    """Answer a checkout whose order_id already exists."""
    resp = dynamodb_client().get_item(
        TableName=orders_table,
        Key={"order_id": {"S": requested["order_id"]}},
        ConsistentRead=True,
    )
    existing = from_dynamo(resp["Item"]) if "Item" in resp else None
    if existing and existing.get("sku") == requested["sku"] and existing.get("quantity") == requested["quantity"]:
        log(logging.INFO, "checkout_replayed", order_id=requested["order_id"])
        return json_response(200, existing)
    return error_response(409, "order_id_conflict", "order_id already exists for a different order")
