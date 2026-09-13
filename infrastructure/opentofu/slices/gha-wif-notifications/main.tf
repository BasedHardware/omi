terraform {
  required_version = ">= 1.12.4, < 2.0.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }

  # Operator supplies reviewed development-only GCS backend.hcl.
  backend "gcs" {}
}

provider "google" {
  project = var.project_id
}

resource "google_service_account" "deploy" {
  account_id   = var.deploy_service_account_id
  display_name = "Omi GHA notif job deploy"
  description  = "GitHub WIF deployer for notifications-job on based-hardware-dev only."
}

resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = var.workload_identity_pool_id
  display_name              = "Omi GHA notif WIF pool"
  description               = "GitHub OIDC pool for notifications-job development WIF."
  disabled                  = false
}

resource "google_iam_workload_identity_pool_provider" "github" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github"
  display_name                       = "Omi GHA notif GitHub OIDC"
  description                        = "Restricts notifications-job development WIF to Omi main + development env."

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

resource "google_service_account_iam_member" "github_deploy_impersonation" {
  service_account_id = google_service_account.deploy.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository_id/${var.github_repository_id}"
}

resource "google_artifact_registry_repository_iam_member" "gcr_writer" {
  project    = var.project_id
  location   = "us"
  repository = "gcr.io"
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${google_service_account.deploy.email}"
}

resource "google_cloud_run_v2_job_iam_member" "notifications_job_developer" {
  project  = var.project_id
  location = "us-central1"
  name     = "notifications-job"
  role     = "roles/run.developer"
  member   = "serviceAccount:${google_service_account.deploy.email}"
}

resource "google_service_account_iam_member" "notifications_job_runtime_act_as" {
  service_account_id = "projects/${var.project_id}/serviceAccounts/${var.runtime_service_account_email}"
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.deploy.email}"
}

# kubectl get deployment for the gateway serving gate (clusterViewer is credentials only).
resource "google_project_iam_member" "gke_viewer" {
  project = var.project_id
  role    = "roles/container.viewer"
  member  = "serviceAccount:${google_service_account.deploy.email}"
}

# Gateway serving gate: addresses.describe + forwarding-rules.list
resource "google_project_iam_member" "compute_network_viewer" {
  project = var.project_id
  role    = "roles/compute.networkViewer"
  member  = "serviceAccount:${google_service_account.deploy.email}"
}

# Throwaway llm-gateway-vpc-probe-* jobs are created at deploy time.
resource "google_project_iam_member" "run_developer" {
  project = var.project_id
  role    = "roles/run.developer"
  member  = "serviceAccount:${google_service_account.deploy.email}"
}

# Probe job --network/--subnet attach.
resource "google_project_iam_member" "compute_network_user" {
  project = var.project_id
  role    = "roles/compute.networkUser"
  member  = "serviceAccount:${google_service_account.deploy.email}"
}

# Probe --set-secrets=OMI_LLM_GATEWAY_SERVICE_TOKEN
resource "google_secret_manager_secret_iam_member" "gateway_token" {
  project   = var.project_id
  secret_id = "OMI_LLM_GATEWAY_SERVICE_TOKEN"
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.deploy.email}"
}
