terraform {
  required_version = ">= 1.9"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.0, < 7.0"
    }
  }

  # Local state in a .nosync folder (kept out of iCloud and git).
  backend "local" {
    path = "state.nosync/dev.tfstate"
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project   = "f1-race-analytics"
      ManagedBy = "terraform"
    }
  }
}
