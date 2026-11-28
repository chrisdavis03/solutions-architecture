data "archive_file" "lambda" {
  type        = "zip"
  source_dir  = local.lambda_source_dir
  output_path = "${local.build_dir}/${local.stack}-lambda.zip"
  excludes    = ["__pycache__", "*.pyc"]
}

resource "aws_cloudwatch_log_group" "fn" {
  for_each = local.functions

  name              = "/aws/lambda/${local.stack}-${each.key}"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "fn" {
  for_each = local.functions

  function_name    = "${local.stack}-${each.key}"
  role             = aws_iam_role.fn[each.key].arn
  runtime          = "python3.12"
  handler          = "${each.value.module}.handler"
  filename         = data.archive_file.lambda.output_path
  source_code_hash = data.archive_file.lambda.output_base64sha256
  memory_size      = 256
  timeout          = each.value.timeout

  environment {
    variables = {
      ORDERS_TABLE    = data.aws_dynamodb_table.orders.name
      INVENTORY_TABLE = data.aws_dynamodb_table.inventory.name
      LOG_LEVEL       = var.log_level
    }
  }

  # Create the log group first so Terraform owns its retention. Otherwise
  # Lambda creates it with infinite retention on the first invocation.
  depends_on = [aws_cloudwatch_log_group.fn]
}

# --- Sweeper schedule (only when enable_sweeper) -----------------------------

resource "aws_cloudwatch_event_rule" "sweeper" {
  count = var.enable_sweeper ? 1 : 0

  name                = "${local.stack}-sweeper"
  description         = "Promote pending orders to fulfilled"
  schedule_expression = "rate(5 minutes)"
}

resource "aws_cloudwatch_event_target" "sweeper" {
  count = var.enable_sweeper ? 1 : 0

  rule      = aws_cloudwatch_event_rule.sweeper[0].name
  target_id = "sweeper"
  arn       = aws_lambda_function.fn["sweeper"].arn
}

resource "aws_lambda_permission" "sweeper_events" {
  count = var.enable_sweeper ? 1 : 0

  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.fn["sweeper"].function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.sweeper[0].arn
}
