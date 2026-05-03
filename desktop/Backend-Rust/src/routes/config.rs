// Client configuration routes
// Serves non-secret config to authenticated desktop clients so keys are not bundled in the app binary.
//
// Keys NO LONGER served here (proxied server-side):
//   - Gemini: /v1/proxy/gemini/* (issue #5861); Deepgram proxy removed (#7137)
//   - ElevenLabs: /v1/tts/synthesize (issue #6622)
//   - Anthropic: kept server-side for /v2/chat/completions proxy only (issue #6594)
//
// Legacy compat (explicit manager decision for backward compat):
// DESKTOP_LEGACY_ANTHROPIC_KEY is served as anthropic_api_key for old app
// versions (pre-#6594) that read the key client-side. New app versions proxy
// all Anthropic traffic server-side and ignore this field.
// SECURITY NOTE: This is a deliberate tradeoff — old clients need the key to
// function until the next major release forces an update. The env var is
// separate from ANTHROPIC_API_KEY so operators can rotate independently.
// TODO: Remove after major release when all clients use server-side proxy.

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
    /// Legacy: served from DESKTOP_LEGACY_ANTHROPIC_KEY for old clients. Deprecated.
    #[serde(skip_serializing_if = "Option::is_none")]
    anthropic_api_key: Option<String>,
}

/// GET /v1/config/api-keys — return non-secret config for the authenticated user
/// NOTE: Anthropic key removed — proxied server-side via /v2/chat/completions (issue #6594)
/// NOTE: Gemini keys proxied server-side (issue #5861); Deepgram proxy removed (#7137)
/// NOTE: ElevenLabs key removed — proxied via /v1/tts/synthesize (issue #6622, #6827)
async fn get_api_keys(State(state): State<AppState>, _user: AuthUser) -> Json<ApiKeysResponse> {
    Json(ApiKeysResponse {
        firebase_api_key: state.config.firebase_api_key.clone(),
        google_calendar_api_key: state.config.google_calendar_api_key.clone(),
        anthropic_api_key: state.config.desktop_legacy_anthropic_key.clone(),
    })
}

pub fn config_routes() -> Router<AppState> {
    Router::new().route("/v1/config/api-keys", get(get_api_keys))
}
