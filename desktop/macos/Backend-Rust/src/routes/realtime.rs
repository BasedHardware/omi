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
    MissingKey(&'static str),
    Upstream(StatusCode, String),
    BadGateway(String),
}

impl IntoResponse for MintError {
    fn into_response(self) -> Response {
        let (status, message) = match self {
            MintError::BadProvider => (
                StatusCode::BAD_REQUEST,
                "provider must be \"openai\" or \"gemini\"".to_string(),
            ),
            MintError::MissingKey(p) => (
                StatusCode::SERVICE_UNAVAILABLE,
                format!("{} realtime is not configured", p),
            ),
            MintError::Upstream(status, body) => {
                let safe = if body.chars().count() > 500 {
                    format!("{}...", body.chars().take(500).collect::<String>())
                } else {
                    body
                };
                (status, format!("token mint failed: {}", safe))
            }
            MintError::BadGateway(message) => (StatusCode::BAD_GATEWAY, message),
        };
        (status, Json(serde_json::json!({ "error": message }))).into_response()
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
    provider: &str,
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
        tracing::warn!("realtime mint({}) {} for uid={}: {}", provider, status, uid, text);
        return Err(MintError::Upstream(status, text));
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
        .record_realtime_session(uid, token, provider, model, expires_at.unwrap_or(""), SESSION_MAX_MIN)
        .await
    {
        tracing::warn!("realtime session-record write failed for uid={}: {}", uid, e);
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
    record_session(state, uid, &token, "openai", OPENAI_REALTIME_MODEL, expires_at.as_deref()).await;
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

    // Single use + short windows bound the cost. NOTE: only the bare token form is
    // verified to connect to the BidiGenerateContentConstrained endpoint; locking the
    // model/config via `liveConnectConstraints` is a follow-up that needs its own
    // spike (the constraint shape wasn't verified) — see Phase 2 spike notes.
    let body = serde_json::json!({
        "uses": 1,
        "expireTime": expire,
        "newSessionExpireTime": new_session_expire,
    });
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
    record_session(state, uid, &token, "gemini", GEMINI_LIVE_MODEL, Some(&expire)).await;
    tracing::info!("realtime mint(gemini) ok for uid={}", uid);
    Ok(MintResponse {
        provider: "gemini".to_string(),
        token,
        expires_at: Some(expire),
    })
}

// =============================================================================
// Usage reporting (Phase 2, v1 — client-reported)
//
// The realtime WS is client↔provider direct, so the backend never sees usage inline.
// As a first pass, the CLIENT reports the provider's own per-turn token counts here and
// we price + record them into the same llm_usage ledger chat uses (account "realtime"),
// so realtime spend counts toward the user's quota. This is CLIENT-TRUSTED (a tampered
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
        // gemini-3.1-flash-live (APPROXIMATE — verify): text in $0.50 / out $3.00;
        // audio ~4x text in, and audio out ~$12 per 1M.
        _ => RealtimeRates {
            in_text: 0.50,
            in_audio: 2.0,
            cached: 0.125,
            out_text: 3.0,
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
    (r.input_text_tokens as f64 * rates.in_text
        + r.input_audio_tokens as f64 * rates.in_audio
        + r.input_cached_tokens as f64 * rates.cached
        + r.output_text_tokens as f64 * rates.out_text
        + r.output_audio_tokens as f64 * rates.out_audio)
        / 1_000_000.0
}

/// Record one client-reported realtime turn's usage into the llm_usage ledger.
async fn report_usage(
    State(state): State<AppState>,
    user: PaywalledAuthUser,
    Json(report): Json<UsageReport>,
) -> StatusCode {
    let input = report.input_text_tokens + report.input_audio_tokens;
    let output = report.output_text_tokens + report.output_audio_tokens;
    let cached = report.input_cached_tokens;
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
