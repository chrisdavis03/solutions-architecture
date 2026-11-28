"""Shared helpers for the multi-region-failover Lambda handlers.

Stdlib + boto3 only. No AWS client is constructed at import time, so every
handler module can be imported without credentials or a configured region.
"""

from __future__ import annotations

import base64
import functools
import json
import logging
import os
import re
from decimal import Decimal
from typing import Any

logger = logging.getLogger("mrf")
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

# Shared by checkout and inventory. Restrictive on purpose: SKUs end up as
# DynamoDB keys and in URL paths.
SKU_PATTERN = re.compile(r"[A-Za-z0-9._-]{1,64}")

_JSON_HEADERS = {"content-type": "application/json"}


class RequestError(Exception):
    """Client-side input problem. Maps to a 400 response."""

    def __init__(self, code: str, message: str | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.message = message


# --- AWS clients (lazy) -------------------------------------------------------

@functools.lru_cache(maxsize=None)
def dynamodb_client():
    """Return a cached DynamoDB client. The region comes from AWS_REGION."""
    import boto3  # imported here so the module stays importable without boto3

    return boto3.client("dynamodb")


# --- configuration ------------------------------------------------------------

def table_name(env_key: str) -> str:
    """Resolve a table name from the Lambda environment (e.g. ORDERS_TABLE)."""
    name = os.environ.get(env_key)
    if not name:
        # Misconfiguration, not client error: let it surface as a 500.
        raise RuntimeError(f"required environment variable {env_key} is not set")
    return name


def error_code(exc: BaseException) -> str:
    """Return the AWS error code (e.g. 'ConditionalCheckFailedException')."""
    response = getattr(exc, "response", None) or {}
    return response.get("Error", {}).get("Code", "")


# --- DynamoDB attribute conversion --------------------------------------------

def to_dynamo(item: dict[str, Any]) -> dict[str, Any]:
    """Convert a plain dict into the low-level DynamoDB attribute format."""
    from boto3.dynamodb.types import TypeSerializer

    serializer = TypeSerializer()
    return {key: serializer.serialize(value) for key, value in item.items()}


def from_dynamo(item: dict[str, Any]) -> dict[str, Any]:
    """Convert low-level DynamoDB attributes into a plain dict.

    Numbers come back as Decimal; json_response() renders them as int/float.
    """
    from boto3.dynamodb.types import TypeDeserializer

    deserializer = TypeDeserializer()
    return {key: deserializer.deserialize(value) for key, value in item.items()}


# --- API Gateway (HTTP API, payload format 2.0) responses ---------------------

def _json_default(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return int(obj) if obj == obj.to_integral_value() else float(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def json_response(status: int, payload: Any) -> dict[str, Any]:
    return {
        "statusCode": status,
        "headers": dict(_JSON_HEADERS),
        "body": json.dumps(payload, default=_json_default),
    }


def error_response(status: int, code: str, message: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"error": code}
    if message:
        payload["message"] = message
    return json_response(status, payload)


def parse_json_body(event: dict[str, Any]) -> dict[str, Any]:
    """Parse the JSON object in the request body, or raise RequestError."""
    raw = event.get("body")
    if not raw:
        raise RequestError("invalid_json", "request body must be a JSON object")
    try:
        if event.get("isBase64Encoded"):
            raw = base64.b64decode(raw).decode("utf-8")
        body = json.loads(raw)
    except ValueError:  # covers JSONDecodeError, UnicodeDecodeError, binascii.Error
        raise RequestError("invalid_json", "request body is not valid JSON") from None
    if not isinstance(body, dict):
        raise RequestError("invalid_json", "request body must be a JSON object")
    return body


# --- logging ------------------------------------------------------------------

def log(level: int, event: str, **fields: Any) -> None:
    """Emit one JSON log line per event so CloudWatch Logs Insights can query fields."""
    logger.log(level, json.dumps({"event": event, **fields}, default=str))
