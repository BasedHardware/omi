// TTS proxy route — server-side text-to-speech with pluggable providers.
//
// Providers:
//   - "elevenlabs" (default) — premium quality, ~$99-330 per 1M chars
//   - "openai"               — ~6.6x cheaper at $15/1M chars, MP3 output,
//                              voices: alloy/ash/ballad/coral/echo/fable/nova/
//                              onyx/sage/shimmer/verse
//
// Selected via the `provider` field in the request body; default remains
// "elevenlabs" for backward compatibility.
//
// Keys stay on the backend; desktop client authenticates via Firebase token only.
//
// Per-user rate limits (Redis-backed):
//   - 50 requests per rolling 60-second window → 429
//   - 10,000 characters per calendar day → 429
//
// Issue #6622: Remove client-side ElevenLabs API key exposure.

use axum::{
    extract::State,
    http::StatusCode,
    response::{IntoResponse, Response},
    routing::post,
    Json, Router,
};
use serde::{Deserialize, Serialize};

use crate::auth::AuthUser;
use crate::AppState;

/// Per-user burst limit: max requests per rolling 60-second window.
const TTS_BURST_PER_MINUTE: i64 = 50;

/// Per-user daily character limit.
const TTS_DAILY_CHAR_LIMIT: i64 = 10_000;

/// Rolling burst window in seconds.
const TTS_BURST_WINDOW_SECS: u64 = 60;

/// Single-request text cap for ElevenLabs synthesis.
const TTS_REQUEST_CHAR_LIMIT: i64 = 5_000;

#[derive(Deserialize)]
struct TtsSynthesizeRequest {
    text: String,
    #[serde(default = "default_voice_id")]
    voice_id: String,
    #[serde(default = "default_model_id")]
    model_id: String,
    #[serde(default = "default_output_format")]
    output_format: String,
    voice_settings: Option<VoiceSettings>,
    /// Provider selector. Defaults to "elevenlabs" when omitted (backward compat).
    /// Valid values: "elevenlabs", "openai".
    #[serde(default)]
    provider: Option<String>,
}

/// OpenAI TTS voice names accepted by `/v1/audio/speech`.
const OPENAI_VOICES: &[&str] = &[
    "alloy", "ash", "ballad", "coral", "echo", "fable", "nova", "onyx", "sage", "shimmer", "verse",
];

fn is_valid_openai_voice(id: &str) -> bool {
    OPENAI_VOICES.contains(&id)
}

#[derive(Deserialize, Serialize)]
struct VoiceSettings {
    stability: Option<f64>,
    similarity_boost: Option<f64>,
    style: Option<f64>,
    use_speaker_boost: Option<bool>,
}

fn default_voice_id() -> String {
    "BAMYoBHLZM7lJgJAmFz0".to_string() // Sloane
}

fn default_model_id() -> String {
    "eleven_turbo_v2_5".to_string()
}

fn default_output_format() -> String {
    "mp3_44100_128".to_string()
}

#[derive(Serialize)]
struct TtsErrorResponse {
    error: TtsErrorDetail,
}

#[derive(Serialize)]
struct TtsErrorDetail {
    message: String,
    code: u16,
}

/// POST /v1/tts/synthesize
/// Proxies TTS requests to the selected provider (default: ElevenLabs). Per-user rate limited.
async fn tts_synthesize(
    State(state): State<AppState>,
    user: AuthUser,
    Json(req): Json<TtsSynthesizeRequest>,
) -> Result<Response, Response> {
    let provider = req
        .provider
        .as_deref()
        .map(|p| p.to_ascii_lowercase())
        .unwrap_or_else(|| "elevenlabs".to_string());

    // Validate voice_id per provider before any external work.
    match provider.as_str() {
        "elevenlabs" => {
            if !is_valid_voice_id(&req.voice_id) {
                return Err(error_response(StatusCode::BAD_REQUEST, "invalid voice_id"));
            }
        }
        "openai" => {
            if !is_valid_openai_voice(&req.voice_id) {
                return Err(error_response(
                    StatusCode::BAD_REQUEST,
                    "invalid voice_id for openai provider",
                ));
            }
        }
        other => {
            tracing::warn!("tts_synthesize: unknown provider '{}'", other);
            return Err(error_response(
                StatusCode::BAD_REQUEST,
                "invalid provider (must be 'elevenlabs' or 'openai')",
            ));
        }
    }

    // Validate text is not empty and not excessively long (single request cap: 5000 chars)
    let char_count = validate_text(&req.text)
        .map_err(|message| error_response(StatusCode::BAD_REQUEST, message))?;

    // Rate limit check (Redis-backed, fail closed) — shared limits across providers
    let redis = state.redis.as_ref().ok_or_else(|| {
        tracing::error!("tts_synthesize: Redis not configured — TTS rate limiting requires Redis");
        error_response(
            StatusCode::SERVICE_UNAVAILABLE,
            "TTS service temporarily unavailable",
        )
    })?;

    match redis
        .check_tts_rate_limit(
            &user.uid,
            TTS_BURST_PER_MINUTE,
            TTS_BURST_WINDOW_SECS,
            char_count,
            TTS_DAILY_CHAR_LIMIT,
        )
        .await
    {
        Ok(TtsRateResult::Allow) => {}
        Ok(TtsRateResult::BurstExceeded) => {
            tracing::warn!("tts_synthesize: burst rate limit exceeded uid={}", user.uid);
            return Err(rate_limit_response_with_retry(
                "Rate limit exceeded: too many requests. Try again in 60 seconds.",
                60,
            ));
        }
        Ok(TtsRateResult::DailyCharsExceeded) => {
            tracing::warn!(
                "tts_synthesize: daily character limit exceeded uid={}",
                user.uid
            );
            return Err(rate_limit_response_with_retry(
                "Daily character limit exceeded (10,000 characters). Resets at midnight UTC.",
                seconds_until_midnight_utc(),
            ));
        }
        Err(e) => {
            tracing::error!("tts_synthesize: Redis error — failing closed: {}", e);
            return Err(error_response(
                StatusCode::SERVICE_UNAVAILABLE,
                "TTS service temporarily unavailable",
            ));
        }
    }

    let (upstream_url, headers, body) = match provider.as_str() {
        "openai" => {
            let key = state.config.openai_api_key.as_ref().ok_or_else(|| {
                tracing::error!("tts_synthesize: OPENAI_API_KEY not configured");
                error_response(
                    StatusCode::SERVICE_UNAVAILABLE,
                    "OpenAI TTS not configured",
                )
            })?;
            // OpenAI model: prefer "gpt-4o-mini-tts" (cheaper + better voices) when the
            // client didn't override model_id with an OpenAI-specific name; fall back
            // to "tts-1" if the caller asked for it explicitly.
            let openai_model = if req.model_id == "tts-1" || req.model_id == "tts-1-hd" {
                req.model_id.clone()
            } else {
                "gpt-4o-mini-tts".to_string()
            };
            let body = serde_json::json!({
                "model": openai_model,
                "input": req.text,
                "voice": req.voice_id,
                "response_format": "mp3",
            });
            let headers = vec![
                ("Content-Type", "application/json".to_string()),
                ("Accept", "audio/mpeg".to_string()),
                ("Authorization", format!("Bearer {}", key)),
            ];
            (
                "https://api.openai.com/v1/audio/speech".to_string(),
                headers,
                body,
            )
        }
        _ => {
            let key = state.config.elevenlabs_api_key.as_ref().ok_or_else(|| {
                tracing::error!("tts_synthesize: ELEVENLABS_API_KEY not configured");
                error_response(
                    StatusCode::SERVICE_UNAVAILABLE,
                    "ElevenLabs TTS not configured",
                )
            })?;
            let mut body = serde_json::json!({
                "text": req.text,
                "model_id": req.model_id,
                "output_format": req.output_format,
            });
            if let Some(vs) = &req.voice_settings {
                body["voice_settings"] = serde_json::to_value(vs).unwrap_or_default();
            }
            let headers = vec![
                ("Content-Type", "application/json".to_string()),
                ("Accept", "audio/mpeg".to_string()),
                ("xi-api-key", key.clone()),
            ];
            let url = format!(
                "https://api.elevenlabs.io/v1/text-to-speech/{}",
                req.voice_id
            );
            (url, headers, body)
        }
    };

    let mut request_builder = reqwest::Client::new()
        .post(&upstream_url)
        .body(serde_json::to_vec(&body).unwrap_or_default())
        .timeout(std::time::Duration::from_secs(60));
    for (name, value) in &headers {
        request_builder = request_builder.header(*name, value);
    }
    let upstream = request_builder.send().await.map_err(|e| {
        tracing::error!(
            "tts_synthesize: upstream request failed (provider={}): {}",
            provider,
            e
        );
        StatusCode::BAD_GATEWAY.into_response()
    })?;

    let status =
        StatusCode::from_u16(upstream.status().as_u16()).unwrap_or(StatusCode::BAD_GATEWAY);

    if !status.is_success() {
        let error_body = upstream.text().await.unwrap_or_default();
        tracing::warn!(
            "tts_synthesize: provider={} returned {} for uid={}: {}",
            provider,
            status.as_u16(),
            user.uid,
            &error_body[..error_body.len().min(200)]
        );
        return Err((status, error_body).into_response());
    }

    let audio_bytes = upstream.bytes().await.map_err(|e| {
        tracing::error!("tts_synthesize: failed to read upstream body: {}", e);
        StatusCode::BAD_GATEWAY.into_response()
    })?;

    Ok(Response::builder()
        .status(StatusCode::OK)
        .header("Content-Type", "audio/mpeg")
        .header("Content-Length", audio_bytes.len().to_string())
        .body(axum::body::Body::from(audio_bytes))
        .unwrap())
}

/// Validate voice_id: alphanumeric only, 1-128 chars. Rejects path traversal and injection.
fn is_valid_voice_id(id: &str) -> bool {
    !id.is_empty() && id.len() <= 128 && id.chars().all(|c| c.is_ascii_alphanumeric())
}

fn validate_text(text: &str) -> Result<i64, &'static str> {
    if text.is_empty() {
        return Err("text must not be empty");
    }

    let char_count = text.chars().count() as i64;
    if char_count > TTS_REQUEST_CHAR_LIMIT {
        return Err("text exceeds maximum length of 5000 characters");
    }

    Ok(char_count)
}

fn error_response(status: StatusCode, message: &str) -> Response {
    let body = TtsErrorResponse {
        error: TtsErrorDetail {
            message: message.to_string(),
            code: status.as_u16(),
        },
    };
    (status, Json(body)).into_response()
}

fn rate_limit_response_with_retry(message: &str, retry_after_secs: u64) -> Response {
    let body = serde_json::json!({
        "error": {
            "message": message,
            "code": 429,
        }
    });
    Response::builder()
        .status(StatusCode::TOO_MANY_REQUESTS)
        .header("Content-Type", "application/json")
        .header("Retry-After", retry_after_secs.to_string())
        .body(axum::body::Body::from(
            serde_json::to_vec(&body).unwrap_or_default(),
        ))
        .unwrap()
}

/// Seconds remaining until the next UTC midnight (for daily limit Retry-After).
fn seconds_until_midnight_utc() -> u64 {
    let now = chrono::Utc::now();
    let tomorrow = (now + chrono::Duration::days(1))
        .date_naive()
        .and_hms_opt(0, 0, 0)
        .unwrap();
    let midnight = tomorrow.and_utc();
    (midnight - now).num_seconds().max(1) as u64
}

/// Result of a TTS rate limit check.
pub enum TtsRateResult {
    Allow,
    BurstExceeded,
    DailyCharsExceeded,
}

pub fn tts_routes() -> Router<AppState> {
    Router::new().route("/v1/tts/synthesize", post(tts_synthesize))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn default_voice_id_is_sloane() {
        assert_eq!(default_voice_id(), "BAMYoBHLZM7lJgJAmFz0");
    }

    // --- voice_id validation (path traversal prevention) ---

    #[test]
    fn valid_voice_id_alphanumeric() {
        assert!(is_valid_voice_id("BAMYoBHLZM7lJgJAmFz0"));
        assert!(is_valid_voice_id("abc123"));
        assert!(is_valid_voice_id("A"));
    }

    #[test]
    fn reject_voice_id_path_traversal() {
        assert!(!is_valid_voice_id("../../history"));
        assert!(!is_valid_voice_id("../v1/voices"));
        assert!(!is_valid_voice_id("foo/bar"));
    }

    #[test]
    fn reject_voice_id_special_chars() {
        assert!(!is_valid_voice_id("id-with-dash"));
        assert!(!is_valid_voice_id("id_with_underscore"));
        assert!(!is_valid_voice_id("id with space"));
        assert!(!is_valid_voice_id("id?query=1"));
    }

    #[test]
    fn reject_voice_id_empty() {
        assert!(!is_valid_voice_id(""));
    }

    #[test]
    fn reject_voice_id_too_long() {
        let long_id: String = "a".repeat(129);
        assert!(!is_valid_voice_id(&long_id));
        let max_id: String = "a".repeat(128);
        assert!(is_valid_voice_id(&max_id));
    }

    #[test]
    fn default_model_id_value() {
        assert_eq!(default_model_id(), "eleven_turbo_v2_5");
    }

    #[test]
    fn default_output_format_value() {
        assert_eq!(default_output_format(), "mp3_44100_128");
    }

    #[test]
    fn deserialize_request_applies_defaults() {
        let req: TtsSynthesizeRequest = serde_json::from_value(serde_json::json!({
            "text": "hello"
        }))
        .unwrap();

        assert_eq!(req.text, "hello");
        assert_eq!(req.voice_id, default_voice_id());
        assert_eq!(req.model_id, default_model_id());
        assert_eq!(req.output_format, default_output_format());
        assert!(req.voice_settings.is_none());
        assert!(req.provider.is_none());
    }

    #[test]
    fn openai_voice_validation() {
        for v in ["alloy", "shimmer", "nova", "coral", "sage", "onyx"] {
            assert!(is_valid_openai_voice(v), "expected {v} to be valid");
        }
        assert!(!is_valid_openai_voice("Shimmer")); // case-sensitive
        assert!(!is_valid_openai_voice("not-a-voice"));
        assert!(!is_valid_openai_voice(""));
    }

    #[test]
    fn deserialize_request_with_openai_provider() {
        let req: TtsSynthesizeRequest = serde_json::from_value(serde_json::json!({
            "text": "hello",
            "voice_id": "shimmer",
            "provider": "openai",
        }))
        .unwrap();
        assert_eq!(req.provider.as_deref(), Some("openai"));
        assert_eq!(req.voice_id, "shimmer");
    }

    #[test]
    fn validate_text_rejects_empty() {
        assert_eq!(validate_text(""), Err("text must not be empty"));
    }

    #[test]
    fn validate_text_accepts_max_length() {
        let text = "a".repeat(TTS_REQUEST_CHAR_LIMIT as usize);
        assert_eq!(validate_text(&text), Ok(TTS_REQUEST_CHAR_LIMIT));
    }

    #[test]
    fn validate_text_rejects_over_limit() {
        let text = "a".repeat((TTS_REQUEST_CHAR_LIMIT + 1) as usize);
        assert_eq!(
            validate_text(&text),
            Err("text exceeds maximum length of 5000 characters")
        );
    }

    #[test]
    fn error_response_format() {
        let resp = error_response(StatusCode::BAD_REQUEST, "test error");
        assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    }

    #[test]
    fn rate_limit_response_burst() {
        let resp = rate_limit_response_with_retry("too many", 60);
        assert_eq!(resp.status(), StatusCode::TOO_MANY_REQUESTS);
        assert_eq!(resp.headers().get("Retry-After").unwrap(), "60");
    }

    #[test]
    fn rate_limit_response_daily() {
        let resp = rate_limit_response_with_retry("daily limit", 3600);
        assert_eq!(resp.status(), StatusCode::TOO_MANY_REQUESTS);
        assert_eq!(resp.headers().get("Retry-After").unwrap(), "3600");
    }

    #[test]
    fn seconds_until_midnight_is_positive() {
        let secs = seconds_until_midnight_utc();
        assert!(secs >= 1);
        assert!(secs <= 86400);
    }
}
