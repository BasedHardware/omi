terraform {
  required_version = ">= 1.12.4, < 2.0.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }

  # The bucket and prefix are intentionally supplied only at initialization
  # time from a reviewed, environment-specific backend config file.
  backend "gcs" {}
}
