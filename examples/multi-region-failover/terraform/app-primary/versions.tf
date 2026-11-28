terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.60"
    }
  }

  # Local state for the demo. Real use needs a remote backend (for example S3
  # with a DynamoDB lock table) so state is shared and locked. Do not commit *.tfstate.
  # backend "s3" {}
}
