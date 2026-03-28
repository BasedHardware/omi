// Gemini proxy rate limiter — tiered per-user daily limits with graceful degradation.
//
// Primary: Redis-backed (shared across instances via Lua script).
// Fallback: In-memory per-instance (when Redis unavailable).
//
// Tier 1 (Allow):   < DAILY_SOFT_LIMIT requests/day — Pro model allowed as-is
// Tier 2 (Degrade): DAILY_SOFT_LIMIT..DAILY_HARD_LIMIT — rewrite Pro → Flash
// Tier 3 (Reject):  > DAILY_HARD_LIMIT — return 429
// Burst cap:        > BURST_PER_MINUTE in rolling 60s window — return 429
//
// Issue #6098 L2.

use std::collections::{HashMap, VecDeque};
use std::sync::Arc;
use std::time::Instant;
use tokio::sync::Mutex;

use crate::services::RedisService;

/// Daily soft limit — above this, Pro requests are degraded to Flash.
const DAILY_SOFT_LIMIT: u32 = 300;

/// Daily hard limit — above this, all requests are rejected with 429.
const DAILY_HARD_LIMIT: u32 = 1500;

/// Burst cap — max requests per rolling 60-second window.
const BURST_PER_MINUTE: usize = 30;

/// Rolling window duration for burst detection (60 seconds).
const BURST_WINDOW_SECS: u64 = 60;

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

/// Snapshot of rate counters returned from Redis or in-memory.
struct RateSnapshot {
    daily_count: u32,
    burst_count: usize,
}

impl RateSnapshot {
    fn to_decision(&self) -> RateDecision {
        if self.burst_count > BURST_PER_MINUTE {
            RateDecision::Reject
        } else if self.daily_count >= DAILY_HARD_LIMIT {
            RateDecision::Reject
        } else if self.daily_count >= DAILY_SOFT_LIMIT {
            RateDecision::DegradeToFlash
        } else {
            RateDecision::Allow
        }
    }
}

/// Per-user rate state for in-memory fallback.
struct UserCounter {
    day_ordinal: i32,
    daily_count: u32,
    burst_window: VecDeque<Instant>,
}

impl UserCounter {
    fn new(day_ordinal: i32) -> Self {
        Self {
            day_ordinal,
            daily_count: 0,
            burst_window: VecDeque::with_capacity(BURST_PER_MINUTE + 1),
        }
    }
}

/// Hybrid Gemini rate limiter: Redis primary, in-memory fallback.
pub struct GeminiRateLimiter {
    /// In-memory counters (fallback when Redis unavailable).
    counters: Mutex<HashMap<String, UserCounter>>,
}

pub type SharedRateLimiter = Arc<GeminiRateLimiter>;

impl GeminiRateLimiter {
    pub fn new() -> SharedRateLimiter {
        Arc::new(Self {
            counters: Mutex::new(HashMap::new()),
        })
    }

    /// Check rate limit for a user and record the request.
    /// Tries Redis first; falls back to in-memory if Redis unavailable.
    pub async fn check_and_record(
        &self,
        uid: &str,
        redis: Option<&Arc<RedisService>>,
    ) -> RateDecision {
        // Try Redis first
        if let Some(redis) = redis {
            match redis.check_gemini_rate_limit(uid, BURST_PER_MINUTE, BURST_WINDOW_SECS).await {
                Ok((daily_count, burst_count)) => {
                    let snapshot = RateSnapshot {
                        daily_count: daily_count as u32,
                        burst_count: burst_count as usize,
                    };
                    return snapshot.to_decision();
                }
                Err(e) => {
                    // Log once at warn, fall through to in-memory
                    tracing::warn!("gemini rate limit: Redis unavailable, using in-memory fallback: {}", e);
                }
            }
        }

        // Fallback: in-memory per-instance limiting
        self.check_and_record_local(uid).await
    }

    /// In-memory rate limit check (fallback).
    async fn check_and_record_local(&self, uid: &str) -> RateDecision {
        let now = Instant::now();
        let today = current_day_ordinal();

        let mut counters = self.counters.lock().await;

        let counter = counters
            .entry(uid.to_string())
            .or_insert_with(|| UserCounter::new(today));

        // Reset if day changed
        if counter.day_ordinal != today {
            counter.day_ordinal = today;
            counter.daily_count = 0;
        }

        // Prune burst window
        let cutoff = now - std::time::Duration::from_secs(BURST_WINDOW_SECS);
        while counter
            .burst_window
            .front()
            .map_or(false, |&t| t < cutoff)
        {
            counter.burst_window.pop_front();
        }

        // Check burst cap first
        if counter.burst_window.len() >= BURST_PER_MINUTE {
            return RateDecision::Reject;
        }

        // Record request
        counter.burst_window.push_back(now);
        counter.daily_count += 1;

        let snapshot = RateSnapshot {
            daily_count: counter.daily_count,
            burst_count: counter.burst_window.len(),
        };
        snapshot.to_decision()
    }

    /// Evict stale in-memory entries.
    pub async fn evict_stale(&self) {
        let today = current_day_ordinal();
        let mut counters = self.counters.lock().await;
        counters.retain(|_, c| today - c.day_ordinal <= 2);
    }
}

/// Get current UTC day as ordinal (days since Unix epoch).
fn current_day_ordinal() -> i32 {
    (chrono::Utc::now().timestamp() / 86400) as i32
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
    if let Some(rest) = path.strip_prefix("models/gemini-pro-latest:") {
        return format!("models/gemini-3-flash-preview:{}", rest);
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

    // --- Decision from snapshot ---

    #[test]
    fn snapshot_allow() {
        let s = RateSnapshot { daily_count: 100, burst_count: 5 };
        assert_eq!(s.to_decision(), RateDecision::Allow);
    }

    #[test]
    fn snapshot_degrade_at_soft_limit() {
        let s = RateSnapshot { daily_count: 300, burst_count: 5 };
        assert_eq!(s.to_decision(), RateDecision::DegradeToFlash);
    }

    #[test]
    fn snapshot_reject_at_hard_limit() {
        let s = RateSnapshot { daily_count: 1500, burst_count: 5 };
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

    // --- In-memory fallback ---

    #[tokio::test]
    async fn local_tier1_allows() {
        let limiter = GeminiRateLimiter::new();
        {
            let mut counters = limiter.counters.lock().await;
            counters.insert("u1".to_string(), UserCounter {
                day_ordinal: current_day_ordinal(),
                daily_count: 298,
                burst_window: VecDeque::new(),
            });
        }
        // After increment: 299, which is < 300 (DAILY_SOFT_LIMIT)
        let decision = limiter.check_and_record_local("u1").await;
        assert_eq!(decision, RateDecision::Allow);
    }

    #[tokio::test]
    async fn local_tier2_degrades() {
        let limiter = GeminiRateLimiter::new();
        {
            let mut counters = limiter.counters.lock().await;
            counters.insert("u1".to_string(), UserCounter {
                day_ordinal: current_day_ordinal(),
                daily_count: 299,
                burst_window: VecDeque::new(),
            });
        }
        // After increment: 300, which is >= DAILY_SOFT_LIMIT
        let decision = limiter.check_and_record_local("u1").await;
        assert_eq!(decision, RateDecision::DegradeToFlash);
    }

    #[tokio::test]
    async fn local_tier3_rejects() {
        let limiter = GeminiRateLimiter::new();
        {
            let mut counters = limiter.counters.lock().await;
            counters.insert("u2".to_string(), UserCounter {
                day_ordinal: current_day_ordinal(),
                daily_count: 1499,
                burst_window: VecDeque::new(),
            });
        }
        // After increment: 1500, which is >= DAILY_HARD_LIMIT
        let decision = limiter.check_and_record_local("u2").await;
        assert_eq!(decision, RateDecision::Reject);
    }

    #[tokio::test]
    async fn local_burst_rejects() {
        let limiter = GeminiRateLimiter::new();
        for _ in 0..30 {
            let d = limiter.check_and_record_local("u3").await;
            assert_eq!(d, RateDecision::Allow);
        }
        let decision = limiter.check_and_record_local("u3").await;
        assert_eq!(decision, RateDecision::Reject);
    }

    #[tokio::test]
    async fn local_day_rollover() {
        let limiter = GeminiRateLimiter::new();
        {
            let mut counters = limiter.counters.lock().await;
            counters.insert("u4".to_string(), UserCounter {
                day_ordinal: current_day_ordinal() - 1,
                daily_count: 2000,
                burst_window: VecDeque::new(),
            });
        }
        let decision = limiter.check_and_record_local("u4").await;
        assert_eq!(decision, RateDecision::Allow);
    }

    #[tokio::test]
    async fn local_separate_users() {
        let limiter = GeminiRateLimiter::new();
        {
            let mut counters = limiter.counters.lock().await;
            counters.insert("uA".to_string(), UserCounter {
                day_ordinal: current_day_ordinal(),
                daily_count: 1500,
                burst_window: VecDeque::new(),
            });
        }
        let decision = limiter.check_and_record_local("uB").await;
        assert_eq!(decision, RateDecision::Allow);
    }

    #[tokio::test]
    async fn evict_stale_removes_old() {
        let limiter = GeminiRateLimiter::new();
        {
            let mut counters = limiter.counters.lock().await;
            counters.insert("old".to_string(), UserCounter {
                day_ordinal: current_day_ordinal() - 3,
                daily_count: 100,
                burst_window: VecDeque::new(),
            });
            counters.insert("recent".to_string(), UserCounter {
                day_ordinal: current_day_ordinal(),
                daily_count: 50,
                burst_window: VecDeque::new(),
            });
        }
        limiter.evict_stale().await;
        let counters = limiter.counters.lock().await;
        assert!(!counters.contains_key("old"));
        assert!(counters.contains_key("recent"));
    }

    // --- Hybrid: falls back when Redis is None ---

    #[tokio::test]
    async fn hybrid_no_redis_uses_local() {
        let limiter = GeminiRateLimiter::new();
        let decision = limiter.check_and_record("u5", None).await;
        assert_eq!(decision, RateDecision::Allow);
    }

    // --- Model path rewrite ---

    #[test]
    fn rewrite_pro_to_flash() {
        let r = maybe_rewrite_model_path(
            "models/gemini-pro-latest:generateContent",
            &RateDecision::DegradeToFlash,
            "generateContent",
        );
        assert_eq!(r, "models/gemini-3-flash-preview:generateContent");
    }

    #[test]
    fn no_rewrite_on_allow() {
        let r = maybe_rewrite_model_path(
            "models/gemini-pro-latest:generateContent",
            &RateDecision::Allow,
            "generateContent",
        );
        assert_eq!(r, "models/gemini-pro-latest:generateContent");
    }

    #[test]
    fn no_rewrite_embed() {
        let r = maybe_rewrite_model_path(
            "models/gemini-pro-latest:embedContent",
            &RateDecision::DegradeToFlash,
            "embedContent",
        );
        assert_eq!(r, "models/gemini-pro-latest:embedContent");
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
            "models/gemini-3-flash-preview:generateContent",
            &RateDecision::DegradeToFlash,
            "generateContent",
        );
        assert_eq!(r, "models/gemini-3-flash-preview:generateContent");
    }

    #[test]
    fn rewrite_pro_stream() {
        let r = maybe_rewrite_model_path(
            "models/gemini-pro-latest:streamGenerateContent",
            &RateDecision::DegradeToFlash,
            "streamGenerateContent",
        );
        assert_eq!(r, "models/gemini-3-flash-preview:streamGenerateContent");
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
