"""Unit tests for the shared helpers in lambda/common.py."""

from __future__ import annotations

import base64
import json
from decimal import Decimal

import pytest
from botocore.exceptions import ClientError

import common
from conftest import assert_v2_response, make_api_event


def test_json_response_shape_and_decimal_rendering():
    response = common.json_response(200, {"quantity": Decimal("5"), "ratio": Decimal("2.5")})
    assert_v2_response(response)
    assert response["statusCode"] == 200
    assert json.loads(response["body"]) == {"quantity": 5, "ratio": 2.5}


def test_error_response_shape_with_and_without_message():
    bare = common.error_response(409, "insufficient_stock")
    assert_v2_response(bare)
    assert bare["statusCode"] == 409
    assert json.loads(bare["body"]) == {"error": "insufficient_stock"}

    detailed = common.error_response(400, "invalid_quantity", "must be positive")
    assert_v2_response(detailed)
    assert json.loads(detailed["body"]) == {
        "error": "invalid_quantity",
        "message": "must be positive",
    }


def test_parse_json_body_plain():
    assert common.parse_json_body(make_api_event(body={"sku": "widget", "quantity": 2})) == {
        "sku": "widget",
        "quantity": 2,
    }


def test_parse_json_body_base64_encoded():
    payload = json.dumps({"sku": "widget", "quantity": 3})
    event = make_api_event(
        raw_body=base64.b64encode(payload.encode("utf-8")).decode("ascii"),
        is_base64_encoded=True,
    )
    assert common.parse_json_body(event) == {"sku": "widget", "quantity": 3}


@pytest.mark.parametrize("raw_body", ["{not json", "[]", "null", "42"])
def test_parse_json_body_rejects_invalid_or_non_object_json(raw_body):
    with pytest.raises(common.RequestError) as exc:
        common.parse_json_body(make_api_event(raw_body=raw_body))
    assert exc.value.code == "invalid_json"


@pytest.mark.parametrize("event", [{}, {"body": ""}, {"body": None}])
def test_parse_json_body_rejects_missing_body(event):
    with pytest.raises(common.RequestError) as exc:
        common.parse_json_body(event)
    assert exc.value.code == "invalid_json"


def test_parse_json_body_rejects_undecodable_base64():
    event = make_api_event(raw_body="%%%not-base64%%%", is_base64_encoded=True)
    with pytest.raises(common.RequestError) as exc:
        common.parse_json_body(event)
    assert exc.value.code == "invalid_json"


def test_to_dynamo_from_dynamo_round_trip():
    original = {"sku": "widget", "quantity": 5, "note": "ok"}
    encoded = common.to_dynamo(original)
    assert encoded == {"sku": {"S": "widget"}, "quantity": {"N": "5"}, "note": {"S": "ok"}}
    decoded = common.from_dynamo(encoded)
    assert decoded == {"sku": "widget", "quantity": Decimal("5"), "note": "ok"}
    assert isinstance(decoded["quantity"], Decimal)


def test_error_code_extraction_from_botocore_client_error():
    exc = ClientError(
        {"Error": {"Code": "ConditionalCheckFailedException", "Message": "nope"}},
        "TransactWriteItems",
    )
    assert common.error_code(exc) == "ConditionalCheckFailedException"
    assert isinstance(exc, Exception)


def test_error_code_is_empty_when_exception_has_no_error_code():
    assert common.error_code(ValueError("plain")) == ""


def test_table_name_raises_for_unset_environment_variable(monkeypatch):
    monkeypatch.delenv("MISSING_TABLE", raising=False)
    with pytest.raises(RuntimeError, match="MISSING_TABLE"):
        common.table_name("MISSING_TABLE")
