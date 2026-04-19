// Client configuration routes
// Serves API keys to authenticated desktop clients so keys are not bundled in the app binary.
//
// Deepgram, Gemini, and ElevenLabs keys are NO LONGER served here — they are proxied
// server-side via /v1/proxy/deepgram/*, /v1/proxy/gemini/*, and /v1/tts/synthesize
// (see proxy.rs, tts.rs; issues #5861, #6622).

use axum::{extract::State, routing::get, Json, Router};
use serde::Serialize;

use crate::auth::AuthUser;
use crate::AppState;

#[derive(Serialize)]
struct ApiKeysResponse {
    #[serde(skip_serializing_if = "Option::is_none")]
    anthropic_api_key: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    firebase_api_key: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    google_calendar_api_key: Option<String>,
}

/// GET /v1/config/api-keys — return API keys for the authenticated user
/// NOTE: Deepgram, Gemini keys removed — proxied server-side (issue #5861)
/// NOTE: ElevenLabs key removed — proxied via /v1/tts/synthesize (issue #6622, #6827)
async fn get_api_keys(State(state): State<AppState>, _user: AuthUser) -> Json<ApiKeysResponse> {
    Json(ApiKeysResponse {
        anthropic_api_key: state.config.anthropic_api_key.clone(),
        firebase_api_key: state.config.firebase_api_key.clone(),
        google_calendar_api_key: state.config.google_calendar_api_key.clone(),
    })
}

pub fn config_routes() -> Router<AppState> {
    Router::new().route("/v1/config/api-keys", get(get_api_keys))
}
