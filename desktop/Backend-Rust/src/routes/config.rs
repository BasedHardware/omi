// Client configuration routes
// Serves non-secret config to authenticated desktop clients so keys are not bundled in the app binary.
//
// Keys NO LONGER served here (proxied server-side):
//   - Deepgram, Gemini: /v1/proxy/deepgram/*, /v1/proxy/gemini/* (issue #5861)
//   - ElevenLabs: /v1/tts/synthesize (issue #6622)
//   - Anthropic: /v2/chat/completions (issue #6594, #6928)

use axum::{extract::State, routing::get, Json, Router};
use serde::Serialize;

use crate::auth::AuthUser;
use crate::AppState;

#[derive(Serialize)]
struct ApiKeysResponse {
    #[serde(skip_serializing_if = "Option::is_none")]
    firebase_api_key: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    google_calendar_api_key: Option<String>,
}

/// GET /v1/config/api-keys — return non-secret config for the authenticated user
/// NOTE: Anthropic key removed (issue #6928) - proxied server-side via /v2/chat/completions
/// NOTE: Deepgram, Gemini keys removed - proxied server-side (issue #5861)
/// NOTE: ElevenLabs key removed - proxied via /v1/tts/synthesize (issue #6622, #6827)
async fn get_api_keys(State(state): State<AppState>, _user: AuthUser) -> Json<ApiKeysResponse> {
    Json(ApiKeysResponse {
        firebase_api_key: state.config.firebase_api_key.clone(),
        google_calendar_api_key: state.config.google_calendar_api_key.clone(),
    })
}

pub fn config_routes() -> Router<AppState> {
    Router::new().route("/v1/config/api-keys", get(get_api_keys))
}