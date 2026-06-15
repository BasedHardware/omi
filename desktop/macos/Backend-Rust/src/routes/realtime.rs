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
    let _ = GEMINI_LIVE_MODEL;
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
    tracing::info!("realtime mint(gemini) ok for uid={}", uid);
    Ok(MintResponse {
        provider: "gemini".to_string(),
        token,
        expires_at: Some(expire),
    })
}

pub fn realtime_routes() -> Router<AppState> {
    Router::new().route("/v2/realtime/session", post(mint_session))
}
