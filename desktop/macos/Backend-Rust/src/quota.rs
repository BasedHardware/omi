// Monthly free-tier chat-quota gate for the Rust desktop-backend.
//
// The Python backend owns quota counting (`GET /v1/users/me/usage-quota`
// aggregates `users/{uid}/llm_usage/*` including legacy field layouts) and
// already 402-blocks free users past FREE_CHAT_QUESTIONS_PER_MONTH on
// `/v2/messages`. The Rust managed lanes (chat completions, realtime,
// agent ask, Gemini proxy, screen activity, TTS) previously checked only
// the trial paywall, so a free user past the monthly cap could keep
// spending managed LLM money through them.
//
// This checker asks the Python endpoint with the user's own bearer token
// (single source of truth — no duplicated counting logic) and blocks only
// when `plan_type == "basic" && allowed == false`. Paid plans are never
// blocked here (overage billing is the Python side's concern). BYOK-active
// users are exempted by the caller before this check runs.
//
// Errors fail open (allow) with a short TTL: an unreachable Python API must
// never lock paying-adjacent flows, and the blast radius of failing open is
// a few free questions.

use std::collections::HashMap;
use std::sync::Arc;
use std::time::{Duration, Instant};
use tokio::sync::Mutex;

use crate::fallback::{record_fallback, FallbackOutcome};

/// Cache TTL for an authoritative answer. Short enough that a user who just
/// hit the cap gets blocked within a minute, and an upgrade unblocks fast.
const CACHE_TTL: Duration = Duration::from_secs(60);

/// TTL for a fail-open decision made when the Python API was unreachable.
const FALLBACK_TTL: Duration = Duration::from_secs(30);

const REQUEST_TIMEOUT: Duration = Duration::from_secs(5);

/// Emergency kill switch: set CHAT_QUOTA_ENFORCEMENT_ENABLED=false to disable
/// the monthly-quota gate on all Rust managed lanes without a redeploy of logic.
fn enforcement_enabled() -> bool {
    !std::env::var("CHAT_QUOTA_ENFORCEMENT_ENABLED")
        .map(|v| v.eq_ignore_ascii_case("false"))
        .unwrap_or(false)
}

#[derive(Debug, Clone, Copy)]
struct CacheEntry {
    blocked: bool,
    expires_at: Instant,
}

pub struct ChatQuotaChecker {
    base_api_url: Option<String>,
    http: reqwest::Client,
    cache: Mutex<HashMap<String, CacheEntry>>,
}

impl ChatQuotaChecker {
    pub fn new(base_api_url: Option<String>) -> Self {
        Self {
            base_api_url,
            http: reqwest::Client::builder()
                .timeout(REQUEST_TIMEOUT)
                .build()
                .unwrap_or_default(),
            cache: Mutex::new(HashMap::new()),
        }
    }

    /// Returns true iff the user is a free-plan user past their monthly chat
    /// quota and must be blocked from managed AI lanes.
    ///
    /// `bearer_token` is the already-verified Firebase ID token from the
    /// request; it is forwarded so the Python endpoint authenticates the same
    /// user. Errors fail open (return false).
    pub async fn is_quota_blocked(&self, uid: &str, bearer_token: &str) -> bool {
        if !enforcement_enabled() {
            return false;
        }
        let Some(base) = self.base_api_url.as_deref() else {
            tracing::warn!("quota: BASE_API_URL not configured, failing open");
            return false;
        };

        let now = Instant::now();
        let stale: Option<bool> = {
            let cache = self.cache.lock().await;
            match cache.get(uid) {
                Some(entry) if entry.expires_at > now => return entry.blocked,
                Some(entry) => Some(entry.blocked),
                None => None,
            }
        };

        let (decision, ttl) = match self.fetch_quota_blocked(base, bearer_token).await {
            Some(blocked) => (blocked, CACHE_TTL),
            None => {
                // Fail open (prefer last-known-good): quota is a free-tier cost
                // cap, so a transient Python outage hands out at most a few free
                // questions rather than blocking every managed lane.
                let v = stale.unwrap_or(false);
                record_fallback(
                    "other",
                    "quota_gate",
                    "fail_open",
                    "quota",
                    FallbackOutcome::Degraded,
                );
                tracing::warn!(
                    "quota: indeterminate check for uid={}, using fallback={} (last_known_good={:?})",
                    uid,
                    v,
                    stale
                );
                (v, FALLBACK_TTL)
            }
        };

        let mut cache = self.cache.lock().await;
        cache.insert(
            uid.to_string(),
            CacheEntry {
                blocked: decision,
                expires_at: now + ttl,
            },
        );

        decision
    }

    /// Calls `GET /v1/users/me/usage-quota`. Returns:
    ///   - `Some(true)`  → free plan past cap (block)
    ///   - `Some(false)` → allowed (paid plan, under cap, or unlimited)
    ///   - `None`        → indeterminate (network/HTTP/parse failure)
    async fn fetch_quota_blocked(&self, base: &str, bearer_token: &str) -> Option<bool> {
        let url = format!("{}/v1/users/me/usage-quota", base.trim_end_matches('/'));
        let resp = self
            .http
            .get(&url)
            .header("Authorization", format!("Bearer {}", bearer_token))
            .header("X-App-Platform", "desktop")
            .send()
            .await
            .ok()?;
        if !resp.status().is_success() {
            tracing::warn!("quota: usage-quota returned {}", resp.status());
            return None;
        }
        let body: serde_json::Value = resp.json().await.ok()?;
        Some(quota_blocked_from_response(&body))
    }
}

/// Pure decision: block only free-plan (`basic`) users the server says are not
/// allowed. Paid plans past cap stay allowed (overage billing, Python-owned).
/// Missing/odd fields fail open.
fn quota_blocked_from_response(body: &serde_json::Value) -> bool {
    let plan_type = body.get("plan_type").and_then(|v| v.as_str()).unwrap_or("");
    let allowed = body
        .get("allowed")
        .and_then(|v| v.as_bool())
        .unwrap_or(true);
    plan_type == "basic" && !allowed
}

/// Wrapper for storing in Axum Extension so extractors can pull it
/// without owning `AppState`.
#[derive(Clone)]
pub struct ChatQuotaCheckerExt(pub Arc<ChatQuotaChecker>);

#[cfg(test)]
#[allow(clippy::unwrap_used)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn free_plan_past_cap_blocked() {
        let body = json!({"plan_type": "basic", "allowed": false});
        assert!(quota_blocked_from_response(&body));
    }

    #[test]
    fn free_plan_under_cap_allowed() {
        let body = json!({"plan_type": "basic", "allowed": true});
        assert!(!quota_blocked_from_response(&body));
    }

    #[test]
    fn paid_plans_never_blocked_even_past_cap() {
        for plan in ["unlimited", "operator", "architect"] {
            let body = json!({"plan_type": plan, "allowed": false});
            assert!(
                !quota_blocked_from_response(&body),
                "plan {} must not be blocked by the Rust gate",
                plan
            );
        }
    }

    #[test]
    fn missing_fields_fail_open() {
        assert!(!quota_blocked_from_response(&json!({})));
        assert!(!quota_blocked_from_response(&json!({"plan_type": "basic"})));
        assert!(!quota_blocked_from_response(&json!({"allowed": false})));
    }

    #[tokio::test]
    async fn no_base_url_fails_open() {
        let checker = ChatQuotaChecker::new(None);
        assert!(!checker.is_quota_blocked("uid1", "token").await);
    }
}
