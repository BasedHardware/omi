terraform {
  required_version = ">= 1.12.4, < 2.0.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }

  # The operator supplies a reviewed development-only GCS backend config when
  # bootstrapping this pilot. CI always removes this block in its temporary copy.
  backend "gcs" {}
}

provider "google" {
  project = var.project_id
}

resource "google_service_account" "plan" {
  account_id   = var.plan_service_account_id
  display_name = "Omi OpenTofu development plan pilot"
  description  = "Read-only GitHub WIF identity for OpenTofu development pilot #9842."
}

resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = var.workload_identity_pool_id
  display_name              = "Omi OpenTofu dev GitHub pool"
  description               = "GitHub OIDC pool for Omi OpenTofu development pilot #9842."
  disabled                  = false
}

resource "google_iam_workload_identity_pool_provider" "github" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github"
  display_name                       = "Omi GitHub dev plan OIDC"
  description                        = "Restricts the development plan identity to Omi's immutable GitHub identity, workflow, environment, and main."

  attribute_mapping = {
    "google.subject"                = "assertion.sub"
    "attribute.repository_id"       = "assertion.repository_id"
    "attribute.repository_owner_id" = "assertion.repository_owner_id"
    "attribute.workflow_ref"        = "assertion.workflow_ref"
    "attribute.environment"         = "assertion.environment"
  }

  attribute_condition = "assertion.repository_id == '${var.github_repository_id}' && assertion.repository_owner_id == '${var.github_repository_owner_id}' && assertion.ref == 'refs/heads/main' && assertion.workflow_ref == '${var.github_workflow_ref}' && assertion.environment == 'development'"

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account_iam_member" "github_plan_impersonation" {
  service_account_id = google_service_account.plan.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository_id/${var.github_repository_id}"
}

resource "google_project_iam_member" "plan_project_browser" {
  project = var.project_id
  role    = "roles/browser"
  member  = "serviceAccount:${google_service_account.plan.email}"
}
