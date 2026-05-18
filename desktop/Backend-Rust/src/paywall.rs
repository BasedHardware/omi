// Trial-paywall middleware for the Rust desktop-backend.
//
// Delegates the decision to Python (`GET /v1/users/me/paywall`) which owns
// the canonical paywall logic (basic plan + no BYOK + Firebase account >3d
// old + platform=macos/desktop). We cache the boolean per-uid in-memory for
// 5 minutes so chat / proxy / TTS / screen-activity calls don't fan out to
// Python on every request.
//
// Mobile is not a concern here — the Rust desktop-backend is only ever
// called by the macOS Swift client, so every paywall check goes in with
// `X-App-Platform: macos`. Python `is_trial_paywalled` enforces the
// platform gate; if it ever returns `paywalled=true` for an iOS / Android
// caller (which can't happen via this code path), this layer would still
// return 402 — but that situation cannot arise from real traffic.

use axum::http::HeaderMap;
use reqwest::Client;
use serde::Deserialize;
use std::collections::HashMap;
use std::sync::Arc;
use std::time::{Duration, Instant};
use tokio::sync::Mutex;

use crate::byok;

const CACHE_TTL: Duration = Duration::from_secs(300);

#[derive(Debug, Clone, Copy)]
struct CacheEntry {
    paywalled: bool,
    cached_at: Instant,
}

#[derive(Deserialize)]
struct PaywallStatus {
    paywalled: bool,
}

/// Singleton helper that calls Python's `/v1/users/me/paywall` and caches
/// the result in-memory. Held inside `AppState` and exposed to extractors
/// via an Axum `Extension`.
pub struct PaywallChecker {
    python_api_base: String,
    http: Client,
    cache: Arc<Mutex<HashMap<String, CacheEntry>>>,
}

impl PaywallChecker {
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

    /// Returns true iff the user is past their desktop trial. Errors fail
    /// open (return false) so a Python outage never makes paying users
    /// look paywalled.
    ///
    /// When the request carries all 4 BYOK headers, they are forwarded to
    /// Python so its `_request_has_all_byok_keys()` escape hatch can fire.
    /// BYOK requests use a separate cache key (`uid:byok`) so a BYOK=false
    /// result never poisons later non-BYOK lookups and vice versa.
    pub async fn is_paywalled(
        &self,
        uid: &str,
        bearer_token: &str,
        request_headers: &HeaderMap,
    ) -> bool {
        let has_byok = byok::has_all_byok_keys(request_headers);

        // Partition cache: "uid" for non-BYOK, "uid:byok" for BYOK requests.
        // Without this, a cached paywalled=true from a non-BYOK request would
        // block a subsequent BYOK request that should pass Python's escape hatch.
        let cache_key = if has_byok {
            format!("{}:byok", uid)
        } else {
            uid.to_string()
        };

        // Cache hit
        {
            let cache = self.cache.lock().await;
            if let Some(entry) = cache.get(&cache_key) {
                if entry.cached_at.elapsed() < CACHE_TTL {
                    return entry.paywalled;
                }
            }
        }

        let url = format!("{}/v1/users/me/paywall", self.python_api_base);
        let mut req = self
            .http
            .get(&url)
            .header("Authorization", format!("Bearer {}", bearer_token))
            .header("X-App-Platform", "macos");

        // Forward BYOK headers so Python's escape hatch can fire (issue #7357).
        if has_byok {
            for header_name in &[
                byok::HEADER_OPENAI,
                byok::HEADER_ANTHROPIC,
                byok::HEADER_GEMINI,
                byok::HEADER_DEEPGRAM,
            ] {
                if let Some(value) = byok::get_byok_key(request_headers, header_name) {
                    req = req.header(*header_name, value);
                }
            }
        }

        let response = req.send().await;

        let paywalled = match response {
            Ok(r) if r.status().is_success() => match r.json::<PaywallStatus>().await {
                Ok(body) => body.paywalled,
                Err(e) => {
                    tracing::warn!(
                        "paywall: failed to parse Python response for uid={}: {}",
                        uid,
                        e
                    );
                    false
                }
            },
            Ok(r) => {
                tracing::warn!(
                    "paywall: Python returned {} for uid={}, failing open",
                    r.status(),
                    uid
                );
                false
            }
            Err(e) => {
                tracing::warn!("paywall: Python call failed for uid={}: {}", uid, e);
                false
            }
        };

        // Cache (even false results — limits Python load when many requests
        // arrive in quick succession for the same uid)
        let mut cache = self.cache.lock().await;
        cache.insert(
            cache_key,
            CacheEntry {
                paywalled,
                cached_at: Instant::now(),
            },
        );

        paywalled
    }
}

/// Wrapper for storing in Axum Extension so extractors can pull it
/// without owning `AppState`.
#[derive(Clone)]
pub struct PaywallCheckerExt(pub Arc<PaywallChecker>);
