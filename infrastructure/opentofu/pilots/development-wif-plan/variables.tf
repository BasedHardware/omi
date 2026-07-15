variable "project_id" {
  type        = string
  description = "The development-only GCP project for the pilot."
  default     = "based-hardware-dev"

  validation {
    condition     = var.project_id == "based-hardware-dev"
    error_message = "The WIF pilot may target only based-hardware-dev."
  }
}

variable "project_number" {
  type        = string
  description = "The immutable project number for based-hardware-dev."
  default     = "1031333818730"

  validation {
    condition     = var.project_number == "1031333818730"
    error_message = "The WIF pilot may target only the based-hardware-dev project number."
  }
}

variable "github_repository" {
  type        = string
  description = "The only GitHub repository allowed to exchange this identity."
  default     = "BasedHardware/omi"

  validation {
    condition     = var.github_repository == "BasedHardware/omi"
    error_message = "The WIF pilot must remain restricted to BasedHardware/omi."
  }
}

variable "workload_identity_pool_id" {
  type        = string
  description = "Dedicated development WIF pool name."
  default     = "omi-opentofu-9842-dev"

  validation {
    condition     = var.workload_identity_pool_id == "omi-opentofu-9842-dev"
    error_message = "The pilot must use its dedicated development WIF pool."
  }
}

variable "plan_service_account_id" {
  type        = string
  description = "Dedicated development-only read-only plan service account name."
  default     = "omi-tofu-plan-dev-9842"

  validation {
    condition     = var.plan_service_account_id == "omi-tofu-plan-dev-9842"
    error_message = "The pilot must use its dedicated development plan service account."
  }
}
