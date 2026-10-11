variable "project_id" {
  type        = string
  description = "Development-only GCP project."
  default     = "based-hardware-dev"

  validation {
    condition     = var.project_id == "based-hardware-dev"
    error_message = "This slice may target only based-hardware-dev."
  }
}

variable "project_number" {
  type        = string
  description = "Immutable based-hardware-dev project number."
  default     = "1031333818730"

  validation {
    condition     = var.project_number == "1031333818730"
    error_message = "This slice may target only the based-hardware-dev project number."
  }
}

variable "github_repository_id" {
  type        = string
  default     = "776121034"

  validation {
    condition     = var.github_repository_id == "776121034"
    error_message = "Must stay restricted to Omi's immutable GitHub repository ID."
  }
}

variable "github_repository_owner_id" {
  type        = string
  default     = "162546372"

  validation {
    condition     = var.github_repository_owner_id == "162546372"
    error_message = "Must stay restricted to BasedHardware's immutable GitHub organization ID."
  }
}

variable "github_workflow_ref" {
  type        = string
  default     = "BasedHardware/omi/.github/workflows/gcp_notifications_job.yml@refs/heads/main"

  validation {
    condition     = var.github_workflow_ref == "BasedHardware/omi/.github/workflows/gcp_notifications_job.yml@refs/heads/main"
    error_message = "Must stay restricted to gcp_notifications_job.yml on main."
  }
}

variable "workload_identity_pool_id" {
  type        = string
  default     = "omi-gha-notif-dev"

  validation {
    condition     = var.workload_identity_pool_id == "omi-gha-notif-dev"
    error_message = "Must use the dedicated notifications-job development WIF pool."
  }
}

variable "deploy_service_account_id" {
  type        = string
  default     = "omi-gha-notif-job-dev"

  validation {
    condition     = var.deploy_service_account_id == "omi-gha-notif-job-dev"
    error_message = "Must use the dedicated notifications-job development deploy SA."
  }
}

variable "runtime_service_account_email" {
  type        = string
  description = "Live notifications-job runtime SA (actAs only on this email)."
  default     = "1031333818730-compute@developer.gserviceaccount.com"

  validation {
    condition     = var.runtime_service_account_email == "1031333818730-compute@developer.gserviceaccount.com"
    error_message = "actAs must stay pinned to the live notifications-job runtime SA."
  }
}
