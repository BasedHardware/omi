use axum::{extract::State, Json};
use serde::Serialize;

use crate::AppState;

#[derive(Serialize)]
pub struct HealthResponse {
    service: &'static str,
    mode: &'static str,
    version: &'static str,
    bind_addr: String,
    data_dir: String,
}

pub async fn health(State(state): State<AppState>) -> Json<HealthResponse> {
    Json(HealthResponse {
        service: "omi-local-backend",
        mode: "local",
        version: env!("CARGO_PKG_VERSION"),
        bind_addr: state.config.bind_addr.to_string(),
        data_dir: state.config.data_dir.display().to_string(),
    })
}
