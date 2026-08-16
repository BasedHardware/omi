terraform {
  required_version = ">= 1.12.4, < 2.0.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
}

variable "project_id" {
  type        = string
  description = "The project that the WIF plan pilot may read."
  default     = "based-hardware-dev"

  validation {
    condition     = var.project_id == "based-hardware-dev"
    error_message = "The pilot probe may read only based-hardware-dev."
  }
}

provider "google" {
  project = var.project_id
}

data "google_project" "development" {
  project_id = var.project_id
}

output "project_number" {
  value       = data.google_project.development.number
  description = "Confirms the WIF principal can read the expected development project only."
}
