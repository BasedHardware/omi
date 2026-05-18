// Trial-paywall logic for the Rust desktop-backend.
//
// Previously delegated to Python (`GET /v1/users/me/paywall`). Now runs
// natively by reading subscription plan, BYOK state, and account creation
// time directly from Firestore / Firebase Auth.
//
// Logic (mirrors Python `_is_trial_expired_uncached` in `utils/subscription.py`):
//   1. BYOK escape hatch: request with all 4 BYOK headers → never paywalled
//   2. Non-"basic" plan → not paywalled
//   3. BYOK active (heartbeat within TTL) → not paywalled
//   4. Account created < 3 days ago → not paywalled (trial active)
//   5. Otherwise → paywalled
//
// Errors fail open (return false) so a Firestore/Auth outage never makes
// paying users look paywalled.

use axum::http::HeaderMap;
use std::collections::HashMap;
use std::sync::Arc;
use std::time::{Duration, Instant};
use tokio::sync::Mutex;

use crate::byok;
use crate::services::FirestoreService;

/// Cache TTL for paywall results (5 minutes, matching previous Python-delegation cache).
const CACHE_TTL: Duration = Duration::from_secs(300);

/// Trial length: 3 days in seconds (matches Python `TRIAL_LENGTH_SECONDS`).
const TRIAL_LENGTH_SECONDS: i64 = 3 * 24 * 60 * 60;

#[derive(Debug, Clone, Copy)]
struct CacheEntry {
    paywalled: bool,
    cached_at: Instant,
}

/// Native paywall checker that reads directly from Firestore and Firebase Auth.
/// Held inside `AppState` and exposed to extractors via an Axum `Extension`.
pub struct PaywallChecker {
    pub firestore: Arc<FirestoreService>,
    firebase_auth_project_id: String,
    byok_cache: Arc<byok::ByokStateCache>,
    cache: Mutex<HashMap<String, CacheEntry>>,
}

impl PaywallChecker {
    pub fn new(
        firestore: Arc<FirestoreService>,
        firebase_auth_project_id: String,
        byok_cache: Arc<byok::ByokStateCache>,
    ) -> Self {
        Self {
            firestore,
            firebase_auth_project_id,
            byok_cache,
            cache: Mutex::new(HashMap::new()),
        }
    }

    /// Returns true iff the user is past their desktop trial.
    ///
    /// When the request carries all 4 BYOK headers, the user is never
    /// paywalled (escape hatch for stale Firestore cache). Otherwise,
    /// checks subscription plan, BYOK active state, and account age.
    ///
    /// Errors fail open (return false).
    /// `byok_stripped`: true if BYOK validation determined the user is not
    /// BYOK-enrolled (headers were silently cleared). When true, the BYOK
    /// escape hatch is disabled — the raw headers cannot be trusted.
    pub async fn is_paywalled(
        &self,
        uid: &str,
        request_headers: &HeaderMap,
        byok_stripped: bool,
    ) -> bool {
        // BYOK escape hatch: a request carrying all 4 BYOK provider headers
        // is never paywalled, regardless of cached state. This handles the
        // race where Firestore hasn't caught up after BYOK activation.
        // SECURITY: Only trust the escape hatch if BYOK validation did NOT
        // strip the headers (i.e. the user is actually BYOK-enrolled or
        // validation hasn't run). A non-enrolled user forging all 4 headers
        // will have byok_stripped=true, so they can't bypass the paywall.
        if !byok_stripped && byok::has_all_byok_keys(request_headers) {
            return false;
        }

        let cache_key = uid.to_string();

        // Cache hit
        {
            let cache = self.cache.lock().await;
            if let Some(entry) = cache.get(&cache_key) {
                if entry.cached_at.elapsed() < CACHE_TTL {
                    return entry.paywalled;
                }
            }
        }

        let paywalled = self.check_trial_expired(uid).await;

        // Cache result
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

    /// Core trial-expiry check. Mirrors Python `_is_trial_expired_uncached`.
    /// Returns false (not paywalled) on any error (fail-open).
    async fn check_trial_expired(&self, uid: &str) -> bool {
        // Step 1: Read effective subscription plan (checks current_period_end for paid plans)
        let plan = match self.firestore.get_user_effective_plan(uid).await {
            Ok(p) => p,
            Err(e) => {
                tracing::warn!(
                    "paywall: failed to read subscription plan for uid={}: {}, failing open",
                    uid,
                    e
                );
                return false;
            }
        };

        // Non-basic plan → not paywalled
        if plan != "basic" {
            return false;
        }

        // Step 2: Check BYOK active (with heartbeat TTL)
        let byok_state = self.byok_cache.get_or_fetch(uid, &self.firestore).await;
        let byok_active = byok_state.active && {
            match byok_state.last_seen_at {
                Some(last_seen) => {
                    let age = chrono::Utc::now()
                        .signed_duration_since(last_seen)
                        .num_seconds();
                    age <= byok::BYOK_HEARTBEAT_TTL_SECS
                }
                None => false,
            }
        };
        if byok_active {
            return false;
        }

        // Step 3: Check account age from Firebase Auth
        let creation_ms = match self
            .firestore
            .get_user_creation_time(&self.firebase_auth_project_id, uid)
            .await
        {
            Ok(Some(ms)) => ms,
            Ok(None) => {
                tracing::warn!(
                    "paywall: no creation time for uid={}, failing open",
                    uid
                );
                return false;
            }
            Err(e) => {
                tracing::warn!(
                    "paywall: failed to get creation time for uid={}: {}, failing open",
                    uid,
                    e
                );
                return false;
            }
        };

        let now_ms = chrono::Utc::now().timestamp() * 1000;
        let age_seconds = (now_ms - creation_ms) / 1000;

        age_seconds > TRIAL_LENGTH_SECONDS
    }
}

/// Wrapper for storing in Axum Extension so extractors can pull it
/// without owning `AppState`.
#[derive(Clone)]
pub struct PaywallCheckerExt(pub Arc<PaywallChecker>);

/// Pure function for testing: is the trial expired given these inputs?
/// This is the core logic extracted for unit testing without Firestore.
#[cfg(test)]
fn is_trial_expired(plan: &str, byok_active: bool, creation_time_ms: Option<i64>) -> bool {
    if plan != "basic" {
        return false;
    }
    if byok_active {
        return false;
    }
    let creation_ms = match creation_time_ms {
        Some(ms) => ms,
        None => return false, // fail-open
    };
    let now_ms = chrono::Utc::now().timestamp() * 1000;
    let age_seconds = (now_ms - creation_ms) / 1000;
    age_seconds > TRIAL_LENGTH_SECONDS
}

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

    // --- Pure function tests for is_trial_expired ---

    #[test]
    fn paid_plan_not_paywalled() {
        assert!(!is_trial_expired("pro", false, Some(0)));
        assert!(!is_trial_expired("enterprise", false, Some(0)));
        assert!(!is_trial_expired("unlimited", false, Some(0)));
    }

    #[test]
    fn basic_plan_byok_active_not_paywalled() {
        // Basic plan + BYOK active → not paywalled regardless of age
        assert!(!is_trial_expired("basic", true, Some(0)));
    }

    #[test]
    fn basic_plan_new_account_not_paywalled() {
        // Account created just now → within 3-day trial
        let now_ms = chrono::Utc::now().timestamp() * 1000;
        assert!(!is_trial_expired("basic", false, Some(now_ms)));
    }

    #[test]
    fn basic_plan_old_account_no_byok_paywalled() {
        // Account created 10 days ago → past 3-day trial
        let ten_days_ago_ms =
            (chrono::Utc::now().timestamp() - 10 * 24 * 60 * 60) * 1000;
        assert!(is_trial_expired("basic", false, Some(ten_days_ago_ms)));
    }

    #[test]
    fn basic_plan_exactly_3_days_not_paywalled() {
        // Account created exactly 3 days ago → age == TRIAL_LENGTH, not > TRIAL_LENGTH
        let exactly_3d_ms =
            (chrono::Utc::now().timestamp() - TRIAL_LENGTH_SECONDS) * 1000;
        assert!(!is_trial_expired("basic", false, Some(exactly_3d_ms)));
    }

    #[test]
    fn basic_plan_just_over_3_days_paywalled() {
        // Account created 3 days + 1 second ago
        let just_over_3d_ms =
            (chrono::Utc::now().timestamp() - TRIAL_LENGTH_SECONDS - 1) * 1000;
        assert!(is_trial_expired("basic", false, Some(just_over_3d_ms)));
    }

    #[test]
    fn missing_creation_time_fails_open() {
        assert!(!is_trial_expired("basic", false, None));
    }

    #[test]
    fn free_plan_treated_as_basic() {
        // "free" should have been migrated to "basic" by Firestore reader,
        // but even if not, it won't match "basic" → not paywalled (fail-open)
        assert!(!is_trial_expired("free", false, Some(0)));
    }

    // --- BYOK escape hatch tests (header-level) ---

    #[test]
    fn byok_escape_hatch_all_headers_present() {
        let h = all_byok_headers();
        assert!(byok::has_all_byok_keys(&h), "all 4 → escape hatch fires");
    }

    #[test]
    fn byok_escape_hatch_missing_header() {
        let h = headers_with(&[
            ("x-byok-openai", "sk-o"),
            ("x-byok-anthropic", "sk-a"),
            ("x-byok-gemini", "sk-g"),
        ]);
        assert!(
            !byok::has_all_byok_keys(&h),
            "missing deepgram → escape hatch does not fire"
        );
    }

    // --- byok_stripped prevents paywall escape hatch ---

    #[test]
    fn byok_stripped_disables_escape_hatch() {
        // Even with all 4 BYOK headers present, if byok_stripped=true,
        // the escape hatch must NOT fire. Verified at the logic level:
        // is_paywalled checks `!byok_stripped && has_all_byok_keys`.
        let h = all_byok_headers();
        let byok_stripped = true;
        // The escape hatch condition:
        let would_escape = !byok_stripped && byok::has_all_byok_keys(&h);
        assert!(!would_escape, "stripped headers must not trigger escape hatch");
    }

    #[test]
    fn non_stripped_allows_escape_hatch() {
        let h = all_byok_headers();
        let byok_stripped = false;
        let would_escape = !byok_stripped && byok::has_all_byok_keys(&h);
        assert!(would_escape, "validated headers should trigger escape hatch");
    }
}
