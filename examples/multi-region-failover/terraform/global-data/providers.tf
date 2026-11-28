# The default provider is the primary region. Route 53 is a global service, so
# the DNS resources use the default provider. The DynamoDB tables pin
# explicitly to the aws.primary alias so the table placement is visible in the
# code. Replicas are declared on those tables and do not need a provider alias.

provider "aws" {
  region = var.primary_region
}

provider "aws" {
  alias  = "primary"
  region = var.primary_region
}
