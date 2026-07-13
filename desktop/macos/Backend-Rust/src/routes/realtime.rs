// Realtime-hub ephemeral token mint (Phase 2).
//
// Managed (subscription) users can't ship OMI's provider keys to the client, so
// the client asks this route for a SHORT-LIVED ephemeral token and connects to
// the provider's realtime WebSocket client-direct with it. The backend stays out
// of the audio path (the latency win) and never sees realtime minutes/tokens
// inline — entitlement is gated here at mint, cost is bounded by the token's
// short lifetime / single use, and spend is reconciled out-of-band.
//
// Auth + paywall gate is the `PaywalledAuthUser` extractor: it returns 402
// (trial_expired) / 403 (byok mismatch) before this handler runs, so the client
// simply falls back to the legacy cascade on any non-200.
//
// Wire formats are the ones verified empirically (see the Phase 2 spike notes):
//   • OpenAI : POST /v1/realtime/client_secrets  → "ek_…"  (used as Bearer, GA)
//   • Gemini : POST /v1alpha/auth_tokens         → "auth_tokens/…"
//              (used as ?access_token= on the BidiGenerateContentConstrained WS)

use axum::{
    extract::State,
    http::StatusCode,
    response::{IntoResponse, Response},
    routing::post,
    Json, Router,
};
use chrono::{Duration as ChronoDuration, Utc};
use serde::{Deserialize, Serialize};
use std::time::Duration;

use crate::auth::PaywalledAuthUser;
use crate::AppState;

const OPENAI_CLIENT_SECRETS_URL: &str = "https://api.openai.com/v1/realtime/client_secrets";
const GEMINI_AUTH_TOKENS_URL: &str =
    "https://generativelanguage.googleapis.com/v1alpha/auth_tokens";
const OPENAI_REALTIME_MODEL: &str = "gpt-realtime-2";
const GEMINI_LIVE_MODEL: &str = "models/gemini-3.1-flash-live-preview";

/// Minutes a minted token may be used to START a session (Gemini newSessionExpireTime).
const SESSION_START_WINDOW_MIN: i64 = 2;
/// Minutes a started session may run (Gemini expireTime). Caps realtime spend.
const SESSION_MAX_MIN: i64 = 30;

#[derive(Debug, Deserialize)]
struct MintRequest {
    /// "openai" | "gemini"
    provider: String,
}

#[derive(Serialize)]
struct MintResponse {
    provider: String,
    /// OpenAI: the "ek_…" client secret. Gemini: the "auth_tokens/…" name.
    token: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    expires_at: Option<String>,
}

enum MintError {
    BadProvider,
    QuotaExceeded,
    MissingKey(&'static str),
    Upstream {
        provider: &'static str,
        status: StatusCode,
        reason: &'static str,
        code: Option<String>,
        message: String,
        retryable: bool,
    },
    BadGateway(String),
}

impl IntoResponse for MintError {
    fn into_response(self) -> Response {
        let (status, body) = match self {
            MintError::BadProvider => mint_error_body(
                StatusCode::BAD_REQUEST,
                "bad_provider",
                "provider must be \"openai\" or \"gemini\"".to_string(),
                None,
                None,
                None,
                false,
            ),
            MintError::QuotaExceeded => mint_error_body(
                StatusCode::PAYMENT_REQUIRED,
                "quota_exceeded",
                "Monthly free limit reached. Upgrade to keep using realtime voice.".to_string(),
                None,
                None,
                None,
                false,
            ),
            MintError::MissingKey(p) => mint_error_body(
                StatusCode::SERVICE_UNAVAILABLE,
                "provider_not_configured",
                format!("{} realtime is not configured", p),
                Some(p),
                None,
                None,
                true,
            ),
            MintError::Upstream {
                provider,
                status,
                reason,
                code,
                message,
                retryable,
            } => mint_error_body(
                status,
                reason,
                message,
                Some(provider),
                code,
                Some(status.as_u16()),
                retryable,
            ),
            MintError::BadGateway(message) => mint_error_body(
                StatusCode::BAD_GATEWAY,
                "provider_mint_transport_error",
                message,
                None,
                None,
                None,
                true,
            ),
        };
        (status, Json(body)).into_response()
    }
}

fn mint_error_body(
    status: StatusCode,
    reason: &str,
    message: String,
    provider: Option<&str>,
    code: Option<String>,
    upstream_status_code: Option<u16>,
    retryable: bool,
) -> (StatusCode, serde_json::Value) {
    let mut body = serde_json::json!({
        "error": message,
        "reason": reason,
        "backend_route": "/v2/realtime/session",
        "retryable": retryable,
    });
    if let Some(provider) = provider {
        body["provider"] = serde_json::Value::String(provider.to_string());
    }
    if let Some(code) = code {
        body["code"] = serde_json::Value::String(code);
    }
    if let Some(upstream_status_code) = upstream_status_code {
        body["upstream_status_code"] = serde_json::Value::Number(upstream_status_code.into());
    }
    (status, body)
}

fn classify_upstream_mint_error(
    provider: &'static str,
    status: StatusCode,
    body: &str,
) -> MintError {
    let (code, message) = parse_upstream_error(body);
    let lower = format!(
        "{} {}",
        code.as_deref().unwrap_or_default(),
        message.as_str()
    )
    .to_lowercase();
    let reason = if status == StatusCode::TOO_MANY_REQUESTS || lower.contains("quota") {
        "provider_quota_exceeded"
    } else if status == StatusCode::UNAUTHORIZED
        || status == StatusCode::FORBIDDEN
        || lower.contains("invalid api key")
        || lower.contains("api key not valid")
        || lower.contains("authentication")
        || lower.contains("permission denied")
    {
        "provider_auth_failed"
    } else if status.is_server_error() {
        "provider_mint_unavailable"
    } else {
        "provider_mint_rejected"
    };
    MintError::Upstream {
        provider,
        status,
        reason,
        code,
        message,
        retryable: status == StatusCode::TOO_MANY_REQUESTS || status.is_server_error(),
    }
}

fn parse_upstream_error(body: &str) -> (Option<String>, String) {
    let parsed = serde_json::from_str::<serde_json::Value>(body).ok();
    let error = parsed.as_ref().and_then(|v| v.get("error"));
    let code = error
        .and_then(|e| {
            value_as_string_code(e.get("code"))
                .or_else(|| value_as_string_code(e.get("status")))
                .or_else(|| value_as_numeric_code(e.get("code")))
        })
        .or_else(|| {
            parsed.as_ref().and_then(|v| {
                value_as_string_code(v.get("code")).or_else(|| value_as_numeric_code(v.get("code")))
            })
        });
    let message = error
        .and_then(|e| e.get("message"))
        .or_else(|| parsed.as_ref().and_then(|v| v.get("message")))
        .and_then(|v| v.as_str())
        .map(str::to_string)
        .unwrap_or_else(|| {
            if body.chars().count() > 500 {
                format!("{}...", body.chars().take(500).collect::<String>())
            } else {
                body.to_string()
            }
        });
    (code, message)
}

fn value_as_string_code(value: Option<&serde_json::Value>) -> Option<String> {
    match value? {
        serde_json::Value::String(s) if !s.is_empty() => Some(s.clone()),
        _ => None,
    }
}

fn value_as_numeric_code(value: Option<&serde_json::Value>) -> Option<String> {
    match value? {
        serde_json::Value::Number(n) => Some(n.to_string()),
        _ => None,
    }
}

fn http_client() -> reqwest::Client {
    reqwest::Client::builder()
        .connect_timeout(Duration::from_secs(10))
        .timeout(Duration::from_secs(15))
        .build()
        .unwrap_or_default()
}

async fn mint_session(
    State(state): State<AppState>,
    user: PaywalledAuthUser,
    Json(request): Json<MintRequest>,
) -> Result<Json<MintResponse>, MintError> {
    // PaywalledAuthUser already enforced auth + paywall (402/403) before we got here.
    // Realtime sessions are ALWAYS minted on Omi's server keys (BYOK keys are
    // never used on this lane), so the quota verdict applies even to validated
    // BYOK requests — otherwise a fake-fingerprint enrollment buys Omi-funded
    // realtime past the free cap.
    if user.quota_blocked {
        return Err(MintError::QuotaExceeded);
    }
    match request.provider.as_str() {
        "openai" => mint_openai(&state, &user.uid).await,
        "gemini" => mint_gemini(&state, &user.uid).await,
        _ => Err(MintError::BadProvider),
    }
    .map(Json)
}

/// Send a mint request and return the parsed JSON body, mapping transport errors to
/// BadGateway and any non-2xx upstream to Upstream (so the client falls back).
async fn send_and_parse(
    req: reqwest::RequestBuilder,
    provider: &'static str,
    uid: &str,
) -> Result<serde_json::Value, MintError> {
    let resp = req
        .send()
        .await
        .map_err(|e| MintError::BadGateway(e.to_string()))?;
    let status = StatusCode::from_u16(resp.status().as_u16()).unwrap_or(StatusCode::BAD_GATEWAY);
    let text = resp
        .text()
        .await
        .map_err(|e| MintError::BadGateway(e.to_string()))?;
    if !status.is_success() {
        tracing::warn!(
            "realtime mint({}) {} for uid={}: {}",
            provider,
            status,
            uid,
            text
        );
        return Err(classify_upstream_mint_error(provider, status, &text));
    }
    serde_json::from_str(&text).map_err(|e| MintError::BadGateway(e.to_string()))
}

/// Best-effort: persist a non-secret record of the minted session (for out-of-band
/// billing reconciliation). Never fails the mint — a transient Firestore blip shouldn't
/// drop the user to the cascade — but logs loudly, since a missing record means the
/// session can't be reconciled/billed.
async fn record_session(
    state: &AppState,
    uid: &str,
    token: &str,
    provider: &str,
    model: &str,
    expires_at: Option<&str>,
) {
    if let Err(e) = state
        .firestore
        .record_realtime_session(
            uid,
            token,
            provider,
            model,
            expires_at.unwrap_or(""),
            SESSION_MAX_MIN,
        )
        .await
    {
        tracing::warn!(
            "realtime session-record write failed for uid={}: {}",
            uid,
            e
        );
    }
}

async fn mint_openai(state: &AppState, uid: &str) -> Result<MintResponse, MintError> {
    let key = state
        .config
        .openai_api_key
        .as_deref()
        .map(str::trim)
        .filter(|v| !v.is_empty())
        .ok_or(MintError::MissingKey("OpenAI"))?;

    // Lock the model server-side; the client still sends its own session.update
    // (tools/instructions/audio format) on connect.
    let body = serde_json::json!({
        "session": { "type": "realtime", "model": OPENAI_REALTIME_MODEL }
    });
    let req = http_client()
        .post(OPENAI_CLIENT_SECRETS_URL)
        .bearer_auth(key)
        .json(&body);

    let json = send_and_parse(req, "openai", uid).await?;
    let token = json
        .get("value")
        .and_then(|v| v.as_str())
        .ok_or_else(|| MintError::BadGateway("openai mint: no client secret in response".into()))?
        .to_string();
    let expires_at = json.get("expires_at").map(|v| v.to_string());
    record_session(
        state,
        uid,
        &token,
        "openai",
        OPENAI_REALTIME_MODEL,
        expires_at.as_deref(),
    )
    .await;
    tracing::info!("realtime mint(openai) ok for uid={}", uid);
    Ok(MintResponse {
        provider: "openai".to_string(),
        token,
        expires_at,
    })
}

async fn mint_gemini(state: &AppState, uid: &str) -> Result<MintResponse, MintError> {
    let key = state
        .config
        .gemini_api_key
        .as_deref()
        .map(str::trim)
        .filter(|v| !v.is_empty())
        .ok_or(MintError::MissingKey("Gemini"))?;

    let now = Utc::now();
    let new_session_expire = (now + ChronoDuration::minutes(SESSION_START_WINDOW_MIN))
        .format("%Y-%m-%dT%H:%M:%SZ")
        .to_string();
    let expire = (now + ChronoDuration::minutes(SESSION_MAX_MIN))
        .format("%Y-%m-%dT%H:%M:%SZ")
        .to_string();

    let body = gemini_auth_token_body(&new_session_expire, &expire);
    let req = http_client()
        .post(GEMINI_AUTH_TOKENS_URL)
        .query(&[("key", key)])
        .json(&body);

    let json = send_and_parse(req, "gemini", uid).await?;
    let token = json
        .get("name")
        .and_then(|v| v.as_str())
        .ok_or_else(|| MintError::BadGateway("gemini mint: no token name in response".into()))?
        .to_string();
    record_session(
        state,
        uid,
        &token,
        "gemini",
        GEMINI_LIVE_MODEL,
        Some(&expire),
    )
    .await;
    tracing::info!("realtime mint(gemini) ok for uid={}", uid);
    Ok(MintResponse {
        provider: "gemini".to_string(),
        token,
        expires_at: Some(expire),
    })
}

fn gemini_auth_token_body(new_session_expire: &str, expire: &str) -> serde_json::Value {
    // The Gemini Developer API's CreateAuthToken (POST /v1alpha/auth_tokens)
    // takes the token settings FLAT at the request root — this matches the
    // google-genai SDK, whose request converter sets `uses`/`expireTime`/
    // `newSessionExpireTime` directly on the request body. Wrapping them under
    // `authToken` makes v1alpha reject the request with
    // `Unknown name "authToken" ... Cannot find field`.
    serde_json::json!({
        "uses": 1,
        "expireTime": expire,
        "newSessionExpireTime": new_session_expire,
    })
}

// =============================================================================
// Usage reporting (Phase 2, v1 — client-reported)
//
// The realtime WS is client↔provider direct, so the backend never sees usage inline.
// As a first pass, the CLIENT reports the provider's own per-turn token counts here and
// we price + record them into the same llm_usage ledger chat uses (account "realtime"),
// and separately increment the explicit desktop question quota counter for the
// accepted managed turn. This is CLIENT-TRUSTED (a tampered
// client could under-report) — acceptable for v1; the eventual hardening is server-side
// reconciliation against the provider Usage API (OpenAI exposes per-user usage via the
// OpenAI-Safety-Identifier; the minted realtime_sessions records are the audit trail).
// Only MANAGED (ephemeral-token) sessions report — BYOK users pay the provider directly.
// =============================================================================

/// Per-1M-token rates ($), split by modality the way both providers bill.
struct RealtimeRates {
    in_text: f64,
    in_audio: f64,
    cached: f64,
    out_text: f64,
    out_audio: f64,
}

/// Realtime model pricing. NOTE: gpt-realtime-2 rates are from OpenAI's published
/// pricing; the Gemini live audio rates are APPROXIMATE (Google doesn't cleanly publish
/// live-audio token rates) and should be verified before relying on them for revenue.
fn realtime_rates(provider: &str, _model: &str) -> RealtimeRates {
    match provider {
        // gpt-realtime-2: audio in $32 / out $64, text in $4 / out $24, cached $0.40 per 1M.
        "openai" => RealtimeRates {
            in_text: 4.0,
            in_audio: 32.0,
            cached: 0.40,
            out_text: 24.0,
            out_audio: 64.0,
        },
        // gemini-3.1-flash-live (Google published paid-tier rates, per 1M tokens):
        // input text $0.75 / audio $3.00; output text $4.50 / audio $12.00. Google does
        // not publish a live cache-read rate — estimated at ~10% of input text (rarely
        // fires for realtime turns anyway).
        _ => RealtimeRates {
            in_text: 0.75,
            in_audio: 3.0,
            cached: 0.075,
            out_text: 4.5,
            out_audio: 12.0,
        },
    }
}

#[derive(Debug, Deserialize)]
struct UsageReport {
    /// "openai" | "gemini"
    provider: String,
    #[serde(default)]
    model: String,
    #[serde(default)]
    input_text_tokens: i64,
    #[serde(default)]
    input_audio_tokens: i64,
    #[serde(default)]
    input_cached_tokens: i64,
    #[serde(default)]
    output_text_tokens: i64,
    #[serde(default)]
    output_audio_tokens: i64,
}

fn usage_cost(r: &UsageReport) -> f64 {
    let rates = realtime_rates(&r.provider, &r.model);
    // Token counts are fully client-reported. Clamp negatives to 0 so a tampered
    // client cannot drive `cost` (and the Firestore cost/quota ledger) negative.
    (r.input_text_tokens.max(0) as f64 * rates.in_text
        + r.input_audio_tokens.max(0) as f64 * rates.in_audio
        + r.input_cached_tokens.max(0) as f64 * rates.cached
        + r.output_text_tokens.max(0) as f64 * rates.out_text
        + r.output_audio_tokens.max(0) as f64 * rates.out_audio)
        / 1_000_000.0
}

/// Record one client-reported realtime turn's usage into the llm_usage ledger.
async fn report_usage(
    State(state): State<AppState>,
    user: PaywalledAuthUser,
    Json(report): Json<UsageReport>,
) -> StatusCode {
    // Token counts are fully client-reported; clamp negatives to 0 before summing
    // so a tampered client cannot record negative usage that understates cost or
    // resets accrued quota in the shared llm_usage ledger.
    let input = report.input_text_tokens.max(0) + report.input_audio_tokens.max(0);
    let output = report.output_text_tokens.max(0) + report.output_audio_tokens.max(0);
    let cached = report.input_cached_tokens.max(0);
    let total = input + output + cached;
    if total <= 0 {
        return StatusCode::NO_CONTENT;
    }
    let cost = usage_cost(&report);
    // Funnels into desktop_chat.cost_usd (counted by get_total_llm_cost/quota) plus a
    // "desktop_chat_realtime.*" breakdown.
    if let Err(e) = state
        .firestore
        .record_llm_usage(&user.uid, input, output, cached, 0, total, cost, "realtime")
        .await
    {
        tracing::error!("realtime usage record failed for uid={}: {}", user.uid, e);
        return StatusCode::BAD_GATEWAY;
    }
    if let Err(e) = state
        .firestore
        .record_desktop_chat_quota_question_with_account(&user.uid, Some("realtime"))
        .await
    {
        tracing::error!(
            "realtime quota question record failed for uid={}: {}",
            user.uid,
            e
        );
        return StatusCode::BAD_GATEWAY;
    }
    tracing::info!(
        "realtime usage uid={} provider={} in={} out={} cached={} cost=${:.5}",
        user.uid,
        report.provider,
        input,
        output,
        cached,
        cost
    );
    StatusCode::NO_CONTENT
}

pub fn realtime_routes() -> Router<AppState> {
    Router::new()
        .route("/v2/realtime/session", post(mint_session))
        .route("/v2/realtime/usage", post(report_usage))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn usage_cost_never_negative_for_negative_client_tokens() {
        // A tampered client reporting negative token counts must not yield a
        // negative cost that would understate/negate the shared cost ledger.
        let report = UsageReport {
            provider: "openai".to_string(),
            model: String::new(),
            input_text_tokens: -1_000_000,
            input_audio_tokens: -1_000_000,
            input_cached_tokens: -1_000_000,
            output_text_tokens: -1_000_000,
            output_audio_tokens: -1_000_000,
        };
        assert_eq!(usage_cost(&report), 0.0);
    }

    #[test]
    fn usage_cost_ignores_negative_fields_but_counts_positive_ones() {
        // A mix of one legitimate positive field and negative padding must equal
        // the cost of the positive field alone (negatives clamped, not subtracted).
        let mixed = UsageReport {
            provider: "openai".to_string(),
            model: String::new(),
            input_text_tokens: 1000,
            input_audio_tokens: -5000,
            input_cached_tokens: -5000,
            output_text_tokens: 0,
            output_audio_tokens: 0,
        };
        let positive_only = UsageReport {
            provider: "openai".to_string(),
            model: String::new(),
            input_text_tokens: 1000,
            input_audio_tokens: 0,
            input_cached_tokens: 0,
            output_text_tokens: 0,
            output_audio_tokens: 0,
        };
        assert_eq!(usage_cost(&mixed), usage_cost(&positive_only));
        assert!(usage_cost(&mixed) > 0.0);
    }

    #[test]
    fn gemini_auth_token_body_is_flat_at_request_root() {
        let body = gemini_auth_token_body("2026-07-03T18:40:00Z", "2026-07-03T19:08:00Z");

        // v1alpha auth_tokens takes the settings flat at the root (google-genai
        // SDK shape); wrapping under `authToken` is what caused the mint 400s.
        assert_eq!(body["uses"], 1);
        assert_eq!(body["newSessionExpireTime"], "2026-07-03T18:40:00Z");
        assert_eq!(body["expireTime"], "2026-07-03T19:08:00Z");
        assert!(body.get("authToken").is_none());
    }

    #[test]
    fn classifies_upstream_auth_error_with_safe_structured_body() {
        let error = classify_upstream_mint_error(
            "openai",
            StatusCode::UNAUTHORIZED,
            r#"{"error":{"message":"Invalid authentication credentials","code":"invalid_api_key"}}"#,
        );

        let response = error.into_response();
        assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
    }

    #[test]
    fn upstream_error_body_includes_actionable_fields() {
        let (_status, body) = mint_error_body(
            StatusCode::TOO_MANY_REQUESTS,
            "provider_quota_exceeded",
            "quota exhausted".to_string(),
            Some("gemini"),
            Some("RESOURCE_EXHAUSTED".to_string()),
            Some(429),
            true,
        );

        assert_eq!(body["provider"], "gemini");
        assert_eq!(body["reason"], "provider_quota_exceeded");
        assert_eq!(body["backend_route"], "/v2/realtime/session");
        assert_eq!(body["upstream_status_code"], 429);
        assert_eq!(body["code"], "RESOURCE_EXHAUSTED");
        assert_eq!(body["retryable"], true);
    }

    #[test]
    fn missing_key_error_body_includes_provider() {
        let (_status, body) = mint_error_body(
            StatusCode::SERVICE_UNAVAILABLE,
            "provider_not_configured",
            "Gemini realtime is not configured".to_string(),
            Some("Gemini"),
            None,
            None,
            true,
        );

        assert_eq!(body["provider"], "Gemini");
    }

    #[test]
    fn parse_upstream_error_preserves_status_when_code_is_numeric() {
        let (code, message) = parse_upstream_error(
            r#"{"error":{"code":429,"status":"RESOURCE_EXHAUSTED","message":"Quota exhausted"}}"#,
        );

        assert_eq!(code.as_deref(), Some("RESOURCE_EXHAUSTED"));
        assert_eq!(message, "Quota exhausted");
    }
}
