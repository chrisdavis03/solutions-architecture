data "aws_region" "current" {}

data "aws_dynamodb_table" "orders" {
  name = var.orders_table_name
}

data "aws_dynamodb_table" "inventory" {
  name = var.inventory_table_name
}

locals {
  # Region in the stack name keeps IAM roles (account-global) and functions unique per region.
  stack = "${var.name_prefix}-${data.aws_region.current.name}"

  # Layout: examples/multi-region-failover/{lambda,terraform/modules/app-stack}.
  # From modules/app-stack, ../../../ resolves to examples/multi-region-failover.
  # Everything under lambda/ is zipped once and shared by every function.
  # Each function picks its handler by filename.
  lambda_source_dir = "${path.module}/../../../lambda"
  build_dir         = "${path.module}/../../../.build"

  # Sweeper only exists when enable_sweeper is true, so the for_each map
  # (and everything keyed on it) drops it when disabled.
  functions = merge(
    {
      checkout  = { module = "checkout", timeout = 10 }
      inventory = { module = "inventory", timeout = 5 }
      healthz   = { module = "healthz", timeout = 3 }
    },
    var.enable_sweeper ? { sweeper = { module = "sweeper", timeout = 60 } } : {}
  )
}
