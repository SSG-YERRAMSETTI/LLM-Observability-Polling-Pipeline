output "service_url" {
  description = "Cloud Run service URL"
  value       = google_cloud_run_v2_service.pipeline.uri
}

output "artifact_registry_url" {
  description = "Artifact Registry repository URL"
  value       = "${var.region}-docker.pkg.dev/${var.gcp_project}/llm-observability"
}
