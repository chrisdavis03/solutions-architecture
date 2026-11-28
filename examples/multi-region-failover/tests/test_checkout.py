"""Tests for POST /checkout: atomic stock reservation and order creation."""

from __future__ import annotations

import json

import pytest

import checkout
from conftest import assert_v2_response, make_api_event, order_items, stock


def _body(response: dict) -> dict:
    return json.loads(response["body"])


def test_happy_path_creates_pending_order_and_decrements_stock_exactly_once(ddb, event_builder):
    event = event_builder({"sku": "widget", "quantity": 2, "order_id": "ord-1"})

    response = checkout.handler(event, None)

    assert_v2_response(response)
    assert response["statusCode"] == 201
    order = _body(response)
    assert order["order_id"] == "ord-1"
    assert order["sku"] == "widget"
    assert order["quantity"] == 2
    assert order["status"] == "pending"
    assert order["created_at"]

    assert stock(ddb) == 3
    orders = order_items(ddb)
    assert len(orders) == 1
    assert orders[0]["order_id"]["S"] == "ord-1"
    assert orders[0]["status"]["S"] == "pending"


def test_insufficient_stock_returns_409_and_writes_nothing(ddb, event_builder):
    event = event_builder({"sku": "widget", "quantity": 6, "order_id": "ord-big"})

    response = checkout.handler(event, None)

    assert_v2_response(response)
    assert response["statusCode"] == 409
    assert _body(response) == {"error": "insufficient_stock"}
    assert stock(ddb) == 5
    assert order_items(ddb) == []


def test_unknown_sku_returns_409_without_order_or_inventory_item(ddb, event_builder):
    event = event_builder({"sku": "missing-sku", "quantity": 1, "order_id": "ord-missing"})

    response = checkout.handler(event, None)

    assert response["statusCode"] == 409
    assert _body(response)["error"] == "insufficient_stock"
    assert order_items(ddb) == []
    assert stock(ddb, "missing-sku") is None
    assert stock(ddb) == 5


@pytest.mark.parametrize(
    "event",
    [
        {},
        {"body": ""},
        make_api_event(raw_body="{not json"),
        make_api_event(raw_body="[]"),
    ],
)
def test_malformed_or_missing_body_returns_400(ddb, event):
    response = checkout.handler(event, None)

    assert_v2_response(response)
    assert response["statusCode"] == 400
    assert _body(response)["error"] == "invalid_json"
    assert stock(ddb) == 5
    assert order_items(ddb) == []


@pytest.mark.parametrize(
    ("body", "code"),
    [
        ({"sku": "widget", "quantity": True, "order_id": "bool-qty"}, "invalid_quantity"),
        ({"sku": "widget", "quantity": 0, "order_id": "zero-qty"}, "invalid_quantity"),
        ({"sku": "widget", "quantity": -1, "order_id": "neg-qty"}, "invalid_quantity"),
        ({"sku": "widget", "quantity": 1001, "order_id": "big-qty"}, "invalid_quantity"),
        ({"sku": "widget", "quantity": "2", "order_id": "str-qty"}, "invalid_quantity"),
        ({"sku": "widget", "quantity": 1.5, "order_id": "float-qty"}, "invalid_quantity"),
        ({"sku": "widget", "order_id": "no-qty"}, "invalid_quantity"),
        ({"sku": "bad sku", "quantity": 1}, "invalid_sku"),
        ({"sku": "x" * 65, "quantity": 1}, "invalid_sku"),
        ({"sku": "", "quantity": 1}, "invalid_sku"),
        ({"sku": "widget", "quantity": 1, "order_id": "bad id"}, "invalid_order_id"),
        ({"sku": "widget", "quantity": 1, "order_id": "x" * 129}, "invalid_order_id"),
    ],
)
def test_invalid_fields_return_400_and_write_nothing(ddb, event_builder, body, code):
    response = checkout.handler(event_builder(body), None)

    assert_v2_response(response)
    assert response["statusCode"] == 400
    assert _body(response)["error"] == code
    assert stock(ddb) == 5
    assert order_items(ddb) == []


def test_replay_same_order_id_same_payload_returns_200_without_second_decrement(ddb, event_builder):
    event = event_builder({"sku": "widget", "quantity": 2, "order_id": "ord-replay"})

    first = checkout.handler(event, None)
    assert first["statusCode"] == 201
    assert stock(ddb) == 3

    second = checkout.handler(event, None)

    assert_v2_response(second)
    assert second["statusCode"] == 200
    replayed = _body(second)
    assert replayed["order_id"] == "ord-replay"
    assert replayed["status"] == "pending"
    assert replayed["sku"] == "widget"
    assert replayed["quantity"] == 2
    assert stock(ddb) == 3
    assert len(order_items(ddb)) == 1


@pytest.mark.parametrize(
    "second_body",
    [
        {"sku": "widget", "quantity": 1, "order_id": "ord-conflict"},
        {"sku": "other-sku", "quantity": 2, "order_id": "ord-conflict"},
    ],
)
def test_reused_order_id_with_different_payload_returns_409(ddb, event_builder, second_body):
    first_body = {"sku": "widget", "quantity": 2, "order_id": "ord-conflict"}
    assert checkout.handler(event_builder(first_body), None)["statusCode"] == 201
    assert stock(ddb) == 3

    response = checkout.handler(event_builder(second_body), None)

    assert_v2_response(response)
    assert response["statusCode"] == 409
    assert _body(response)["error"] == "order_id_conflict"
    assert stock(ddb) == 3
    assert stock(ddb, "other-sku") is None
    assert len(order_items(ddb)) == 1


def test_response_is_api_gateway_v2_shape(ddb, event_builder):
    response = checkout.handler(event_builder({"sku": "widget", "quantity": 1}), None)
    assert_v2_response(response)
    assert response["statusCode"] == 201
    assert _body(response)["status"] == "pending"
