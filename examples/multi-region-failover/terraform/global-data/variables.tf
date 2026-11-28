variable "primary_region" {
  description = "Region that serves traffic when healthy. Also the Global Table writer region for the demo."
  type        = string
  default     = "us-east-1"
}

variable "secondary_region" {
  description = "Warm-standby region. Holds a Global Table replica and takes traffic when the primary fails its health check."
  type        = string
  default     = "us-west-2"
}

variable "domain_name" {
  description = "A public Route 53 hosted zone you already own (e.g. example.com). This stack looks it up and never creates it. Checkout is served at checkout.<domain_name>."
  type        = string
}

variable "orders_table_name" {
  description = "Name of the orders Global Table."
  type        = string
  default     = "mrf-orders"
}

variable "inventory_table_name" {
  description = "Name of the inventory Global Table."
  type        = string
  default     = "mrf-inventory"
}

variable "enable_traffic" {
  description = "Create the health check and failover records. Keep false on the first apply (tables only). Set true after both app stacks are deployed and their api_hostname outputs are known. This avoids a circular dependency: records need hostnames that only exist after the app stacks apply."
  type        = bool
  default     = false
}

variable "primary_api_hostname" {
  description = "api_hostname output from terraform/app-primary. Required when enable_traffic is true."
  type        = string
  default     = ""
}

variable "secondary_api_hostname" {
  description = "api_hostname output from terraform/app-secondary. Required when enable_traffic is true."
  type        = string
  default     = ""
}

variable "health_check_interval" {
  description = "Seconds between Route 53 health checks. Valid values are 10 and 30."
  type        = number
  default     = 30

  validation {
    condition     = contains([10, 30], var.health_check_interval)
    error_message = "health_check_interval must be 10 or 30 (Route 53 supported values)."
  }
}

variable "health_check_failure_threshold" {
  description = "Consecutive failures before the primary is marked unhealthy. With a 30s interval, 3 means about 90s to fail over."
  type        = number
  default     = 3
}

variable "record_ttl" {
  description = "TTL in seconds for the failover CNAME records. Low TTL keeps clients from caching the old answer for long."
  type        = number
  default     = 60
}
