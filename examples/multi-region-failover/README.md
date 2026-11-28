# Multi-region failover

A runnable warm-standby reference system for an order checkout that shares inventory across regions. The primary region serves traffic; a second region is fully provisioned and takes over when a Route 53 health check marks the primary unhealthy. Data lives in DynamoDB Global Tables, so the standby reads and writes the same logical tables.

Architecture at a glance:

- **Route 53 failover** — `checkout.<domain>` is a pair of CNAME records, PRIMARY and SECONDARY, with an HTTPS health check on the primary API's `/healthz` (30 s interval, 3 failures, TTL 60 s).
- **Two identical regional stacks** — API Gateway HTTP API plus Python 3.12 Lambdas (`checkout`, `inventory`, `healthz`, and `sweeper` in the standby only).
- **DynamoDB Global Tables** — `mrf-orders` and `mrf-inventory`, each with a replica in the standby region. Replication is asynchronous and last-writer-wins.
- **One transaction per checkout** — a conditional stock decrement and a conditional order insert in a single `TransactWriteItems` call, with idempotent replay on the same `order_id`.
- **Sweeper** — an EventBridge `rate(5 minutes)` schedule in the standby that promotes `pending` orders through the `status-index` GSI.

Diagram source: [`diagrams/multi-region-failover.drawio`](../../diagrams/multi-region-failover.drawio). The PNG/SVG export is a manual step; see [Diagram export](#diagram-export).

## Prerequisites

- **AWS credentials** with permission to manage DynamoDB tables and replicas, Lambda functions and roles, API Gateway HTTP APIs, CloudWatch Logs and Events, Route 53 hosted-zone records and health checks, and IAM roles/policies. `sts:GetCallerIdentity` is handy for a sanity check.
- **OpenTofu** `tofu` >= 1.6. The stacks are plain HCL and also work with Terraform 1.6+ if you swap the binary in every command below.
- **Python 3.11 or 3.12** for the test suite.
- **An existing public Route 53 hosted zone and a domain you own.** This example looks the zone up by name and never creates it. The registrar must already point at the zone's name servers.

> **Cost warning.** This runs in two regions. Global Tables roughly double the table write cost and add cross-region replication transfer; the idle Lambdas and HTTP APIs are cheap but not free; the Route 53 health check is billed. Expect a few dollars a month at rest, plus normal request and transfer charges at demo traffic. Destroy the stacks when you are done (see [Teardown](#teardown)).

## Layout

```text
examples/multi-region-failover/
├── README.md
├── lambda/
│   ├── common.py        # shared helpers: JSON responses, DynamoDB conversion, logging
│   ├── checkout.py      # POST /checkout
│   ├── inventory.py     # GET /inventory/{sku}
│   ├── healthz.py       # GET /healthz (no data-tier call)
│   └── sweeper.py       # scheduled promotion of pending orders
├── terraform/
│   ├── modules/app-stack/   # shared Lambda + HTTP API module, instantiated per region
│   ├── global-data/         # tables, replicas, health check, failover records
│   ├── app-primary/         # us-east-1 app stack (sweeper disabled)
│   └── app-secondary/       # us-west-2 app stack (sweeper enabled)
└── tests/
    ├── conftest.py
    ├── test_*.py
    └── requirements-dev.txt
```

Each root keeps its own local state. That is fine for a demo and wrong for production; see [Production deltas](#production-deltas--not-for-production).

## Deploy (three phases)

The order matters: the failover records need the API hostnames that only exist after the app stacks apply, and the app stacks read table names that only exist after the data stack applies. Keep `enable_traffic=false` until both regions are up.

From `examples/multi-region-failover`, set these once and use the same values everywhere. `EXAMPLE_DIR` keeps every later block copy-pasteable no matter which directory the previous block left you in.

```bash
export EXAMPLE_DIR=$(pwd)          # run this from examples/multi-region-failover
export DOMAIN=example.com          # the hosted zone you already own
export PRIMARY_REGION=us-east-1
export SECONDARY_REGION=us-west-2
```

### Phase 1 — data

Create the Global Tables and their replicas. Traffic resources stay off.

```bash
cd "$EXAMPLE_DIR/terraform/global-data"
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars: set domain_name, and the regions if you changed them.
# Leave enable_traffic = false.
tofu init
tofu apply
```

Verify the replica is live before moving on:

```bash
aws dynamodb describe-table \
  --region "$PRIMARY_REGION" \
  --table-name mrf-inventory \
  --query 'Table.Replicas[].ReplicaStatus' \
  --output text
```

Wait for `ACTIVE`.

### Phase 2 — apps

Deploy both regional stacks. The primary runs without the sweeper; the secondary runs with it, so exactly one region promotes orders.

```bash
cd "$EXAMPLE_DIR/terraform/app-primary"
cp terraform.tfvars.example terraform.tfvars
tofu init
tofu apply
export PRIMARY_HOST=$(tofu output -raw api_hostname)
export PRIMARY_ENDPOINT=$(tofu output -raw api_endpoint)

cd "$EXAMPLE_DIR/terraform/app-secondary"
cp terraform.tfvars.example terraform.tfvars
tofu init
tofu apply
export SECONDARY_HOST=$(tofu output -raw api_hostname)
export SECONDARY_ENDPOINT=$(tofu output -raw api_endpoint)
```

Both `api_hostname` values are bare hostnames (no `https://`). Confirm they are set:

```bash
printf 'primary=%s\nsecondary=%s\n' "$PRIMARY_HOST" "$SECONDARY_HOST"
```

### Phase 3 — traffic

Re-apply the data stack with the health check and failover records enabled. These `-var` flags override only this apply; set the same three values in `terraform.tfvars` if you want them to stick.

```bash
cd "$EXAMPLE_DIR/terraform/global-data"
tofu apply \
  -var "enable_traffic=true" \
  -var "primary_api_hostname=$PRIMARY_HOST" \
  -var "secondary_api_hostname=$SECONDARY_HOST"
```

Capture the health check ID for the drill:

```bash
export HEALTH_CHECK_ID=$(tofu output -raw primary_health_check_id)
echo "$HEALTH_CHECK_ID"
```

## Smoke test

Seed one SKU first. The stacks create empty tables, so `GET /inventory/widget` would otherwise return `404` and every checkout would fail the stock condition.

```bash
aws dynamodb put-item \
  --region "$PRIMARY_REGION" \
  --table-name mrf-inventory \
  --item '{"sku":{"S":"widget"},"quantity":{"N":"5"}}'
```

Call the primary regional endpoint directly. This is the path that works out of the box:

```bash
curl -sS "$PRIMARY_ENDPOINT/healthz"
# {"status": "ok", "region": "us-east-1"}

curl -sS "$PRIMARY_ENDPOINT/inventory/widget"
# {"sku": "widget", "quantity": 5}

curl -sS -X POST "$PRIMARY_ENDPOINT/checkout" \
  -H 'content-type: application/json' \
  -d '{"sku":"widget","quantity":2,"order_id":"demo-1"}'
# {"order_id": "demo-1", "sku": "widget", "quantity": 2, "status": "pending",
#  "created_at": "2026-11-28T12:00:00+00:00"}

curl -sS -X POST "$PRIMARY_ENDPOINT/checkout" \
  -H 'content-type: application/json' \
  -d '{"sku":"widget","quantity":99,"order_id":"demo-2"}'
# {"error": "insufficient_stock"}
```

Expected status codes are `201` for the first checkout and `409` for the over-order. To show the code explicitly:

```bash
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$PRIMARY_ENDPOINT/checkout" \
  -H 'content-type: application/json' \
  -d '{"sku":"widget","quantity":99,"order_id":"demo-3"}'
# 409
```

The intended public path is `checkout.<domain>`:

```bash
curl -sSk "https://checkout.$DOMAIN/healthz"
# {"status": "ok", "region": "us-east-1"}   # once the custom domain exists
```

Use `-k` here. The example wires DNS failover but does **not** create an API Gateway custom domain (ACM certificate plus domain name plus API mapping). Until you add one, the CNAME target presents a certificate for `*.execute-api.<region>.amazonaws.com`, and because a Regional endpoint routes by the `Host` header you may also get a `403`. The health check is unaffected because it calls the execute-api hostname directly with SNI. For day-to-day testing, use `$PRIMARY_ENDPOINT` / `$SECONDARY_ENDPOINT`.

## Failover drill

Break the health check by pointing it at a path the handler does not serve. This marks the primary unhealthy without touching the data layer or the API.

```bash
cd "$EXAMPLE_DIR/terraform/global-data"
export HEALTH_CHECK_ID=$(tofu output -raw primary_health_check_id)

aws route53 update-health-check \
  --health-check-id "$HEALTH_CHECK_ID" \
  --resource-path /broken

aws route53 get-health-check-status --health-check-id "$HEALTH_CHECK_ID"
```

Detection math: Route 53 checks every 30 s and needs 3 consecutive failures, so the primary is marked unhealthy after about 90 s. Clients may cache the old answer for up to the 60 s TTL, and Route 53 takes a moment to publish the new answer. Budget roughly **2.5–3 minutes** for traffic to move, which is inside the 5-minute RTO.

Poll DNS and the endpoint it resolves to:

```bash
while true; do
  target=$(dig +short "checkout.$DOMAIN" | tail -n1)
  region=$(curl -sSk "https://$target/healthz" | jq -r .region)
  echo "target=$target region=$region"
  [ "$region" = "$SECONDARY_REGION" ] && break
  sleep 15
done
```

`jq` is optional; `python3 -c 'import json,sys; print(json.load(sys.stdin)["region"])'` reads the same field. A successful drill ends with `region=us-west-2`.

Then confirm the standby serves a checkout:

```bash
curl -sS "$SECONDARY_ENDPOINT/inventory/widget"
curl -sS -X POST "$SECONDARY_ENDPOINT/checkout" \
  -H 'content-type: application/json' \
  -d '{"sku":"widget","quantity":1,"order_id":"drill-1"}'
```

Restore the check:

```bash
aws route53 update-health-check \
  --health-check-id "$HEALTH_CHECK_ID" \
  --resource-path /healthz
```

## Split-brain demo (the teaching moment)

Leave the primary healthy and write to the standby **directly**, bypassing Route 53. This simulates two writers accepting orders for the same SKU at once.

```bash
# Standby accepts a checkout while the primary is still serving.
curl -sS -X POST "$SECONDARY_ENDPOINT/checkout" \
  -H 'content-type: application/json' \
  -d '{"sku":"widget","quantity":1,"order_id":"split-1"}'

# Read the same item from each region.
aws dynamodb get-item --region "$PRIMARY_REGION" --table-name mrf-inventory \
  --key '{"sku":{"S":"widget"}}' --query 'Item.quantity.N' --output text

aws dynamodb get-item --region "$SECONDARY_REGION" --table-name mrf-inventory \
  --key '{"sku":{"S":"widget"}}' --query 'Item.quantity.N' --output text
```

Both reads report a decrement for a moment, then the replicas converge. Global Tables resolve conflicts **last-writer-wins per item**, so one decrement survives and the other is silently dropped. The SKU can therefore be oversold even though each region's conditional decrement (`attribute_exists(sku) AND quantity >= :qty`) passed locally.

This is deliberate. The example uses a single writer plus failover, not active/active. If you need multi-region writes, allocate stock per region (escrow) or use one writer per SKU; a global counter is not what DynamoDB gives you.

## Failback

Restore the health check (the command is at the end of the drill), then wait for the PRIMARY record to pass again and traffic to return:

```bash
while true; do
  target=$(dig +short "checkout.$DOMAIN" | tail -n1)
  region=$(curl -sSk "https://$target/healthz" | jq -r .region)
  echo "target=$target region=$region"
  [ "$region" = "$PRIMARY_REGION" ] && break
  sleep 15
done
```

Replication is bidirectional, so there is no manual re-seed. Two caveats:

- Writes in flight during the flip can be lost. LWW keeps one copy of a conflicting item; it does not merge.
- The sweeper runs only in the standby on a 5-minute schedule. Orders left `pending` are promoted on its next run after it is reachable again.

## Tests

The suite is offline: `moto` emulates DynamoDB, credentials are dummy, and no AWS call leaves the machine.

```bash
cd "$EXAMPLE_DIR"
python3 -m venv .venv
. .venv/bin/activate
pip install -r tests/requirements-dev.txt
python3 -m pytest -q
```

Expected: **48 passed** (pytest 8.x, moto 5.x). The tests cover checkout atomicity and idempotency, invalid input, inventory reads, healthz, the sweeper's pagination and conditional-update races, and the shared response helpers.

## Diagram export

The source is [`diagrams/multi-region-failover.drawio`](../../diagrams/multi-region-failover.drawio). No draw.io CLI is installed in this repo, so the export is manual:

1. Open the `.drawio` file in draw.io (desktop or the web app).
2. Export a PNG or SVG beside the source (`diagrams/multi-region-failover.png` or `.svg`).
3. Commit the export. Generated render artifacts belong in `diagrams/.render/`, which is gitignored — never link to that directory.

Do not invent a PNG path in the README or post before the export exists.

## Teardown

Destroy traffic resources first so the records and health check go away while the APIs they point at still exist, then the app stacks, then the data.

```bash
# 1. Remove records and the health check.
cd "$EXAMPLE_DIR/terraform/global-data"
tofu apply -var "enable_traffic=false"

# 2. Destroy both regional app stacks.
cd "$EXAMPLE_DIR/terraform/app-secondary"
tofu destroy
cd "$EXAMPLE_DIR/terraform/app-primary"
tofu destroy

# 3. Destroy the tables and replicas.
cd "$EXAMPLE_DIR/terraform/global-data"
tofu destroy
```

Deletion protection and point-in-time recovery are **off** for the demo, so the table destroy is immediate and unrecoverable. Do not run this against anything you care about.

## Production deltas / not for production

- **No authentication.** The API routes are public. Add an authorizer (JWT, IAM, or Lambda) before exposing anything.
- **Deletion protection and PITR are off**, and the tables use the AWS-owned key. Enable both, use a customer-managed KMS key, and alarm on `ReplicationLatency`.
- **Local state.** Each root has its own `terraform.tfstate`. Use a remote backend with locking, one state key per root.
- **Single-writer discipline is required.** The conditional update prevents overselling inside one region, not across replicas. Keep writes in one region, or partition stock per region.
- **The public hostname is incomplete.** Add a Regional API Gateway custom domain per region (ACM certificate, domain name, API mapping) so `checkout.<domain>` serves a valid certificate and routes correctly.
- **Automated failover** is a much better fit than mutating a health check by hand. Route 53 Application Recovery Controller (ARC) routing controls give you audited, reversible traffic shifts; the manual drill here is for learning.
- **The sweeper is a stand-in.** EventBridge Global Endpoints are the managed alternative for cross-region event delivery. SQS is regional, so messages sitting in a dead region are trapped — that is exactly why this example runs a sweeper in the standby instead of relying on a queue.
- **No game day, no confidence.** Schedule the drill and failback; a failover you have not run is a drawing.

## Troubleshooting

- **Health check stays green when it should be red.** Check the path and hostname on the check (`aws route53 get-health-check --id "$HEALTH_CHECK_ID"`), confirm `enable_sni=true`, and make sure you are editing the check attached to the PRIMARY record, not a different one.
- **DNS still returns the old region.** The record TTL is 60 s; resolvers and clients may cache longer. Re-run `dig +short "checkout.$DOMAIN"` and try a different resolver.
- **`ReplicaStatus` is not `ACTIVE`.** Replication is asynchronous. Wait, then re-check `describe-table`. Applies against a table whose replica is still creating can fail.
- **`data.aws_route53_zone` lookup fails.** The hosted zone must already exist, be public, and match `domain_name`. This stack never creates it. Confirm the zone's name servers are set at your registrar.
- **`checkout.<domain>` returns a certificate error or 403.** Expected until you add the API Gateway custom domain described in [Production deltas](#production-deltas--not-for-production). Test the regional endpoints directly.
- **Checkout returns `409 insufficient_stock` immediately.** The inventory table is empty. Seed the SKU (see [Smoke test](#smoke-test)) or check that `inventory_table_name` matches between the data stack and the app stacks.
