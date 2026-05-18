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

#[cfg(test)]
mod tests {
    use super::*;

    fn headers_with(pairs: &[(&str, &str)]) -> HeaderMap {
        let mut map = HeaderMap::new();
        for (k, v) in pairs {
            map.insert(
                axum::http::HeaderName::from_bytes(k.as_bytes()).unwrap(),
                v.parse().unwrap(),
            );
        }
        map
    }

    fn all_byok_headers() -> HeaderMap {
        headers_with(&[
            ("x-byok-openai", "sk-o"),
            ("x-byok-anthropic", "sk-a"),
            ("x-byok-gemini", "sk-g"),
            ("x-byok-deepgram", "sk-d"),
        ])
    }

    /// Verify that cache uses different keys for BYOK vs non-BYOK requests.
    /// A cached paywalled=true from a non-BYOK request must not block a
    /// subsequent BYOK request (which should get its own cache slot).
    #[tokio::test]
    async fn cache_partitioned_by_byok_presence() {
        // Use a nonexistent server — all Python calls will fail open (= false).
        let checker = PaywallChecker::new("http://127.0.0.1:1".to_string());

        let no_byok = HeaderMap::new();
        let with_byok = all_byok_headers();

        // First call: non-BYOK → fails open → cached as "user123" = false
        let result1 = checker.is_paywalled("user123", "token", &no_byok).await;
        assert!(!result1, "should fail open");

        // Second call: BYOK → should NOT hit the non-BYOK cache entry
        // (it should make its own call, also failing open, cached as "user123:byok")
        let result2 = checker.is_paywalled("user123", "token", &with_byok).await;
        assert!(!result2, "BYOK should fail open independently");

        // Verify both cache entries exist with different keys
        let cache = checker.cache.lock().await;
        assert!(cache.contains_key("user123"), "non-BYOK cache key");
        assert!(cache.contains_key("user123:byok"), "BYOK cache key");
        assert_eq!(cache.len(), 2, "should have separate cache entries");
    }

    /// Verify that partial BYOK headers (missing one) use the non-BYOK cache path.
    #[tokio::test]
    async fn partial_byok_uses_non_byok_cache() {
        let checker = PaywallChecker::new("http://127.0.0.1:1".to_string());

        // Missing deepgram → not all 4 → should use "uid" cache key
        let partial = headers_with(&[
            ("x-byok-openai", "sk-o"),
            ("x-byok-anthropic", "sk-a"),
            ("x-byok-gemini", "sk-g"),
        ]);

        checker.is_paywalled("user456", "token", &partial).await;

        let cache = checker.cache.lock().await;
        assert!(cache.contains_key("user456"), "partial BYOK should use non-BYOK key");
        assert!(!cache.contains_key("user456:byok"), "partial BYOK should NOT use BYOK key");
    }

    /// Verify that empty BYOK header values are not treated as present.
    #[tokio::test]
    async fn empty_byok_headers_use_non_byok_cache() {
        let checker = PaywallChecker::new("http://127.0.0.1:1".to_string());

        let empty_value = headers_with(&[
            ("x-byok-openai", "sk-o"),
            ("x-byok-anthropic", ""),
            ("x-byok-gemini", "sk-g"),
            ("x-byok-deepgram", "sk-d"),
        ]);

        checker.is_paywalled("user789", "token", &empty_value).await;

        let cache = checker.cache.lock().await;
        assert!(cache.contains_key("user789"), "empty BYOK value → non-BYOK key");
        assert!(!cache.contains_key("user789:byok"));
    }
}
