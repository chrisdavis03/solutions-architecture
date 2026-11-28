output "api_endpoint" {
  description = "Default execute-api endpoint for the secondary region's HTTP API."
  value       = module.app.api_endpoint
}

output "api_hostname" {
  description = "Host part of api_endpoint. Set as primary_api_hostname or secondary_api_hostname in terraform/global-data."
  value       = module.app.api_hostname
}
