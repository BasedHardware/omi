terraform {
  required_version = ">= 1.12.0, < 2.0.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "8.1.0"
    }
  }
}

provider "google" {
  project = "based-hardware-dev"
  region  = "us-central1"
}

resource "google_storage_bucket" "state" {
  project                     = "based-hardware-dev"
  name                        = "based-hardware-dev-omi-platform-tfstate"
  location                    = "US-CENTRAL1"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false
  labels = {
    environment = "dev"
    application = "omi-platform"
    managed_by  = "opentofu"
  }
  versioning {
    enabled = true
  }
  lifecycle {
    prevent_destroy = true
  }
}

output "state_bucket" {
  value = google_storage_bucket.state.name
}
