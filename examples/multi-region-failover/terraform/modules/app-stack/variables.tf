variable "name_prefix" {
  description = "Prefix for every resource name. Region is appended automatically so two regional stacks can coexist in one account."
  type        = string
  default     = "mrf"
}

variable "orders_table_name" {
  description = "Name of the orders table. Created by terraform/global-data; this module only reads its ARN."
  type        = string
  default     = "mrf-orders"
}

variable "inventory_table_name" {
  description = "Name of the inventory table. Created by terraform/global-data; this module only reads its ARN."
  type        = string
  default     = "mrf-inventory"
}

variable "enable_sweeper" {
  description = "Deploy the sweeper Lambda and its 5-minute EventBridge schedule. Enable in one region only, or both regions will promote the same orders."
  type        = bool
  default     = false
}

variable "log_level" {
  description = "LOG_LEVEL passed to the Lambda functions."
  type        = string
  default     = "INFO"

  validation {
    condition     = contains(["DEBUG", "INFO", "WARNING", "ERROR"], var.log_level)
    error_message = "log_level must be one of DEBUG, INFO, WARNING, ERROR."
  }
}

variable "log_retention_days" {
  description = "CloudWatch Logs retention for each function's log group."
  type        = number
  default     = 7
}
