"""Tests for the scheduled sweeper: promotion, pagination and idempotency."""

from __future__ import annotations

from botocore.exceptions import ClientError

import common
import sweeper
from conftest import ORDERS_TABLE, SEED_SKU


def _item(order_id, status, created_at):
    return common.to_dynamo(
        {
            "order_id": order_id,
            "sku": SEED_SKU,
            "quantity": 1,
            "status": status,
            "created_at": created_at,
        }
    )


def _get_status(client, order_id):
    item = client.get_item(TableName=ORDERS_TABLE, Key={"order_id": {"S": order_id}}).get("Item")
    return item["status"]["S"] if item else None


def test_sweeper_promotes_pending_orders_leaves_fulfilled_alone_and_is_idempotent(
    ddb, seed_order
):
    seed_order("pending-1", "pending", "2026-01-01T00:00:01+00:00")
    seed_order("pending-2", "pending", "2026-01-01T00:00:02+00:00")
    seed_order("already-done", "fulfilled", "2026-01-01T00:00:03+00:00")

    first = sweeper.handler({}, None)

    assert first == {"scanned": 2, "fulfilled": 2, "skipped": 0}
    assert _get_status(ddb, "pending-1") == "fulfilled"
    assert _get_status(ddb, "pending-2") == "fulfilled"
    assert _get_status(ddb, "already-done") == "fulfilled"  # was already fulfilled

    # A fulfilled order must not gain a second fulfilled_at value, and the
    # original order's other attributes must survive the promotion.
    done = ddb.get_item(TableName=ORDERS_TABLE, Key={"order_id": {"S": "pending-1"}})["Item"]
    assert "fulfilled_at" in done
    assert done["sku"]["S"] == SEED_SKU

    second = sweeper.handler({}, None)

    assert second == {"scanned": 0, "fulfilled": 0, "skipped": 0}


def test_sweeper_follows_pagination_and_processes_both_pages(ddb, monkeypatch, seed_order):
    seed_order("page-1", "pending", "2026-01-01T00:00:01+00:00")
    seed_order("page-2", "pending", "2026-01-01T00:00:02+00:00")
    page_one_key = {"order_id": {"S": "page-1"}, "status": {"S": "pending"}}
    pages = [
        {"Items": [_item("page-1", "pending", "2026-01-01T00:00:01+00:00")], "LastEvaluatedKey": page_one_key},
        {"Items": [_item("page-2", "pending", "2026-01-01T00:00:02+00:00")]},
    ]
    query_calls = []
    real_client = common.dynamodb_client()

    class TwoPageClient:
        def query(self, **kwargs):
            query_calls.append(kwargs)
            return pages[len(query_calls) - 1]

        def update_item(self, **kwargs):
            return real_client.update_item(**kwargs)

    monkeypatch.setattr(sweeper, "dynamodb_client", lambda: TwoPageClient())

    result = sweeper.handler({}, None)

    assert result == {"scanned": 2, "fulfilled": 2, "skipped": 0}
    assert len(query_calls) == 2
    assert "ExclusiveStartKey" not in query_calls[0]
    assert query_calls[1]["ExclusiveStartKey"] == page_one_key
    for kwargs in query_calls:
        assert kwargs["TableName"] == ORDERS_TABLE
        assert kwargs["IndexName"] == "status-index"
        assert kwargs["KeyConditionExpression"] == "#status = :pending"
        assert kwargs["ExpressionAttributeValues"] == {":pending": {"S": "pending"}}
    assert _get_status(ddb, "page-1") == "fulfilled"
    assert _get_status(ddb, "page-2") == "fulfilled"


def test_sweeper_counts_conditional_update_failure_as_skipped(ddb, monkeypatch, seed_order):
    seed_order("lost-race", "pending", "2026-01-01T00:00:01+00:00")
    seed_order("won-race", "pending", "2026-01-01T00:00:02+00:00")
    real_client = common.dynamodb_client()

    class RacingClient:
        def query(self, **kwargs):
            return {
                "Items": [
                    _item("lost-race", "pending", "2026-01-01T00:00:01+00:00"),
                    _item("won-race", "pending", "2026-01-01T00:00:02+00:00"),
                ]
            }

        def update_item(self, **kwargs):
            if kwargs["Key"]["order_id"]["S"] == "lost-race":
                raise ClientError(
                    {"Error": {"Code": "ConditionalCheckFailedException", "Message": "raced"}},
                    "UpdateItem",
                )
            return real_client.update_item(**kwargs)

    monkeypatch.setattr(sweeper, "dynamodb_client", lambda: RacingClient())

    result = sweeper.handler({}, None)

    assert result == {"scanned": 2, "fulfilled": 1, "skipped": 1}
    assert _get_status(ddb, "won-race") == "fulfilled"
