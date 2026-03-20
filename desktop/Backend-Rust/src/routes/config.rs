// Client configuration routes
// Serves API keys to authenticated desktop clients so keys are not bundled in the app binary.
//
// NOTE: The current desktop app is slopped on security — API keys were hardcoded in the
// Swift source and env files. This endpoint exists to move secrets server-side. Will remove
// this endpoint once all client-side key slop is cleaned up properly. — CTO

use axum::{extract::State, routing::get, Json, Router};
use serde::Serialize;

use crate::auth::AuthUser;
use crate::AppState;

#[derive(Serialize)]
struct ApiKeysResponse {
    #[serde(skip_serializing_if = "Option::is_none")]
    deepgram_api_key: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    gemini_api_key: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    anthropic_api_key: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    firebase_api_key: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    google_calendar_api_key: Option<String>,
}

/// GET /v1/config/api-keys — return API keys for the authenticated user
async fn get_api_keys(State(state): State<AppState>, _user: AuthUser) -> Json<ApiKeysResponse> {
    Json(ApiKeysResponse {
        deepgram_api_key: state.config.deepgram_api_key.clone(),
        gemini_api_key: state.config.gemini_api_key.clone(),
        anthropic_api_key: state.config.anthropic_api_key.clone(),
        firebase_api_key: state.config.firebase_api_key.clone(),
        google_calendar_api_key: state.config.google_calendar_api_key.clone(),
    })
}

pub fn config_routes() -> Router<AppState> {
    Router::new().route("/v1/config/api-keys", get(get_api_keys))
}
