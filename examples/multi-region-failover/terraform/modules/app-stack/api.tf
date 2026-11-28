locals {
  # method and arn_path build the execute-api source ARN for the invoke
  # permission. arn_path uses a wildcard for path parameters.
  routes = {
    healthz   = { method = "GET", path = "/healthz", arn_path = "/healthz" }
    inventory = { method = "GET", path = "/inventory/{sku}", arn_path = "/inventory/*" }
    checkout  = { method = "POST", path = "/checkout", arn_path = "/checkout" }
  }
}

# HTTP API (API Gateway v2). $default stage with auto-deploy: changes apply on save, no manual deployment step.
resource "aws_apigatewayv2_api" "this" {
  name          = "${local.stack}-api"
  protocol_type = "HTTP"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.this.id
  name        = "$default"
  auto_deploy = true
}

resource "aws_apigatewayv2_integration" "fn" {
  for_each = local.routes

  api_id                 = aws_apigatewayv2_api.this.id
  integration_type       = "AWS_PROXY"
  integration_method     = "POST"
  integration_uri        = aws_lambda_function.fn[each.key].invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "this" {
  for_each = local.routes

  api_id    = aws_apigatewayv2_api.this.id
  route_key = "${each.value.method} ${each.value.path}"
  target    = "integrations/${aws_apigatewayv2_integration.fn[each.key].id}"
}

resource "aws_lambda_permission" "apigw" {
  for_each = local.routes

  statement_id  = "AllowApiGateway-${each.key}"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.fn[each.key].function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.this.execution_arn}/*/${each.value.method}${each.value.arn_path}"
}
