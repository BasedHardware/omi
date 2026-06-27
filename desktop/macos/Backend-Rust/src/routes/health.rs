// Health check routes

use axum::{extract::State, routing::get, Json, Router};
use serde::Serialize;

use crate::AppState;

#[derive(Serialize)]
pub struct HealthResponse {
    pub status: String,
    pub service: String,
    pub version: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub release_tag: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub release_sha: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub release_channel: Option<String>,
}

/// Health check endpoint for Kubernetes probes
async fn health_check(State(state): State<AppState>) -> Json<HealthResponse> {
    Json(HealthResponse {
        status: "healthy".to_string(),
        service: "omi-desktop-backend".to_string(),
        version: env!("CARGO_PKG_VERSION").to_string(),
        release_tag: state.config.desktop_release_tag.clone(),
        release_sha: state.config.desktop_release_sha.clone(),
        release_channel: state.config.desktop_release_channel.clone(),
    })
}

pub fn health_routes() -> Router<AppState> {
    Router::new()
        .route("/health", get(health_check))
        .route("/", get(health_check))
}
