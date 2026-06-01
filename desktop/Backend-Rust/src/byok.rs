// BYOK (Bring Your Own Keys) — header helpers, fingerprint validation, and state cache.
//
// Desktop Swift client sends X-BYOK-{OpenAI,Anthropic,Gemini,Deepgram} headers
// on every request via APIKeyService. These helpers extract, validate, and cache
// BYOK state from Firestore.
//
// Validation flow (mirrors Python `_check_byok_validity` in `backend/utils/byok.py`):
//   1. No BYOK headers → fast-path skip (no Firestore read)
//   2. User not BYOK-active (or heartbeat expired) → silently clear headers
//   3. User BYOK-active → SHA-256 hash each header, compare against enrolled fingerprints
//      → 403 on mismatch, proceed on match

use axum::http::HeaderMap;
use chrono::{DateTime, Utc};
use sha2::{Digest, Sha256};
use std::collections::HashMap;
use std::sync::Arc;
use std::time::{Duration, Instant};
use tokio::sync::Mutex;

use crate::services::FirestoreService;

/// Header names for each BYOK provider (case-insensitive in HTTP).
pub const HEADER_OPENAI: &str = "x-byok-openai";
pub const HEADER_ANTHROPIC: &str = "x-byok-anthropic";
pub const HEADER_GEMINI: &str = "x-byok-gemini";
pub const HEADER_DEEPGRAM: &str = "x-byok-deepgram";

/// All four required BYOK headers. Python's `_request_has_all_byok_keys()` checks
/// the same set — a fully enrolled BYOK user sends all four on every request.
const ALL_BYOK_HEADERS: &[&str] = &[
    HEADER_OPENAI,
    HEADER_ANTHROPIC,
    HEADER_GEMINI,
    HEADER_DEEPGRAM,
];

/// Map from header name to provider name (used for fingerprint lookup).
const HEADER_TO_PROVIDER: &[(&str, &str)] = &[
    (HEADER_OPENAI, "openai"),
    (HEADER_ANTHROPIC, "anthropic"),
    (HEADER_GEMINI, "gemini"),
    (HEADER_DEEPGRAM, "deepgram"),
];

/// Heartbeat TTL: BYOK is considered inactive if last_seen_at is older than this.
/// Matches Python's `BYOK_HEARTBEAT_TTL_SECONDS` in `database/users.py`.
pub const BYOK_HEARTBEAT_TTL_SECS: i64 = 7 * 24 * 60 * 60; // 7 days

/// Cache TTL for BYOK state from Firestore.
/// Matches Python's 30-second cache in `utils/byok.py`.
const BYOK_CACHE_TTL: Duration = Duration::from_secs(30);

/// Maximum cache entries (matches Python's `maxsize=1024`).
const BYOK_CACHE_MAX_ENTRIES: usize = 1024;

// ---------------------------------------------------------------------------
// Header extraction (unchanged from original)
// ---------------------------------------------------------------------------

/// Extract a single BYOK header value, trimmed and non-empty.
/// Returns `None` if the header is missing, empty, or whitespace-only.
pub fn get_byok_key<'a>(headers: &'a HeaderMap, header_name: &str) -> Option<&'a str> {
    headers
        .get(header_name)
        .and_then(|v| v.to_str().ok())
        .map(str::trim)
        .filter(|v| !v.is_empty())
}

/// Extract a BYOK key for a provider, respecting the `byok_stripped` flag.
///
/// When `byok_stripped` is true (non-enrolled user or expired heartbeat), returns
/// `None` regardless of header presence — forcing fallback to server-managed keys.
/// Route handlers should use this instead of calling `get_byok_key` directly.
pub fn get_byok_key_if_active<'a>(
    headers: &'a HeaderMap,
    header_name: &str,
    byok_stripped: bool,
) -> Option<&'a str> {
    if byok_stripped {
        None
    } else {
        get_byok_key(headers, header_name)
    }
}

/// True if the request carries non-empty values for all four BYOK provider headers.
///
/// This mirrors Python's `_request_has_all_byok_keys()`. Presence of all four
/// headers signals the user has fully enrolled BYOK keys. The paywall escape
/// hatch trusts presence here — fingerprint validation runs separately.
pub fn has_all_byok_keys(headers: &HeaderMap) -> bool {
    ALL_BYOK_HEADERS
        .iter()
        .all(|h| get_byok_key(headers, h).is_some())
}

// ---------------------------------------------------------------------------
// BYOK state from Firestore
// ---------------------------------------------------------------------------

/// BYOK enrollment state for a user, read from `users/{uid}.byok` in Firestore.
#[derive(Debug, Clone)]
pub struct ByokState {
    pub active: bool,
    /// Provider name → SHA-256 hex fingerprint of the enrolled key.
    pub fingerprints: HashMap<String, String>,
    pub last_seen_at: Option<DateTime<Utc>>,
}

impl Default for ByokState {
    fn default() -> Self {
        Self {
            active: false,
            fingerprints: HashMap::new(),
            last_seen_at: None,
        }
    }
}

// ---------------------------------------------------------------------------
// Validation result
// ---------------------------------------------------------------------------

/// Result of per-request BYOK validation.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ByokValidation {
    /// User is BYOK-active and all fingerprints match. Use the user's keys.
    Active,
    /// User is not BYOK-active (or no BYOK headers sent).
    /// `clear_headers`: if true, the request carried BYOK headers that should be
    /// silently ignored (non-enrolled user or expired heartbeat).
    Inactive { clear_headers: bool },
}

/// Validate BYOK headers against enrolled Firestore state.
///
/// This is a pure function — no I/O. The caller provides the `ByokState`
/// (typically from `ByokStateCache`).
///
/// Returns `Ok(ByokValidation)` on success, `Err(message)` on fingerprint
/// mismatch (caller should return HTTP 403).
pub fn validate_byok_request(
    _uid: &str,
    headers: &HeaderMap,
    state: &ByokState,
) -> Result<ByokValidation, String> {
    // Fast path: no BYOK headers on this request → nothing to validate.
    let has_any_byok = HEADER_TO_PROVIDER
        .iter()
        .any(|(h, _)| get_byok_key(headers, h).is_some());

    if !has_any_byok {
        return Ok(ByokValidation::Inactive {
            clear_headers: false,
        });
    }

    // Check if user is BYOK-active with valid heartbeat.
    let is_active = state.active && {
        match state.last_seen_at {
            Some(last_seen) => {
                let age = Utc::now()
                    .signed_duration_since(last_seen)
                    .num_seconds();
                age <= BYOK_HEARTBEAT_TTL_SECS
            }
            None => false,
        }
    };

    if !is_active {
        // Non-enrolled user (or expired heartbeat) sent BYOK headers.
        // Silently discard them so downstream code uses Omi's own keys.
        return Ok(ByokValidation::Inactive {
            clear_headers: true,
        });
    }

    // BYOK-active user with headers present — validate every enrolled
    // provider fingerprint.
    for (provider, stored_fp) in &state.fingerprints {
        // Find the header for this provider
        let header_name = HEADER_TO_PROVIDER
            .iter()
            .find(|(_, p)| p == provider)
            .map(|(h, _)| *h);

        let header_name = match header_name {
            Some(h) => h,
            None => continue, // Unknown provider in fingerprints — skip
        };

        let raw_key = match get_byok_key(headers, header_name) {
            Some(k) => k,
            None => {
                return Err(format!(
                    "BYOK key header missing for enrolled provider: {}",
                    provider
                ));
            }
        };

        let request_fp = hex::encode(Sha256::digest(raw_key.as_bytes()));
        if request_fp != *stored_fp {
            return Err(format!(
                "BYOK key fingerprint mismatch for provider: {}",
                provider
            ));
        }
    }

    Ok(ByokValidation::Active)
}

// ---------------------------------------------------------------------------
// In-memory cache for BYOK state (30s TTL, 1024 max entries)
// ---------------------------------------------------------------------------

struct CacheEntry {
    state: ByokState,
    cached_at: Instant,
}

/// In-memory cache for BYOK state fetched from Firestore.
/// Mirrors Python's `@lru_cache(maxsize=1024)` with 30-second TTL.
pub struct ByokStateCache {
    cache: Mutex<HashMap<String, CacheEntry>>,
}

impl ByokStateCache {
    pub fn new() -> Self {
        Self {
            cache: Mutex::new(HashMap::new()),
        }
    }

    /// Get BYOK state for a user, using cache if fresh (< 30s).
    /// On Firestore error, returns default inactive state (fail-open).
    pub async fn get_or_fetch(
        &self,
        uid: &str,
        firestore: &FirestoreService,
    ) -> ByokState {
        // Cache hit
        {
            let cache = self.cache.lock().await;
            if let Some(entry) = cache.get(uid) {
                if entry.cached_at.elapsed() < BYOK_CACHE_TTL {
                    return entry.state.clone();
                }
            }
        }

        // Cache miss or stale — fetch from Firestore
        let (state, should_cache) = match firestore.get_user_byok_state(uid).await {
            Ok(s) => (s, true),
            Err(e) => {
                // Fail open but do NOT cache the error-default. A transient
                // Firestore blip should not poison the cache and make an
                // active BYOK user look paywalled for 30 seconds.
                tracing::warn!(
                    "byok: failed to fetch BYOK state for uid={}: {}, failing open (not cached)",
                    uid,
                    e
                );
                return ByokState::default();
            }
        };

        // Store successful results in cache (evict oldest if at capacity)
        if should_cache {
            let mut cache = self.cache.lock().await;
            if cache.len() >= BYOK_CACHE_MAX_ENTRIES && !cache.contains_key(uid) {
                // Evict the oldest entry
                if let Some(oldest_key) = cache
                    .iter()
                    .min_by_key(|(_, v)| v.cached_at)
                    .map(|(k, _)| k.clone())
                {
                    cache.remove(&oldest_key);
                }
            }
            cache.insert(
                uid.to_string(),
                CacheEntry {
                    state: state.clone(),
                    cached_at: Instant::now(),
                },
            );
        }

        state
    }
}

/// Wrapper for storing ByokStateCache in Axum Extension.
#[derive(Clone)]
pub struct ByokCacheExt(pub Arc<ByokStateCache>);

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

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

    fn all_byok_headers_with_keys() -> HeaderMap {
        headers_with(&[
            ("x-byok-openai", "sk-o"),
            ("x-byok-anthropic", "sk-a"),
            ("x-byok-gemini", "sk-g"),
            ("x-byok-deepgram", "sk-d"),
        ])
    }

    fn fingerprints_for_keys() -> HashMap<String, String> {
        let mut fp = HashMap::new();
        fp.insert(
            "openai".to_string(),
            hex::encode(Sha256::digest(b"sk-o")),
        );
        fp.insert(
            "anthropic".to_string(),
            hex::encode(Sha256::digest(b"sk-a")),
        );
        fp.insert(
            "gemini".to_string(),
            hex::encode(Sha256::digest(b"sk-g")),
        );
        fp.insert(
            "deepgram".to_string(),
            hex::encode(Sha256::digest(b"sk-d")),
        );
        fp
    }

    fn active_state_with_fingerprints(fingerprints: HashMap<String, String>) -> ByokState {
        ByokState {
            active: true,
            fingerprints,
            last_seen_at: Some(Utc::now()),
        }
    }

    // --- Header extraction tests (unchanged) ---

    #[test]
    fn get_byok_key_present() {
        let h = headers_with(&[("x-byok-openai", "sk-test123")]);
        assert_eq!(get_byok_key(&h, HEADER_OPENAI), Some("sk-test123"));
    }

    #[test]
    fn get_byok_key_trimmed() {
        let h = headers_with(&[("x-byok-openai", "  sk-test  ")]);
        assert_eq!(get_byok_key(&h, HEADER_OPENAI), Some("sk-test"));
    }

    #[test]
    fn get_byok_key_empty() {
        let h = headers_with(&[("x-byok-openai", "")]);
        assert_eq!(get_byok_key(&h, HEADER_OPENAI), None);
    }

    #[test]
    fn get_byok_key_whitespace_only() {
        let h = headers_with(&[("x-byok-openai", "   ")]);
        assert_eq!(get_byok_key(&h, HEADER_OPENAI), None);
    }

    #[test]
    fn get_byok_key_missing() {
        let h = HeaderMap::new();
        assert_eq!(get_byok_key(&h, HEADER_OPENAI), None);
    }

    #[test]
    fn has_all_byok_keys_all_present() {
        let h = all_byok_headers_with_keys();
        assert!(has_all_byok_keys(&h));
    }

    #[test]
    fn has_all_byok_keys_missing_one() {
        let h = headers_with(&[
            ("x-byok-openai", "sk-o"),
            ("x-byok-anthropic", "sk-a"),
            ("x-byok-gemini", "sk-g"),
        ]);
        assert!(!has_all_byok_keys(&h));
    }

    #[test]
    fn has_all_byok_keys_one_empty() {
        let h = headers_with(&[
            ("x-byok-openai", "sk-o"),
            ("x-byok-anthropic", ""),
            ("x-byok-gemini", "sk-g"),
            ("x-byok-deepgram", "sk-d"),
        ]);
        assert!(!has_all_byok_keys(&h));
    }

    #[test]
    fn has_all_byok_keys_none() {
        let h = HeaderMap::new();
        assert!(!has_all_byok_keys(&h));
    }

    // --- Fingerprint validation tests ---

    #[test]
    fn fingerprint_sha256_matches_known_value() {
        let fp = hex::encode(Sha256::digest(b"sk-test123"));
        assert_eq!(
            fp,
            "bc372bdb48322359f05049dcf298b69067d926cd9f0aa42bb0660de7970b7e29"
        );
    }

    #[test]
    fn validate_active_byok_valid_fingerprints() {
        let state = active_state_with_fingerprints(fingerprints_for_keys());
        let headers = all_byok_headers_with_keys();
        let result = validate_byok_request("uid", &headers, &state);
        assert_eq!(result, Ok(ByokValidation::Active));
    }

    #[test]
    fn validate_active_byok_mismatched_fingerprint() {
        let mut fp = fingerprints_for_keys();
        fp.insert("openai".to_string(), "wrong_fingerprint".to_string());
        let state = active_state_with_fingerprints(fp);
        let headers = all_byok_headers_with_keys();
        let result = validate_byok_request("uid", &headers, &state);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("mismatch"));
    }

    #[test]
    fn validate_non_byok_user_with_headers_strips() {
        let state = ByokState::default();
        let headers = all_byok_headers_with_keys();
        let result = validate_byok_request("uid", &headers, &state);
        assert_eq!(
            result,
            Ok(ByokValidation::Inactive {
                clear_headers: true
            })
        );
    }

    #[test]
    fn validate_no_headers_no_action() {
        let state = ByokState::default();
        let headers = HeaderMap::new();
        let result = validate_byok_request("uid", &headers, &state);
        assert_eq!(
            result,
            Ok(ByokValidation::Inactive {
                clear_headers: false
            })
        );
    }

    #[test]
    fn validate_expired_heartbeat_strips() {
        let state = ByokState {
            active: true,
            fingerprints: fingerprints_for_keys(),
            last_seen_at: Some(Utc::now() - chrono::Duration::days(8)),
        };
        let headers = all_byok_headers_with_keys();
        let result = validate_byok_request("uid", &headers, &state);
        assert_eq!(
            result,
            Ok(ByokValidation::Inactive {
                clear_headers: true
            })
        );
    }

    #[test]
    fn validate_missing_enrolled_provider_header() {
        // BYOK-active user enrolled for all 4 but request only has openai
        let state = active_state_with_fingerprints(fingerprints_for_keys());
        let headers = headers_with(&[("x-byok-openai", "sk-o")]);
        let result = validate_byok_request("uid", &headers, &state);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("missing"));
    }

    #[test]
    fn validate_active_byok_no_headers_no_error() {
        // BYOK-active user sends no headers — not an error, just no BYOK for this request
        let state = active_state_with_fingerprints(fingerprints_for_keys());
        let headers = HeaderMap::new();
        let result = validate_byok_request("uid", &headers, &state);
        assert_eq!(
            result,
            Ok(ByokValidation::Inactive {
                clear_headers: false
            })
        );
    }

    #[test]
    fn validate_heartbeat_within_ttl_valid() {
        // Heartbeat 6 days ago — still within 7-day TTL
        let state = ByokState {
            active: true,
            fingerprints: fingerprints_for_keys(),
            last_seen_at: Some(Utc::now() - chrono::Duration::days(6)),
        };
        let headers = all_byok_headers_with_keys();
        let result = validate_byok_request("uid", &headers, &state);
        assert_eq!(result, Ok(ByokValidation::Active));
    }

    #[test]
    fn validate_active_no_last_seen_strips() {
        // Active flag but no last_seen_at — treat as expired heartbeat
        let state = ByokState {
            active: true,
            fingerprints: fingerprints_for_keys(),
            last_seen_at: None,
        };
        let headers = all_byok_headers_with_keys();
        let result = validate_byok_request("uid", &headers, &state);
        assert_eq!(
            result,
            Ok(ByokValidation::Inactive {
                clear_headers: true
            })
        );
    }

    // --- Edge cases: empty / partial fingerprints ---

    #[test]
    fn validate_active_byok_empty_fingerprints() {
        // Active BYOK user with empty fingerprint map — all headers pass
        // (no enrolled fingerprints to check against)
        let state = ByokState {
            active: true,
            fingerprints: HashMap::new(),
            last_seen_at: Some(Utc::now()),
        };
        let headers = all_byok_headers_with_keys();
        let result = validate_byok_request("uid", &headers, &state);
        assert_eq!(result, Ok(ByokValidation::Active));
    }

    #[test]
    fn validate_active_byok_partial_enrollment() {
        // Active BYOK user enrolled for only openai + gemini.
        // Request sends all 4 headers — validates only the 2 enrolled.
        let mut fp = HashMap::new();
        fp.insert("openai".to_string(), hex::encode(Sha256::digest(b"sk-o")));
        fp.insert("gemini".to_string(), hex::encode(Sha256::digest(b"sk-g")));
        let state = active_state_with_fingerprints(fp);
        let headers = all_byok_headers_with_keys();
        let result = validate_byok_request("uid", &headers, &state);
        assert_eq!(result, Ok(ByokValidation::Active));
    }

    #[test]
    fn validate_active_byok_partial_enrollment_mismatch() {
        // Active BYOK user enrolled for openai + gemini, but request sends
        // wrong key for gemini → mismatch even though anthropic/deepgram are ok
        let mut fp = HashMap::new();
        fp.insert("openai".to_string(), hex::encode(Sha256::digest(b"sk-o")));
        fp.insert("gemini".to_string(), hex::encode(Sha256::digest(b"WRONG")));
        let state = active_state_with_fingerprints(fp);
        let headers = all_byok_headers_with_keys();
        let result = validate_byok_request("uid", &headers, &state);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("gemini"));
    }

    #[test]
    fn validate_active_byok_partial_headers_match_enrollment() {
        // Active user enrolled for only openai. Request sends only openai header.
        // Should pass — the one enrolled fingerprint matches.
        let mut fp = HashMap::new();
        fp.insert("openai".to_string(), hex::encode(Sha256::digest(b"sk-o")));
        let state = active_state_with_fingerprints(fp);
        let headers = headers_with(&[("x-byok-openai", "sk-o")]);
        let result = validate_byok_request("uid", &headers, &state);
        assert_eq!(result, Ok(ByokValidation::Active));
    }

    #[test]
    fn validate_active_byok_unknown_provider_in_fingerprints_skipped() {
        // Fingerprints contain a provider not in HEADER_TO_PROVIDER — should be skipped
        let mut fp = fingerprints_for_keys();
        fp.insert("unknown_provider".to_string(), "deadbeef".to_string());
        let state = active_state_with_fingerprints(fp);
        let headers = all_byok_headers_with_keys();
        let result = validate_byok_request("uid", &headers, &state);
        assert_eq!(result, Ok(ByokValidation::Active));
    }

    #[test]
    fn validate_heartbeat_exactly_at_ttl_boundary() {
        // Heartbeat exactly at 7 days (604800 seconds) — should still be valid (<=)
        let state = ByokState {
            active: true,
            fingerprints: fingerprints_for_keys(),
            last_seen_at: Some(Utc::now() - chrono::Duration::seconds(BYOK_HEARTBEAT_TTL_SECS)),
        };
        let headers = all_byok_headers_with_keys();
        let result = validate_byok_request("uid", &headers, &state);
        assert_eq!(result, Ok(ByokValidation::Active));
    }

    #[test]
    fn validate_heartbeat_one_second_past_ttl() {
        // Heartbeat at 7 days + 1 second — should be expired
        let state = ByokState {
            active: true,
            fingerprints: fingerprints_for_keys(),
            last_seen_at: Some(
                Utc::now() - chrono::Duration::seconds(BYOK_HEARTBEAT_TTL_SECS + 1),
            ),
        };
        let headers = all_byok_headers_with_keys();
        let result = validate_byok_request("uid", &headers, &state);
        assert_eq!(
            result,
            Ok(ByokValidation::Inactive {
                clear_headers: true
            })
        );
    }

    // --- get_byok_key_if_active tests (used by route handlers) ---

    #[test]
    fn key_if_active_stripped_returns_none() {
        // byok_stripped=true → always returns None, even if header is present
        let h = headers_with(&[("x-byok-gemini", "sk-real-key")]);
        assert_eq!(get_byok_key_if_active(&h, HEADER_GEMINI, true), None);
    }

    #[test]
    fn key_if_active_not_stripped_returns_key() {
        // byok_stripped=false → returns the header value
        let h = headers_with(&[("x-byok-gemini", "sk-real-key")]);
        assert_eq!(
            get_byok_key_if_active(&h, HEADER_GEMINI, false),
            Some("sk-real-key")
        );
    }

    #[test]
    fn key_if_active_not_stripped_missing_header_returns_none() {
        // byok_stripped=false but header missing → None (natural fallback)
        let h = HeaderMap::new();
        assert_eq!(get_byok_key_if_active(&h, HEADER_GEMINI, false), None);
    }

    #[test]
    fn key_if_active_all_providers_stripped() {
        // Verify all 4 provider headers are blocked when stripped
        let h = all_byok_headers_with_keys();
        assert_eq!(get_byok_key_if_active(&h, HEADER_OPENAI, true), None);
        assert_eq!(get_byok_key_if_active(&h, HEADER_ANTHROPIC, true), None);
        assert_eq!(get_byok_key_if_active(&h, HEADER_GEMINI, true), None);
        assert_eq!(get_byok_key_if_active(&h, HEADER_DEEPGRAM, true), None);
    }

    #[test]
    fn key_if_active_all_providers_not_stripped() {
        // Verify all 4 provider headers are returned when not stripped
        let h = all_byok_headers_with_keys();
        assert_eq!(
            get_byok_key_if_active(&h, HEADER_OPENAI, false),
            Some("sk-o")
        );
        assert_eq!(
            get_byok_key_if_active(&h, HEADER_ANTHROPIC, false),
            Some("sk-a")
        );
        assert_eq!(
            get_byok_key_if_active(&h, HEADER_GEMINI, false),
            Some("sk-g")
        );
        assert_eq!(
            get_byok_key_if_active(&h, HEADER_DEEPGRAM, false),
            Some("sk-d")
        );
    }
}
