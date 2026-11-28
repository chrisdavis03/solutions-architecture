output "api_endpoint" {
  description = "Default execute-api endpoint URL for this region's HTTP API (https://...)."
  value       = aws_apigatewayv2_api.this.api_endpoint
}

output "api_hostname" {
  description = "Host part of api_endpoint, without scheme. Used as the CNAME target in global-data."
  value       = trimprefix(aws_apigatewayv2_api.this.api_endpoint, "https://")
}

output "api_id" {
  description = "HTTP API ID."
  value       = aws_apigatewayv2_api.this.id
}
