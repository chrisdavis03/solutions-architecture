"""Shared pytest fixtures for the multi-region-failover example.

Everything runs offline: moto emulates DynamoDB, credentials are dummy, and
the Lambda directory is put on sys.path so the handlers import as they would
in the runtime.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

LAMBDA_DIR = Path(__file__).resolve().parents[1] / "lambda"
if str(LAMBDA_DIR) not in sys.path:
    sys.path.insert(0, str(LAMBDA_DIR))

import common  # noqa: E402 - sys.path must be prepared first

ORDERS_TABLE = "mrf-orders"
INVENTORY_TABLE = "mrf-inventory"
SEED_SKU = "widget"
SEED_QUANTITY = 5


def make_api_event(
    body: dict | None = None,
    *,
    raw_body: str | None = None,
    is_base64_encoded: bool = False,
    path_parameters: dict | None = None,
) -> dict:
    """Build a minimal API Gateway HTTP API (payload v2) event."""
    event = {
        "version": "2.0",
        "routeKey": "POST /checkout",
        "rawPath": "/checkout",
        "httpMethod": "POST",
        "headers": {"content-type": "application/json"},
        "requestContext": {"stage": "test", "http": {"method": "POST", "path": "/checkout"}},
        "isBase64Encoded": is_base64_encoded,
    }
    if raw_body is not None:
        event["body"] = raw_body
    elif body is not None:
        event["body"] = json.dumps(body)
    if path_parameters is not None:
        event["pathParameters"] = path_parameters
    return event


def assert_v2_response(response: dict) -> None:
    """Assert the API Gateway v2 response envelope and return nothing."""
    assert set(response) == {"statusCode", "headers", "body"}
    assert isinstance(response["statusCode"], int)
    assert response["headers"] == {"content-type": "application/json"}
    assert isinstance(response["body"], str)
    json.loads(response["body"])  # must be valid JSON text


def stock(client, sku: str = SEED_SKU) -> int | None:
    """Current quantity for a SKU, or None when the SKU does not exist."""
    item = client.get_item(TableName=INVENTORY_TABLE, Key={"sku": {"S": sku}}).get("Item")
    return int(item["quantity"]["N"]) if item else None


def order_items(client) -> list[dict]:
    return client.scan(TableName=ORDERS_TABLE).get("Items", [])


@pytest.fixture(autouse=True)
def aws_env(monkeypatch):
    """Dummy credentials, a fixed region and lambda table names for every test."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("ORDERS_TABLE", ORDERS_TABLE)
    monkeypatch.setenv("INVENTORY_TABLE", INVENTORY_TABLE)
    common.dynamodb_client.cache_clear()
    yield
    # A test may replace dynamodb_client with a plain function; only clear
    # the cache when the attribute is still the lru_cache-wrapped original.
    clear = getattr(common.dynamodb_client, "cache_clear", None)
    if clear is not None:
        clear()


@pytest.fixture
def ddb():
    """An in-memory DynamoDB with the two example tables, one seeded SKU."""
    with mock_aws():
        client = boto3.client("dynamodb", region_name="us-east-1")
        client.create_table(
            TableName=INVENTORY_TABLE,
            AttributeDefinitions=[{"AttributeName": "sku", "AttributeType": "S"}],
            KeySchema=[{"AttributeName": "sku", "KeyType": "HASH"}],
            BillingMode="PAY_PER_REQUEST",
        )
        client.put_item(
            TableName=INVENTORY_TABLE,
            Item={"sku": {"S": SEED_SKU}, "quantity": {"N": str(SEED_QUANTITY)}},
        )
        client.create_table(
            TableName=ORDERS_TABLE,
            AttributeDefinitions=[
                {"AttributeName": "order_id", "AttributeType": "S"},
                {"AttributeName": "status", "AttributeType": "S"},
                {"AttributeName": "created_at", "AttributeType": "S"},
            ],
            KeySchema=[{"AttributeName": "order_id", "KeyType": "HASH"}],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "status-index",
                    "KeySchema": [
                        {"AttributeName": "status", "KeyType": "HASH"},
                        {"AttributeName": "created_at", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                }
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        common.dynamodb_client.cache_clear()
        yield client
        common.dynamodb_client.cache_clear()


@pytest.fixture
def event_builder():
    return make_api_event


@pytest.fixture
def seed_order(ddb):
    """Insert an order directly, bypassing checkout, with all GSI keys."""

    def _seed(order_id: str, status: str = "pending", created_at: str = "2026-01-01T00:00:00+00:00"):
        item = {
            "order_id": order_id,
            "sku": SEED_SKU,
            "quantity": 1,
            "status": status,
            "created_at": created_at,
        }
        ddb.put_item(TableName=ORDERS_TABLE, Item=common.to_dynamo(item))
        return item

    return _seed
