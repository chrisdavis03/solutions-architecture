output "inventory_table_name" {
  description = "Inventory table name. Pass to the app roots as inventory_table_name."
  value       = aws_dynamodb_table.inventory.name
}

output "inventory_table_arn" {
  description = "Inventory table ARN in the primary region."
  value       = aws_dynamodb_table.inventory.arn
}

output "orders_table_name" {
  description = "Orders table name. Pass to the app roots as orders_table_name."
  value       = aws_dynamodb_table.orders.name
}

output "orders_table_arn" {
  description = "Orders table ARN in the primary region."
  value       = aws_dynamodb_table.orders.arn
}

output "checkout_fqdn" {
  description = "Public failover hostname, checkout.<domain_name>."
  value       = local.checkout_fqdn
}

output "primary_health_check_id" {
  description = "Route 53 health check ID for the primary. Null until enable_traffic is true."
  value       = try(aws_route53_health_check.primary[0].id, null)
}
