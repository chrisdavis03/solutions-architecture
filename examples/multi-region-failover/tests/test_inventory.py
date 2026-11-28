"""Tests for GET /inventory/{sku}."""

from __future__ import annotations

import json

from conftest import assert_v2_response, make_api_event
from inventory import handler


def test_existing_sku_returns_200_with_sku_and_quantity(ddb):
    response = handler(make_api_event(path_parameters={"sku": "widget"}), None)

    assert_v2_response(response)
    assert response["statusCode"] == 200
    assert json.loads(response["body"]) == {"sku": "widget", "quantity": 5}


def test_missing_sku_returns_404(ddb):
    response = handler(make_api_event(path_parameters={"sku": "absent"}), None)

    assert_v2_response(response)
    assert response["statusCode"] == 404
    assert json.loads(response["body"]) == {"error": "not_found"}


def test_path_parameter_selects_the_sku(ddb):
    ddb.put_item(
        TableName="mrf-inventory",
        Item={"sku": {"S": "gadget"}, "quantity": {"N": "7"}},
    )

    response = handler(make_api_event(path_parameters={"sku": "gadget"}), None)

    assert response["statusCode"] == 200
    assert json.loads(response["body"]) == {"sku": "gadget", "quantity": 7}


def test_missing_or_invalid_path_parameter_returns_400(ddb):
    for event in [make_api_event(), make_api_event(path_parameters={"sku": "bad sku"})]:
        response = handler(event, None)
        assert response["statusCode"] == 400
        assert json.loads(response["body"])["error"] == "invalid_sku"
