variable "region" {
  description = "AWS region for the primary stack."
  type        = string
  default     = "us-east-1"
}

variable "orders_table_name" {
  description = "Orders Global Table name. Must match the value used in terraform/global-data."
  type        = string
  default     = "mrf-orders"
}

variable "inventory_table_name" {
  description = "Inventory Global Table name. Must match the value used in terraform/global-data."
  type        = string
  default     = "mrf-inventory"
}
