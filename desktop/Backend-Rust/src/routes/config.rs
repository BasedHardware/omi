// Client configuration routes
// Serves API keys to authenticated desktop clients so keys are not bundled in the app binary.
//
// Deepgram and Gemini keys are NO LONGER served here — they are proxied server-side
// via /v1/proxy/deepgram/* and /v1/proxy/gemini/* (see proxy.rs, issue #5861).
//
// ElevenLabs key: new clients use the TTS proxy at /v1/tts/synthesize (issue #6622),
// but the key is still served here for backward compatibility with older app versions.
// Set DISABLE_ELEVENLABS_KEY_RESPONSE=true to stop serving it once all clients have updated.

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
    #[serde(skip_serializing_if = "Option::is_none")]
    elevenlabs_api_key: Option<String>,
}

/// GET /v1/config/api-keys — return API keys for the authenticated user
/// NOTE: Deepgram, Gemini keys removed — proxied server-side (issue #5861)
/// NOTE: ElevenLabs key gated by DISABLE_ELEVENLABS_KEY_RESPONSE (issue #6622)
async fn get_api_keys(State(state): State<AppState>, _user: AuthUser) -> Json<ApiKeysResponse> {
    let elevenlabs_key = if state.config.disable_elevenlabs_key_response {
        None
    } else {
        state.config.elevenlabs_api_key.clone()
    };

    Json(ApiKeysResponse {
        anthropic_api_key: state.config.anthropic_api_key.clone(),
        firebase_api_key: state.config.firebase_api_key.clone(),
        google_calendar_api_key: state.config.google_calendar_api_key.clone(),
        elevenlabs_api_key: elevenlabs_key,
    })
}

pub fn config_routes() -> Router<AppState> {
    Router::new().route("/v1/config/api-keys", get(get_api_keys))
}
