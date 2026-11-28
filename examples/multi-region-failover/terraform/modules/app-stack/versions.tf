terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.60"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
  }
}

# No provider block here on purpose. The calling root configures the region
# (app-primary or app-secondary), and this module inherits it. That is what
# lets one module be instantiated once per region.
