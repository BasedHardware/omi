// Health check routes

use axum::{routing::get, Json, Router};
use serde::Serialize;

use crate::AppState;

#[derive(Serialize)]
pub struct HealthResponse {
    pub status: String,
    pub service: String,
    pub version: String,
}

/// Health check endpoint for Kubernetes probes
async fn health_check() -> Json<HealthResponse> {
    Json(HealthResponse {
        status: "healthy".to_string(),
        service: "omi-desktop-backend".to_string(),
        version: env!("CARGO_PKG_VERSION").to_string(),
    })
}

pub fn health_routes() -> Router<AppState> {
    Router::new()
        .route("/health", get(health_check))
        .route("/", get(health_check))
}
