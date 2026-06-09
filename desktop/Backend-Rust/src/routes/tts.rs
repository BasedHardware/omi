// OpenAI TTS proxy route.
// Clients authenticate with Firebase and never need a bundled OpenAI key.

use axum::{
    body::Body,
    extract::State,
    http::{HeaderMap, StatusCode},
    response::{IntoResponse, Response},
    routing::post,
    Json, Router,
};
use serde::{Deserialize, Serialize};
use std::time::Duration;

use crate::auth::{AuthUser, PaywalledAuthUser};
use crate::byok;
use crate::AppState;

const OPENAI_TTS_MODEL_ID: &str = "gpt-4o-mini-tts";
const OPENAI_SPEECH_URL: &str = "https://api.openai.com/v1/audio/speech";
const MAX_TTS_CHARS: usize = 4096;

/// Max attempts for the OpenAI TTS request (1 try + 2 retries on transient errors).
const TTS_MAX_ATTEMPTS: usize = 3;

/// Transient upstream statuses worth retrying (overload/availability). Caller/auth
/// errors (400/401/etc.) are returned immediately.
fn is_transient_tts_status(status: u16) -> bool {
    matches!(status, 408 | 425 | 429 | 500 | 502 | 503 | 504 | 529)
}
const SERVER_TTS_BURST_PER_MINUTE: i64 = 20;
const SERVER_TTS_DAILY_CHARS: i64 = 50_000;
const TTS_BURST_WINDOW_SECS: u64 = 60;

#[derive(Debug, Deserialize)]
struct TtsSynthesizeRequest {
    text: String,
    voice_id: String,
    #[serde(default)]
    instructions: Option<String>,
}

#[derive(Serialize)]
struct OpenAISpeechRequest<'a> {
    model: &'a str,
    input: &'a str,
    voice: &'a str,
    #[serde(skip_serializing_if = "Option::is_none")]
    instructions: Option<&'a str>,
    response_format: &'a str,
}

enum TtsProxyError {
    BadRequest(&'static str),
    MissingApiKey,
    RateLimited(&'static str),
    RateLimitUnavailable,
    Upstream(StatusCode, String),
    BadGateway(String),
}

impl IntoResponse for TtsProxyError {
    fn into_response(self) -> Response {
        let (status, message) = match self {
            TtsProxyError::BadRequest(message) => (StatusCode::BAD_REQUEST, message.to_string()),
            TtsProxyError::MissingApiKey => (
                StatusCode::SERVICE_UNAVAILABLE,
                "OpenAI TTS is not configured".to_string(),
            ),
            TtsProxyError::RateLimited(message) => {
                (StatusCode::TOO_MANY_REQUESTS, message.to_string())
            }
            TtsProxyError::RateLimitUnavailable => (
                StatusCode::SERVICE_UNAVAILABLE,
                "TTS rate limiting is unavailable".to_string(),
            ),
            TtsProxyError::Upstream(status, body) => {
                let safe_body = if body.chars().count() > 500 {
                    format!("{}...", body.chars().take(500).collect::<String>())
                } else {
                    body
                };
                (status, format!("OpenAI TTS request failed: {}", safe_body))
            }
            TtsProxyError::BadGateway(message) => (StatusCode::BAD_GATEWAY, message),
        };

        (
            status,
            Json(serde_json::json!({
                "error": message,
            })),
        )
            .into_response()
    }
}

async fn tts_synthesize(
    State(state): State<AppState>,
    user: PaywalledAuthUser,
    headers: HeaderMap,
    Json(request): Json<TtsSynthesizeRequest>,
) -> Result<Response, TtsProxyError> {
    let byok_stripped = user.byok_stripped;
    let user: AuthUser = user.into();
    let text = request.text.trim();
    if text.is_empty() {
        return Err(TtsProxyError::BadRequest("text is required"));
    }
    let char_count = text.chars().count();
    if char_count > MAX_TTS_CHARS {
        return Err(TtsProxyError::BadRequest("text is too long"));
    }

    let voice_id = request.voice_id.trim();
    if !is_allowed_openai_voice(voice_id) {
        return Err(TtsProxyError::BadRequest("voice_id is not supported"));
    }

    let instructions = request
        .instructions
        .as_deref()
        .map(str::trim)
        .filter(|value| !value.is_empty());

    let (api_key, uses_server_key) = openai_key_for_request(&state, &headers, byok_stripped)?;
    if uses_server_key {
        check_server_tts_rate_limit(&state, &user.uid, char_count).await?;
    }

    let payload = OpenAISpeechRequest {
        model: OPENAI_TTS_MODEL_ID,
        input: text,
        voice: voice_id,
        instructions,
        response_format: "mp3",
    };

    let client = reqwest::Client::builder()
        .connect_timeout(Duration::from_secs(10))
        .timeout(Duration::from_secs(30))
        .build()
        .unwrap_or_default();

    // Retry the request on transient OpenAI failures (network/429/5xx) so a brief blip
    // doesn't drop the voice reply. The client additionally falls back to the macOS
    // system voice if this ultimately fails.
    let mut upstream = None;
    for attempt in 1..=TTS_MAX_ATTEMPTS {
        match client
            .post(OPENAI_SPEECH_URL)
            .bearer_auth(api_key)
            .json(&payload)
            .send()
            .await
        {
            Ok(resp) => {
                let s = resp.status().as_u16();
                if is_transient_tts_status(s) && attempt < TTS_MAX_ATTEMPTS {
                    tracing::warn!(
                        "tts_synthesize: OpenAI {} (attempt {}/{}), retrying",
                        s,
                        attempt,
                        TTS_MAX_ATTEMPTS
                    );
                    tokio::time::sleep(Duration::from_millis(300 * attempt as u64)).await;
                    continue;
                }
                upstream = Some(resp);
                break;
            }
            Err(error) => {
                if attempt < TTS_MAX_ATTEMPTS {
                    tracing::warn!(
                        "tts_synthesize: OpenAI request error (attempt {}/{}): {}",
                        attempt,
                        TTS_MAX_ATTEMPTS,
                        error
                    );
                    tokio::time::sleep(Duration::from_millis(300 * attempt as u64)).await;
                    continue;
                }
                return Err(TtsProxyError::BadGateway(error.to_string()));
            }
        }
    }
    let upstream = upstream.ok_or_else(|| TtsProxyError::BadGateway("tts: no upstream response".to_string()))?;

    let status =
        StatusCode::from_u16(upstream.status().as_u16()).unwrap_or(StatusCode::BAD_GATEWAY);
    let bytes = upstream
        .bytes()
        .await
        .map_err(|error| TtsProxyError::BadGateway(error.to_string()))?;

    if !status.is_success() {
        let body = String::from_utf8_lossy(&bytes).to_string();
        tracing::warn!(
            "tts_synthesize: OpenAI returned {} for uid={}: {}",
            status,
            user.uid,
            body
        );
        return Err(TtsProxyError::Upstream(status, body));
    }

    Ok(Response::builder()
        .status(StatusCode::OK)
        .header("content-type", "audio/mpeg")
        .body(Body::from(bytes))
        .unwrap())
}

fn openai_key_for_request<'a>(
    state: &'a AppState,
    headers: &'a HeaderMap,
    byok_stripped: bool,
) -> Result<(&'a str, bool), TtsProxyError> {
    if let Some(value) = byok::get_byok_key_if_active(headers, byok::HEADER_OPENAI, byok_stripped) {
        return Ok((value, false));
    }

    let key = state
        .config
        .openai_api_key
        .as_deref()
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .ok_or(TtsProxyError::MissingApiKey)?;

    Ok((key, true))
}

async fn check_server_tts_rate_limit(
    state: &AppState,
    uid: &str,
    char_count: usize,
) -> Result<(), TtsProxyError> {
    let redis = state.redis.as_ref().ok_or_else(|| {
        tracing::error!(
            "tts_synthesize: Redis is not configured; refusing unmetered server-key TTS"
        );
        TtsProxyError::RateLimitUnavailable
    })?;

    let (daily_chars, burst_count) = redis
        .check_tts_rate_limit(uid, char_count, TTS_BURST_WINDOW_SECS)
        .await
        .map_err(|error| {
            tracing::error!(
                "tts_synthesize: Redis rate-limit error for uid={}: {}",
                uid,
                error
            );
            TtsProxyError::RateLimitUnavailable
        })?;

    if burst_count > SERVER_TTS_BURST_PER_MINUTE {
        tracing::warn!("tts_synthesize: burst rate limit exceeded uid={}", uid);
        return Err(TtsProxyError::RateLimited("TTS burst rate limit exceeded"));
    }
    if daily_chars > SERVER_TTS_DAILY_CHARS {
        tracing::warn!("tts_synthesize: daily character limit exceeded uid={}", uid);
        return Err(TtsProxyError::RateLimited(
            "TTS daily character limit exceeded",
        ));
    }

    Ok(())
}

fn is_allowed_openai_voice(voice_id: &str) -> bool {
    matches!(
        voice_id,
        "alloy"
            | "ash"
            | "ballad"
            | "coral"
            | "echo"
            | "fable"
            | "nova"
            | "onyx"
            | "sage"
            | "shimmer"
            | "verse"
            | "marin"
            | "cedar"
    )
}

pub fn tts_routes() -> Router<AppState> {
    Router::new().route("/v1/tts/synthesize", post(tts_synthesize))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn allows_supported_openai_voices() {
        for voice in ["onyx", "shimmer", "coral", "nova", "marin", "cedar"] {
            assert!(is_allowed_openai_voice(voice));
        }
    }

    #[test]
    fn rejects_unsupported_voice_ids() {
        for voice in ["", "BAMYoBHLZM7lJgJAmFz0", "onyx/", "OpenAI"] {
            assert!(!is_allowed_openai_voice(voice));
        }
    }

    #[test]
    fn request_character_limit_matches_openai_limit() {
        assert_eq!(MAX_TTS_CHARS, 4096);
    }
}
