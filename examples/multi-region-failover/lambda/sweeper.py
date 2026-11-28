"""Scheduled sweeper: promote pending orders to fulfilled.

Runs on a schedule in the secondary region only (see enable_sweeper). It stands
in for the fulfillment work a real system would do after checkout, such as
picking, packing, or handing off to a shipping provider.

Safe to re-run:
- The query reads the status-index GSI, so it only returns orders that are
  pending at the time of the query.
- Each promotion is an UpdateItem conditioned on `status = pending`. An order
  that another run (or another region) already promoted fails the condition
  and is counted as skipped, not as an error.

GSI queries are eventually consistent. An order created just before the query
may be missed until the next run. The conditional update still protects
against double-processing.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from common import dynamodb_client, error_code, log, table_name

PENDING = "pending"
FULFILLED = "fulfilled"
INDEX_NAME = "status-index"


def handler(event: dict[str, Any], context: Any) -> dict[str, int]:
    client = dynamodb_client()
    orders_table = table_name("ORDERS_TABLE")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    scanned = fulfilled = skipped = 0
    query_kwargs: dict[str, Any] = {
        "TableName": orders_table,
        "IndexName": INDEX_NAME,
        "KeyConditionExpression": "#status = :pending",
        "ExpressionAttributeNames": {"#status": "status"},
        "ExpressionAttributeValues": {":pending": {"S": PENDING}},
    }

    # Pages are followed until exhausted. A very large backlog could run past
    # the function timeout; the remedy is a Limit plus resuming on the next run.
    while True:
        resp = client.query(**query_kwargs)
        for item in resp.get("Items", []):
            scanned += 1
            try:
                client.update_item(
                    TableName=orders_table,
                    Key={"order_id": item["order_id"]},
                    UpdateExpression="SET #status = :fulfilled, fulfilled_at = :now",
                    ConditionExpression="#status = :pending",
                    ExpressionAttributeNames={"#status": "status"},
                    ExpressionAttributeValues={
                        ":pending": {"S": PENDING},
                        ":fulfilled": {"S": FULFILLED},
                        ":now": {"S": now},
                    },
                )
                fulfilled += 1
            except Exception as exc:  # noqa: BLE001 - re-raised unless it is the expected race
                if error_code(exc) != "ConditionalCheckFailedException":
                    raise
                skipped += 1  # already promoted by a previous run or another writer

        last_key = resp.get("LastEvaluatedKey")
        if not last_key:
            break
        query_kwargs["ExclusiveStartKey"] = last_key

    summary = {"scanned": scanned, "fulfilled": fulfilled, "skipped": skipped}
    log(logging.INFO, "sweeper_finished", **summary)
    return summary
