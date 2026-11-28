# Two Global Tables (version 2019.11.21), each created in the primary region
# with a replica in the secondary region.
#
# Demo settings: deletion protection and PITR are OFF. Production deltas:
#   - deletion_protection_enabled = true on both tables
#   - point_in_time_recovery enabled (both tables, and on each replica)
#   - a KMS key you manage, not the AWS-owned default
#   - backups and an alarm on replication latency (ReplicationLatency metric)
#
# Replication semantics (read this before reusing the pattern):
#   - Replication is asynchronous, typically within about a second, with no
#     bound guaranteed.
#   - Conflicts are resolved last-writer-wins per item. A decrement of
#     `quantity` in one region can be overwritten by a concurrent write from the
#     other region, so the stock check is not global. See the comments in
#     lambda/checkout.py. Use a single writer per SKU, or allocate stock per
#     region, before relying on this for real inventory.

resource "aws_dynamodb_table" "inventory" {
  provider = aws.primary

  name                        = var.inventory_table_name
  billing_mode                = "PAY_PER_REQUEST"
  hash_key                    = "sku"
  deletion_protection_enabled = false # demo only; enable in production

  attribute {
    name = "sku"
    type = "S"
  }

  # Streams are required for Global Tables replication.
  stream_enabled   = true
  stream_view_type = "NEW_AND_OLD_IMAGES"


  point_in_time_recovery {
    enabled = false # demo only; enable in production
  }

  replica {
    region_name            = var.secondary_region
    point_in_time_recovery = false
  }
}

resource "aws_dynamodb_table" "orders" {
  provider = aws.primary

  name                        = var.orders_table_name
  billing_mode                = "PAY_PER_REQUEST"
  hash_key                    = "order_id"
  deletion_protection_enabled = false # demo only; enable in production

  attribute {
    name = "order_id"
    type = "S"
  }

  attribute {
    name = "status"
    type = "S"
  }

  attribute {
    name = "created_at"
    type = "S"
  }

  # The sweeper reads pending orders through this index. Its ARN is the only
  # index the app roles can query (see terraform/modules/app-stack/iam.tf).
  global_secondary_index {
    name            = "status-index"
    hash_key        = "status"
    range_key       = "created_at"
    projection_type = "ALL"
  }

  stream_enabled   = true
  stream_view_type = "NEW_AND_OLD_IMAGES"


  point_in_time_recovery {
    enabled = false # demo only; enable in production
  }

  replica {
    region_name            = var.secondary_region
    point_in_time_recovery = false
  }
}
