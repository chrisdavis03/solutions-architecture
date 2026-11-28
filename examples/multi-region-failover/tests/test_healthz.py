"""Tests for GET /healthz: cheap liveness, no data-tier dependency."""

from __future__ import annotations

import boto3
import common
from conftest import assert_v2_response
from healthz import handler


def test_healthz_returns_ok_with_region_and_never_calls_dynamodb(monkeypatch):
    monkeypatch.setenv("AWS_REGION", "us-west-2")

    def forbidden_client(*args, **kwargs):
        raise AssertionError("healthz must not construct an AWS client")

    monkeypatch.setattr(common, "dynamodb_client", forbidden_client)
    monkeypatch.setattr(boto3, "client", forbidden_client)

    response = handler({}, None)

    assert_v2_response(response)
    assert response["statusCode"] == 200
    assert response["headers"] == {"content-type": "application/json"}
    assert response["body"] == '{"status": "ok", "region": "us-west-2"}'


def test_healthz_defaults_region_to_unknown_when_unset(monkeypatch):
    monkeypatch.delenv("AWS_REGION", raising=False)
    response = handler({}, None)
    assert response["statusCode"] == 200
    assert '"region": "unknown"' in response["body"]
