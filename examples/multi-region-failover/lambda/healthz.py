"""GET /healthz: liveness for the Route 53 health check.

Deliberately makes no DynamoDB call. The check should stay cheap and report
"this region's API and Lambda are up", not "the data layer is healthy". That
also means the endpoint can keep answering during a data-tier problem. The
failover demo uses it on purpose: a region can be marked unhealthy by
breaking this handler, not by touching the tables.
"""

from __future__ import annotations

import os
from typing import Any

from common import json_response


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    # AWS_REGION is set by the Lambda runtime, so this reports the region the
    # function actually runs in.
    return json_response(200, {"status": "ok", "region": os.environ.get("AWS_REGION", "unknown")})
