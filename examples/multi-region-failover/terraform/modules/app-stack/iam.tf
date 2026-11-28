# One execution role per function, so each function only gets the table
# actions it actually uses. Role names carry the region because IAM is global
# to the account and both regional stacks would otherwise collide.

data "aws_iam_policy_document" "assume_lambda" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "fn" {
  for_each = local.functions

  name               = "${local.stack}-${each.key}"
  assume_role_policy = data.aws_iam_policy_document.assume_lambda.json
}

# Logs: scoped to this function's own log group, not "*".
data "aws_iam_policy_document" "logs" {
  for_each = local.functions

  statement {
    sid       = "WriteOwnLogGroup"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${trimsuffix(aws_cloudwatch_log_group.fn[each.key].arn, ":*")}:*"]
  }
}

resource "aws_iam_role_policy" "logs" {
  for_each = local.functions

  name   = "logs"
  role   = aws_iam_role.fn[each.key].id
  policy = data.aws_iam_policy_document.logs[each.key].json
}

# Table access, per function. No wildcard actions or resources. GSI access is
# granted by ARN (<table>/index/<name>), not by a table-wide Query.
locals {
  orders_arn    = data.aws_dynamodb_table.orders.arn
  inventory_arn = data.aws_dynamodb_table.inventory.arn

  table_access = {
    # Checkout's TransactWriteItems needs UpdateItem on inventory and PutItem
    # on orders. GetItem on orders is for the idempotent-replay path.
    checkout = [
      { actions = ["dynamodb:UpdateItem"], resources = [local.inventory_arn] },
      { actions = ["dynamodb:PutItem", "dynamodb:GetItem"], resources = [local.orders_arn] },
    ]
    inventory = [
      { actions = ["dynamodb:GetItem"], resources = [local.inventory_arn] },
    ]
    # healthz: no table access, by design (see healthz.py).
    sweeper = [
      { actions = ["dynamodb:Query"], resources = ["${local.orders_arn}/index/status-index"] },
      { actions = ["dynamodb:UpdateItem"], resources = [local.orders_arn] },
    ]
  }

  functions_with_table_access = { for k, v in local.functions : k => v if length(lookup(local.table_access, k, [])) > 0 }
}

data "aws_iam_policy_document" "table_access" {
  for_each = local.functions_with_table_access

  dynamic "statement" {
    for_each = local.table_access[each.key]

    content {
      actions   = statement.value.actions
      resources = statement.value.resources
    }
  }
}

resource "aws_iam_role_policy" "table_access" {
  for_each = local.functions_with_table_access

  name   = "dynamodb"
  role   = aws_iam_role.fn[each.key].id
  policy = data.aws_iam_policy_document.table_access[each.key].json
}
