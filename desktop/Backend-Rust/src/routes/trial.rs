// Trial metadata route — proxies GET /v1/users/me/trial from Python and
// caches per-uid for 60 seconds. The Swift client polls this to render the
// countdown UI and pre-expiry nudges without hammering Python on every poll.

use axum::{extract::State, http::HeaderMap, routing::get, Json, Router};
use reqwest::Client;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::Arc;
use std::time::{Duration, Instant};
use tokio::sync::Mutex;

use crate::auth::AuthUser;
use crate::AppState;

const TRIAL_CACHE_TTL: Duration = Duration::from_secs(60);

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TrialMetadataResponse {
    pub trial_started_at: Option<i64>,
    pub trial_ends_at: Option<i64>,
    pub trial_remaining_seconds: i64,
    pub trial_expired: bool,
    pub trial_duration_seconds: i64,
    pub trial_features: Vec<String>,
    pub plan_after_trial: String,
}

#[derive(Debug, Clone)]
struct TrialCacheEntry {
    metadata: TrialMetadataResponse,
    cached_at: Instant,
}

/// In-memory trial metadata cache. Shorter TTL than paywall (60s vs 300s)
/// because countdown accuracy matters for the client UI.
pub struct TrialMetadataCache {
    python_api_base: String,
    http: Client,
    cache: Arc<Mutex<HashMap<String, TrialCacheEntry>>>,
}

impl TrialMetadataCache {
    pub fn new(python_api_base: String) -> Self {
        let http = Client::builder()
            .timeout(Duration::from_secs(5))
            .build()
            .unwrap_or_else(|_| Client::new());
        Self {
            python_api_base: python_api_base.trim_end_matches('/').to_string(),
            http,
            cache: Arc::new(Mutex::new(HashMap::new())),
        }
    }

    pub async fn get_trial_metadata(&self, uid: &str, bearer_token: &str) -> TrialMetadataResponse {
        // Cache hit
        {
            let cache = self.cache.lock().await;
            if let Some(entry) = cache.get(uid) {
                if entry.cached_at.elapsed() < TRIAL_CACHE_TTL {
                    return entry.metadata.clone();
                }
            }
        }

        let url = format!("{}/v1/users/me/trial", self.python_api_base);
        let response = self
            .http
            .get(&url)
            .header("Authorization", format!("Bearer {}", bearer_token))
            .send()
            .await;

        let metadata = match response {
            Ok(r) if r.status().is_success() => match r.json::<TrialMetadataResponse>().await {
                Ok(body) => body,
                Err(e) => {
                    tracing::warn!("trial: failed to parse response for uid={}: {}", uid, e);
                    Self::fail_open_response()
                }
            },
            Ok(r) => {
                tracing::warn!("trial: Python returned {} for uid={}", r.status(), uid);
                Self::fail_open_response()
            }
            Err(e) => {
                tracing::warn!("trial: Python call failed for uid={}: {}", uid, e);
                Self::fail_open_response()
            }
        };

        // Cache result
        let mut cache = self.cache.lock().await;
        cache.insert(
            uid.to_string(),
            TrialCacheEntry {
                metadata: metadata.clone(),
                cached_at: Instant::now(),
            },
        );

        metadata
    }

    /// Fail open: trial not expired, so user is never falsely blocked.
    fn fail_open_response() -> TrialMetadataResponse {
        TrialMetadataResponse {
            trial_started_at: None,
            trial_ends_at: None,
            trial_remaining_seconds: 0,
            trial_expired: false,
            trial_duration_seconds: 0,
            trial_features: vec![],
            plan_after_trial: "Free".to_string(),
        }
    }
}

/// GET /v1/trial — returns cached trial metadata for the authenticated user.
async fn get_trial(
    State(state): State<AppState>,
    headers: HeaderMap,
    user: AuthUser,
) -> Json<TrialMetadataResponse> {
    let token = headers
        .get("Authorization")
        .and_then(|h| h.to_str().ok())
        .and_then(|h| h.strip_prefix("Bearer "))
        .unwrap_or("");
    let metadata = state.trial_cache.get_trial_metadata(&user.uid, token).await;
    Json(metadata)
}

pub fn trial_routes() -> Router<AppState> {
    Router::new().route("/v1/trial", get(get_trial))
}
