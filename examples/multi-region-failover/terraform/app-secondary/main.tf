# Thin wrapper around the shared module. Every resource lives in the module,
# so this root only chooses the region and the sweeper setting.
module "app" {
  source = "../modules/app-stack"

  name_prefix          = "mrf"
  orders_table_name    = var.orders_table_name
  inventory_table_name = var.inventory_table_name
  enable_sweeper       = true
}
