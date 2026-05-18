# ══════════════════════════════════════════════════
# Terraform — GCP Cloud Run Deployment
# Deploys the LLM Observability Pipeline as a
# serverless container on Google Cloud Run.
# ══════════════════════════════════════════════════

terraform {
  required_version = ">= 1.5"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.gcp_project
  region  = var.region
}

# ── Artifact Registry ────────────────────────────────────────────────────────
resource "google_artifact_registry_repository" "llm_obs" {
  location      = var.region
  repository_id = "llm-observability"
  format        = "DOCKER"
  description   = "LLM Observability Pipeline container images"
}

# ── Cloud Run Service ────────────────────────────────────────────────────────
resource "google_cloud_run_v2_service" "pipeline" {
  name     = "llm-observability-pipeline"
  location = var.region

  template {
    service_account = google_service_account.pipeline_sa.email

    containers {
      image = "${var.region}-docker.pkg.dev/${var.gcp_project}/llm-observability/pipeline:${var.image_tag}"

      env {
        name = "ARIZE_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.arize_key.secret_id
            version = "latest"
          }
        }
      }

      env {
        name = "ARIZE_SPACE_ID"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.arize_space.secret_id
            version = "latest"
          }
        }
      }

      env {
        name  = "GCP_PROJECT_ID"
        value = var.gcp_project
      }

      resources {
        limits = {
          memory = "1Gi"
          cpu    = "1"
        }
      }
    }

    scaling {
      min_instance_count = 0
      max_instance_count = 3
    }
  }

  depends_on = [
    google_secret_manager_secret_iam_member.pipeline_secret_access
  ]
}

# ── Service Account ──────────────────────────────────────────────────────────
resource "google_service_account" "pipeline_sa" {
  account_id   = "llm-obs-pipeline-sa"
  display_name = "LLM Observability Pipeline Service Account"
}

resource "google_project_iam_member" "vertex_ai_access" {
  project = var.gcp_project
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.pipeline_sa.email}"
}

resource "google_project_iam_member" "storage_access" {
  project = var.gcp_project
  role    = "roles/storage.objectCreator"
  member  = "serviceAccount:${google_service_account.pipeline_sa.email}"
}

# ── Secret Manager ───────────────────────────────────────────────────────────
resource "google_secret_manager_secret" "arize_key" {
  secret_id = "arize-api-key"
  replication { auto {} }
}

resource "google_secret_manager_secret" "arize_space" {
  secret_id = "arize-space-id"
  replication { auto {} }
}

resource "google_secret_manager_secret_iam_member" "pipeline_secret_access" {
  for_each  = toset([google_secret_manager_secret.arize_key.name, google_secret_manager_secret.arize_space.name])
  secret_id = each.value
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.pipeline_sa.email}"
}

# ── Cloud Scheduler (run pipeline on schedule) ───────────────────────────────
resource "google_cloud_scheduler_job" "pipeline_trigger" {
  name      = "llm-obs-pipeline-trigger"
  schedule  = "*/5 * * * *"   # Every 5 minutes
  time_zone = "UTC"

  http_target {
    http_method = "POST"
    uri         = "${google_cloud_run_v2_service.pipeline.uri}/run"

    oidc_token {
      service_account_email = google_service_account.pipeline_sa.email
    }
  }
}
