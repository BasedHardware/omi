// Gemini proxy rate limiter — tiered per-user daily limits with graceful degradation.
//
// Source of truth: Redis (shared across all instances via Lua script).
// Local cache: Reduces Redis calls by caching recent decisions per user.
//              NOT a fallback — if Redis is unavailable, requests pass through unmetered.
//
// Tier 1 (Allow):   < DAILY_SOFT_LIMIT requests/day — Pro model allowed as-is
// Tier 2 (Degrade): DAILY_SOFT_LIMIT..DAILY_HARD_LIMIT — rewrite Pro → Flash
// Tier 3 (Reject):  >= DAILY_HARD_LIMIT — return 429
// Burst cap:        >= BURST_PER_MINUTE in rolling 60s window — return 429
//
// Cache strategy (conservative — only cache rejections):
//   Only Reject decisions are cached (TTL 30s) to skip Redis for blocked users.
//   Allow and Degrade always call Redis so every request is recorded in shared counters.
//   Local burst tracking provides fast per-instance rejection without Redis.
//
// Issue #6098 L2.

use std::collections::{HashMap, VecDeque};
use std::sync::Arc;
use std::time::{Duration, Instant};
use tokio::sync::Mutex;

use crate::services::RedisService;

// Daily soft/hard limits are tier-aware — see crate::llm::model_qos.
use crate::llm::model_qos;

/// Burst cap — max requests per rolling 60-second window.
const BURST_PER_MINUTE: usize = 30;

/// Rolling window duration for burst detection (60 seconds).
const BURST_WINDOW_SECS: u64 = 60;

/// Cache TTL for Reject decisions (blocked users — skip Redis for this window).
/// Allow/Degrade are never cached so every request is recorded in Redis.
const CACHE_TTL_REJECT_SECS: u64 = 30;

/// Rate limit decision for a single request.
#[derive(Debug, Clone, PartialEq)]
pub enum RateDecision {
    /// Under daily soft limit — allow request as-is.
    Allow,
    /// Over daily soft limit but under hard limit — rewrite Pro model to Flash.
    DegradeToFlash,
    /// Over daily hard limit or burst cap exceeded.
    Reject,
}

/// Snapshot of rate counters returned from Redis.
struct RateSnapshot {
    daily_count: u32,
    burst_count: usize,
}

impl RateSnapshot {
    fn to_decision(&self) -> RateDecision {
        if self.burst_count > BURST_PER_MINUTE {
            RateDecision::Reject
        } else if self.daily_count >= model_qos::daily_hard_limit() {
            RateDecision::Reject
        } else if self.daily_count >= model_qos::daily_soft_limit() {
            RateDecision::DegradeToFlash
        } else {
            RateDecision::Allow
        }
    }
}

/// Per-user cached rate state (reduces Redis calls).
struct CachedEntry {
    /// Last decision from Redis.
    decision: RateDecision,
    /// When this cache entry expires (must re-check Redis).
    expires_at: Instant,
    /// Local burst window for fast per-instance rejection.
    local_burst: VecDeque<Instant>,
}

/// Gemini rate limiter: Redis source of truth, local cache to reduce Redis calls.
pub struct GeminiRateLimiter {
    /// Per-user cache of recent Redis decisions + local burst tracking.
    cache: Mutex<HashMap<String, CachedEntry>>,
}

pub type SharedRateLimiter = Arc<GeminiRateLimiter>;

impl GeminiRateLimiter {
    pub fn new() -> SharedRateLimiter {
        Arc::new(Self {
            cache: Mutex::new(HashMap::new()),
        })
    }

    /// Check rate limit for a user and record the request.
    ///
    /// 1. No Redis configured → allow unmetered (no cache, no local enforcement).
    /// 2. Local burst >= cap → reject without Redis (conservative, safe).
    /// 3. Cached Reject still fresh → reject without Redis (user already blocked).
    /// 4. All other cases → call Redis (ensures every request is recorded).
    pub async fn check_and_record(
        &self,
        uid: &str,
        redis: Option<&Arc<RedisService>>,
    ) -> RateDecision {
        // Phase 1: No Redis → unmetered (skip cache entirely)
        let Some(redis) = redis else {
            tracing::warn!("gemini rate limit: Redis not configured, request unmetered");
            return RateDecision::Allow;
        };

        let now = Instant::now();
        let burst_cutoff = now - Duration::from_secs(BURST_WINDOW_SECS);

        // Phase 2: Fast-path local checks (conservative rejections only)
        {
            let mut cache = self.cache.lock().await;
            if let Some(entry) = cache.get_mut(uid) {
                // Prune stale burst entries
                while entry.local_burst.front().map_or(false, |&t| t < burst_cutoff) {
                    entry.local_burst.pop_front();
                }

                // Fast reject on local burst (this instance alone has seen >= cap)
                if entry.local_burst.len() >= BURST_PER_MINUTE {
                    return RateDecision::Reject;
                }

                // Cached Reject still fresh → skip Redis (user is blocked)
                if entry.decision == RateDecision::Reject && now < entry.expires_at {
                    entry.local_burst.push_back(now);
                    return RateDecision::Reject;
                }
            }
        }

        // Phase 3: Call Redis (source of truth — records the request)
        match redis.check_gemini_rate_limit(uid, BURST_PER_MINUTE, BURST_WINDOW_SECS).await {
            Ok((daily_count, burst_count)) => {
                let snapshot = RateSnapshot {
                    daily_count: daily_count as u32,
                    burst_count: burst_count as usize,
                };
                let decision = snapshot.to_decision();

                let mut cache = self.cache.lock().await;
                let entry = cache.entry(uid.to_string()).or_insert_with(|| CachedEntry {
                    decision: RateDecision::Allow,
                    expires_at: now,
                    local_burst: VecDeque::with_capacity(BURST_PER_MINUTE + 1),
                });

                // Only cache Reject decisions (Allow/Degrade always go to Redis)
                entry.decision = decision.clone();
                if decision == RateDecision::Reject {
                    entry.expires_at = now + Duration::from_secs(CACHE_TTL_REJECT_SECS);
                } else {
                    // Mark expired so next request always hits Redis
                    entry.expires_at = now;
                }

                // Track burst locally
                while entry.local_burst.front().map_or(false, |&t| t < burst_cutoff) {
                    entry.local_burst.pop_front();
                }
                entry.local_burst.push_back(now);

                decision
            }
            Err(e) => {
                tracing::error!("gemini rate limit: Redis error, request unmetered: {}", e);
                RateDecision::Allow
            }
        }
    }

    /// Evict expired cache entries (called periodically from background task).
    pub async fn evict_stale(&self) {
        let now = Instant::now();
        let mut cache = self.cache.lock().await;
        // Remove entries whose cache expired more than 5 minutes ago
        let stale_cutoff = now - Duration::from_secs(300);
        cache.retain(|_, entry| entry.expires_at > stale_cutoff);
    }
}

/// Rewrite a Gemini model path from Pro to Flash if the decision is DegradeToFlash.
/// Embedding actions are exempt from rewrite (Flash is not a drop-in for embedding models).
pub fn maybe_rewrite_model_path(path: &str, decision: &RateDecision, action: &str) -> String {
    if !matches!(decision, RateDecision::DegradeToFlash) {
        return path.to_string();
    }
    if action == "embedContent" || action == "batchEmbedContents" {
        return path.to_string();
    }
    // Degrade any non-flash model to the flash degrade target.
    // Extract the model from "models/{model}:{action}" and check if it's already the target.
    let degrade_target = crate::llm::model_qos::gemini_degrade_target();
    if let Some(rest) = path.strip_prefix("models/") {
        if let Some((model, action_part)) = rest.split_once(':') {
            if model != degrade_target {
                return format!("models/{}:{}", degrade_target, action_part);
            }
        }
    }
    path.to_string()
}

/// Build a Gemini-compatible 429 JSON error response body.
pub fn rate_limit_error_json(message: &str) -> String {
    serde_json::json!({
        "error": {
            "message": message,
            "code": 429,
            "status": "RESOURCE_EXHAUSTED"
        }
    })
    .to_string()
}

#[cfg(test)]
mod tests {
    use super::*;

    // --- Decision from snapshot (uses QoS tier — Premium in test env: soft=30, hard=1500) ---

    #[test]
    fn snapshot_allow() {
        let s = RateSnapshot { daily_count: 10, burst_count: 5 };
        assert_eq!(s.to_decision(), RateDecision::Allow);
    }

    #[test]
    fn snapshot_degrade_at_soft_limit() {
        let soft = model_qos::daily_soft_limit();
        let s = RateSnapshot { daily_count: soft, burst_count: 5 };
        assert_eq!(s.to_decision(), RateDecision::DegradeToFlash);
    }

    #[test]
    fn snapshot_reject_at_hard_limit() {
        let hard = model_qos::daily_hard_limit();
        let s = RateSnapshot { daily_count: hard, burst_count: 5 };
        assert_eq!(s.to_decision(), RateDecision::Reject);
    }

    #[test]
    fn snapshot_reject_burst() {
        let s = RateSnapshot { daily_count: 10, burst_count: 31 };
        assert_eq!(s.to_decision(), RateDecision::Reject);
    }

    #[test]
    fn snapshot_burst_at_exact_limit() {
        // burst_count == BURST_PER_MINUTE is not over (it's the count AFTER add)
        let s = RateSnapshot { daily_count: 10, burst_count: 30 };
        assert_eq!(s.to_decision(), RateDecision::Allow);
    }

    // --- Boundary: just below thresholds ---

    #[test]
    fn snapshot_allow_just_below_soft_limit() {
        let soft = model_qos::daily_soft_limit();
        let s = RateSnapshot { daily_count: soft - 1, burst_count: 5 };
        assert_eq!(s.to_decision(), RateDecision::Allow);
    }

    #[test]
    fn snapshot_degrade_just_below_hard_limit() {
        let hard = model_qos::daily_hard_limit();
        let s = RateSnapshot { daily_count: hard - 1, burst_count: 5 };
        assert_eq!(s.to_decision(), RateDecision::DegradeToFlash);
    }

    // --- No Redis → unmetered (cache bypassed entirely) ---

    #[tokio::test]
    async fn no_redis_allows_unmetered() {
        let limiter = GeminiRateLimiter::new();
        let decision = limiter.check_and_record("u1", None).await;
        assert_eq!(decision, RateDecision::Allow);
    }

    #[tokio::test]
    async fn no_redis_ignores_cached_reject() {
        // Cached Reject must NOT fire when Redis is None
        let limiter = GeminiRateLimiter::new();
        {
            let mut cache = limiter.cache.lock().await;
            cache.insert("u2".to_string(), CachedEntry {
                decision: RateDecision::Reject,
                expires_at: Instant::now() + Duration::from_secs(60),
                local_burst: VecDeque::new(),
            });
        }
        let decision = limiter.check_and_record("u2", None).await;
        assert_eq!(decision, RateDecision::Allow);
    }

    #[tokio::test]
    async fn no_redis_ignores_cached_degrade() {
        // Cached Degrade must NOT fire when Redis is None
        let limiter = GeminiRateLimiter::new();
        {
            let mut cache = limiter.cache.lock().await;
            cache.insert("u3".to_string(), CachedEntry {
                decision: RateDecision::DegradeToFlash,
                expires_at: Instant::now() + Duration::from_secs(60),
                local_burst: VecDeque::new(),
            });
        }
        let decision = limiter.check_and_record("u3", None).await;
        assert_eq!(decision, RateDecision::Allow);
    }

    #[tokio::test]
    async fn no_redis_ignores_local_burst() {
        // Full local burst must NOT fire when Redis is None
        let limiter = GeminiRateLimiter::new();
        {
            let mut cache = limiter.cache.lock().await;
            let mut burst = VecDeque::new();
            let now = Instant::now();
            for i in 0..30 {
                burst.push_back(now - Duration::from_millis(i * 100));
            }
            cache.insert("u4".to_string(), CachedEntry {
                decision: RateDecision::Allow,
                expires_at: now,
                local_burst: burst,
            });
        }
        let decision = limiter.check_and_record("u4", None).await;
        assert_eq!(decision, RateDecision::Allow);
    }

    // --- Expired Reject cache falls through to Redis ---

    #[tokio::test]
    async fn expired_reject_cache_falls_through() {
        let limiter = GeminiRateLimiter::new();
        {
            let mut cache = limiter.cache.lock().await;
            cache.insert("u5".to_string(), CachedEntry {
                decision: RateDecision::Reject,
                expires_at: Instant::now() - Duration::from_secs(1),
                local_burst: VecDeque::new(),
            });
        }
        // No Redis → falls through to unmetered Allow
        let decision = limiter.check_and_record("u5", None).await;
        assert_eq!(decision, RateDecision::Allow);
    }

    // --- Separate users don't interfere ---

    #[tokio::test]
    async fn separate_users() {
        let limiter = GeminiRateLimiter::new();
        {
            let mut cache = limiter.cache.lock().await;
            cache.insert("uA".to_string(), CachedEntry {
                decision: RateDecision::Reject,
                expires_at: Instant::now() + Duration::from_secs(60),
                local_burst: VecDeque::new(),
            });
        }
        // uB has no Redis → unmetered Allow
        let decision = limiter.check_and_record("uB", None).await;
        assert_eq!(decision, RateDecision::Allow);
    }

    // --- Evict stale ---

    #[tokio::test]
    async fn evict_stale_removes_old() {
        let limiter = GeminiRateLimiter::new();
        {
            let mut cache = limiter.cache.lock().await;
            cache.insert("old".to_string(), CachedEntry {
                decision: RateDecision::Allow,
                // Expired 10 minutes ago (> 5 min stale cutoff)
                expires_at: Instant::now() - Duration::from_secs(600),
                local_burst: VecDeque::new(),
            });
            cache.insert("recent".to_string(), CachedEntry {
                decision: RateDecision::Allow,
                expires_at: Instant::now() + Duration::from_secs(60),
                local_burst: VecDeque::new(),
            });
        }
        limiter.evict_stale().await;
        let cache = limiter.cache.lock().await;
        assert!(!cache.contains_key("old"));
        assert!(cache.contains_key("recent"));
    }

    // --- Model path rewrite ---

    #[test]
    fn rewrite_pro_to_flash() {
        let r = maybe_rewrite_model_path(
            "models/gemini-2.5-pro:generateContent",
            &RateDecision::DegradeToFlash,
            "generateContent",
        );
        assert_eq!(r, "models/gemini-2.5-flash:generateContent");
    }

    #[test]
    fn no_rewrite_on_allow() {
        let r = maybe_rewrite_model_path(
            "models/gemini-2.5-pro:generateContent",
            &RateDecision::Allow,
            "generateContent",
        );
        assert_eq!(r, "models/gemini-2.5-pro:generateContent");
    }

    #[test]
    fn no_rewrite_embed() {
        let r = maybe_rewrite_model_path(
            "models/gemini-2.5-pro:embedContent",
            &RateDecision::DegradeToFlash,
            "embedContent",
        );
        assert_eq!(r, "models/gemini-2.5-pro:embedContent");
    }

    #[test]
    fn no_rewrite_batch_embed() {
        let r = maybe_rewrite_model_path(
            "models/gemini-embedding-001:batchEmbedContents",
            &RateDecision::DegradeToFlash,
            "batchEmbedContents",
        );
        assert_eq!(r, "models/gemini-embedding-001:batchEmbedContents");
    }

    #[test]
    fn no_rewrite_flash_model() {
        let r = maybe_rewrite_model_path(
            "models/gemini-2.5-flash:generateContent",
            &RateDecision::DegradeToFlash,
            "generateContent",
        );
        assert_eq!(r, "models/gemini-2.5-flash:generateContent");
    }

    #[test]
    fn rewrite_pro_stream() {
        let r = maybe_rewrite_model_path(
            "models/gemini-2.5-pro:streamGenerateContent",
            &RateDecision::DegradeToFlash,
            "streamGenerateContent",
        );
        assert_eq!(r, "models/gemini-2.5-flash:streamGenerateContent");
    }

    // --- 429 error JSON ---

    #[test]
    fn error_json_format() {
        let json = rate_limit_error_json(
            "Resource exhausted: rate limit exceeded. Please try again later.",
        );
        let parsed: serde_json::Value = serde_json::from_str(&json).unwrap();
        assert_eq!(parsed["error"]["code"], 429);
        assert_eq!(parsed["error"]["status"], "RESOURCE_EXHAUSTED");
        let msg = parsed["error"]["message"].as_str().unwrap();
        assert!(msg.to_lowercase().contains("resource exhausted"));
    }
}
