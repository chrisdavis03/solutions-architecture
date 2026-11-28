"""GET /inventory/{sku}: return the current stock level for one SKU."""

from __future__ import annotations

from typing import Any

from common import (
    SKU_PATTERN,
    dynamodb_client,
    error_response,
    from_dynamo,
    json_response,
    table_name,
)


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    sku = (event.get("pathParameters") or {}).get("sku")
    if not sku or not SKU_PATTERN.fullmatch(sku):
        return error_response(400, "invalid_sku")

    resp = dynamodb_client().get_item(
        TableName=table_name("INVENTORY_TABLE"),
        Key={"sku": {"S": sku}},
        # Strongly consistent read within the region. Global Tables replication
        # is still asynchronous, so another region can briefly show a different value.
        ConsistentRead=True,
    )
    item = resp.get("Item")
    if item is None:
        return error_response(404, "not_found")

    quantity = from_dynamo(item)["quantity"]
    return json_response(200, {"sku": sku, "quantity": int(quantity)})
