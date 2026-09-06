terraform {
  required_version = ">= 1.12.0, < 2.0.0"
  backend "gcs" {
    bucket = "based-hardware-dev-omi-platform-tfstate"
    prefix = "omi-platform/dev/foundation"
  }
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

locals {
  project = "based-hardware-dev"
  budget  = jsondecode(file("${path.module}/connection-budget.json"))
  labels = {
    environment = "dev"
    application = "omi-platform"
    managed_by  = "opentofu"
  }
  secrets = toset([
    "omi-platform-dev-database-url",
    "omi-platform-dev-codec-key",
    "omi-platform-dev-cursor-key"
  ])
}

resource "google_project_service" "required" {
  for_each = toset([
    "sqladmin.googleapis.com",
    "secretmanager.googleapis.com",
    "iam.googleapis.com"
  ])
  project            = local.project
  service            = each.key
  disable_on_destroy = false
}

resource "google_service_account" "runtime" {
  project      = local.project
  account_id   = "omi-platform-dev-runtime"
  display_name = "Omi platform development runtime"
  depends_on   = [google_project_service.required]
}

resource "google_project_iam_member" "sql_client" {
  project = local.project
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.runtime.email}"
}

resource "google_sql_database_instance" "platform" {
  project             = local.project
  name                = "omi-platform-dev-pg18"
  region              = "us-central1"
  database_version    = "POSTGRES_18"
  deletion_protection = true
  depends_on          = [google_project_service.required]

  settings {
    edition                     = "ENTERPRISE"
    tier                        = "db-custom-1-3840"
    availability_type           = "ZONAL"
    disk_type                   = "PD_SSD"
    disk_size                   = 10
    disk_autoresize             = true
    disk_autoresize_limit       = 100
    deletion_protection_enabled = true
    connector_enforcement       = "REQUIRED"
    user_labels                 = local.labels
    ip_configuration {
      ipv4_enabled = true
      ssl_mode     = "ENCRYPTED_ONLY"
    }
    database_flags {
      name  = "max_connections"
      value = tostring(local.budget.database_max_connections)
    }
    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true
      start_time                     = "04:00"
      transaction_log_retention_days = 7
      backup_retention_settings {
        retained_backups = 7
        retention_unit   = "COUNT"
      }
    }
    maintenance_window {
      day          = 7
      hour         = 5
      update_track = "stable"
    }
  }
  lifecycle {
    prevent_destroy = true
    precondition {
      condition     = local.budget.concurrent_revisions * local.budget.revision_instance_cap * local.budget.api_pool_max + local.budget.job_connections + local.budget.migration_reserve + local.budget.operator_reserve <= local.budget.approved_connections
      error_message = "All concurrent release units plus migration and operator reserves must fit the connection budget."
    }
    precondition {
      condition     = local.budget.approved_connections < local.budget.database_max_connections - local.budget.provider_reserved_connections
      error_message = "The approved connection budget must remain below database capacity after provider reserves."
    }
  }
}

resource "google_sql_database" "platform" {
  project  = local.project
  name     = "omi_platform"
  instance = google_sql_database_instance.platform.name
  lifecycle {
    prevent_destroy = true
  }
}

resource "google_secret_manager_secret" "runtime" {
  for_each  = local.secrets
  project   = local.project
  secret_id = each.key
  labels    = local.labels
  replication {
    user_managed {
      replicas {
        location = "us-central1"
      }
    }
  }
  depends_on = [google_project_service.required]
  lifecycle {
    prevent_destroy = true
  }
}

resource "google_secret_manager_secret_iam_member" "runtime_access" {
  for_each  = google_secret_manager_secret.runtime
  project   = local.project
  secret_id = each.value.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.runtime.email}"
}

output "runtime_service_account" {
  value = google_service_account.runtime.email
}

output "cloud_sql_connection_name" {
  value = google_sql_database_instance.platform.connection_name
}

output "database_name" {
  value = google_sql_database.platform.name
}

output "secret_containers" {
  value = { for name, secret in google_secret_manager_secret.runtime : name => secret.id }
}

output "connection_budget" {
  value = local.budget
}

resource "google_project_iam_custom_role" "auth_verifier" {
  project     = local.project
  role_id     = "omiPlatformDevAuthVerifier"
  title       = "Omi development token revocation verification"
  permissions = ["firebaseauth.users.get"]
  depends_on  = [google_project_service.required]
}

resource "google_project_iam_member" "auth_verifier" {
  project = local.project
  role    = google_project_iam_custom_role.auth_verifier.name
  member  = "serviceAccount:${google_service_account.runtime.email}"
}

resource "google_secret_manager_secret_iam_member" "gateway_access" {
  project   = local.project
  secret_id = "jit-qa-gateway-token"
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.runtime.email}"
}
