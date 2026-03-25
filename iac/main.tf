terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

# Configura tu proyecto (Cambia el ID por el tuyo)
variable "project_id" {
  description = "ID del proyecto de GCP"
  type        = string
  default     = "tysa-491218" # <--- ¡CÁMBIALO!
}

variable "region" {
  description = "Región de despliegue"
  type        = string
  default     = "us-central1"
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# 1. Habilitar APIs necesarias
resource "google_project_service" "apis" {
  for_each = toset([
    "iam.googleapis.com",
    "artifactregistry.googleapis.com",
    "run.googleapis.com",
    "cloudscheduler.googleapis.com",
    "cloudresourcemanager.googleapis.com"
  ])
  service            = each.key
  disable_on_destroy = false
}

# 2. Artifact Registry (Donde GitHub subirá el Docker)
resource "google_artifact_registry_repository" "repo" {
  location      = var.region
  repository_id = "cloud-run-source-deploy"
  description   = "Repositorio Docker para GoCanvas Sync"
  format        = "DOCKER"
  depends_on    = [google_project_service.apis]
}

# 3. Service Account para Cloud Run (El que entrará a Google Sheets)
resource "google_service_account" "cloud_run_sa" {
  account_id   = "gocanvas-sync-sa"
  display_name = "Cloud Run SA (Acceso a Sheets)"
  depends_on   = [google_project_service.apis]
}

# 4. Service Account para GitHub Actions (El que despliega la app)
resource "google_service_account" "github_sa" {
  account_id   = "github-actions-deploy-sa"
  display_name = "GitHub Actions CI/CD SA"
  depends_on   = [google_project_service.apis]
}

# 5. Permisos para que GitHub Actions pueda desplegar
resource "google_project_iam_member" "github_ar_writer" {
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${google_service_account.github_sa.email}"
}

resource "google_project_iam_member" "github_run_admin" {
  project = var.project_id
  role    = "roles/run.admin"
  member  = "serviceAccount:${google_service_account.github_sa.email}"
}

# Permite a GitHub asignar el SA de Cloud Run al Job
resource "google_service_account_iam_member" "github_act_as_cloud_run" {
  service_account_id = google_service_account.cloud_run_sa.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.github_sa.email}"
}

# Permite al Scheduler invocar a Cloud Run
resource "google_project_iam_member" "scheduler_invoker" {
  project = var.project_id
  role    = "roles/run.invoker"
  member  = "serviceAccount:${google_service_account.cloud_run_sa.email}"
}

# 6. Crear el Cloud Run Job inicial (Con imagen Dummy)
resource "google_cloud_run_v2_job" "sync_job" {
  name     = "sync-gocanvas-job"
  location = var.region

  template {
    template {
      service_account = google_service_account.cloud_run_sa.email
      containers {
        # Imagen de prueba solo para poder crear el recurso
        image = "us-docker.pkg.dev/cloudrun/container/hello" 
      }
    }
  }
  depends_on = [google_project_service.apis]
}

# 7. Cloud Scheduler (El gatillo diario)
resource "google_cloud_scheduler_job" "daily_trigger" {
  name             = "disparador-diario-gocanvas"
  description      = "Ejecuta el Sync de GoCanvas todos los días a las 6 PM"
  schedule         = "0 18 * * *" # Formato Cron: 6:00 PM todos los días
  time_zone        = "America/Bogota"

  http_target {
    http_method = "POST"
    # URL de la API v2 de Cloud Run para ejecutar Jobs
    uri = "https://${var.region}-run.googleapis.com/v2/projects/${var.project_id}/locations/${var.region}/jobs/sync-gocanvas-job:run"
    
    oauth_token {
      service_account_email = google_service_account.cloud_run_sa.email
    }
  }
  depends_on = [google_cloud_run_v2_job.sync_job]
}