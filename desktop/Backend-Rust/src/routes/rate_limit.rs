// Gemini proxy rate limiter — tiered per-user daily limits with graceful degradation.
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

/// Per-user rate state for a single UTC day.
struct UserCounter {
    /// UTC date ordinal (days since epoch) for this counter.
    day_ordinal: i32,
    /// Total requests today.
    daily_count: u32,
    /// Rolling window of recent request timestamps for burst detection.
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

/// In-memory Gemini rate limiter. Thread-safe via Arc<Mutex<>>.
pub struct GeminiRateLimiter {
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
    /// Returns the decision (Allow / DegradeToFlash / Reject).
    pub async fn check_and_record(&self, uid: &str) -> RateDecision {
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
            // Don't clear burst window — it spans seconds, not days
        }

        // Prune burst window: remove entries older than 60s
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

        // Determine tier
        if counter.daily_count > DAILY_HARD_LIMIT {
            RateDecision::Reject
        } else if counter.daily_count > DAILY_SOFT_LIMIT {
            RateDecision::DegradeToFlash
        } else {
            RateDecision::Allow
        }
    }

    /// Evict stale entries (users inactive for >48h worth of day changes).
    /// Called periodically from a background task.
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
    // Embedding requests are exempt from model rewrite
    if action == "embedContent" || action == "batchEmbedContents" {
        return path.to_string();
    }
    // Only rewrite exact gemini-pro-latest model
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

    // --- RateDecision thresholds ---
    // Tests set up counters directly to avoid burst cap interference.

    #[tokio::test]
    async fn tier1_allows_under_soft_limit() {
        let limiter = GeminiRateLimiter::new();

        // Set counter at 299 (just under soft limit)
        {
            let mut counters = limiter.counters.lock().await;
            counters.insert(
                "user1".to_string(),
                UserCounter {
                    day_ordinal: current_day_ordinal(),
                    daily_count: 299,
                    burst_window: VecDeque::new(),
                },
            );
        }

        // Request 300 should still be Allow
        let decision = limiter.check_and_record("user1").await;
        assert_eq!(decision, RateDecision::Allow);
    }

    #[tokio::test]
    async fn tier2_degrades_at_soft_limit() {
        let limiter = GeminiRateLimiter::new();

        // Set counter at exactly soft limit
        {
            let mut counters = limiter.counters.lock().await;
            counters.insert(
                "user1".to_string(),
                UserCounter {
                    day_ordinal: current_day_ordinal(),
                    daily_count: 300,
                    burst_window: VecDeque::new(),
                },
            );
        }

        // Request 301 should degrade
        let decision = limiter.check_and_record("user1").await;
        assert_eq!(decision, RateDecision::DegradeToFlash);
    }

    #[tokio::test]
    async fn tier2_degrades_between_soft_and_hard() {
        let limiter = GeminiRateLimiter::new();

        // Set counter midway between soft and hard limit
        {
            let mut counters = limiter.counters.lock().await;
            counters.insert(
                "user1".to_string(),
                UserCounter {
                    day_ordinal: current_day_ordinal(),
                    daily_count: 900,
                    burst_window: VecDeque::new(),
                },
            );
        }

        let decision = limiter.check_and_record("user1").await;
        assert_eq!(decision, RateDecision::DegradeToFlash);
    }

    #[tokio::test]
    async fn tier3_rejects_over_hard_limit() {
        let limiter = GeminiRateLimiter::new();

        // Set counter at hard limit
        {
            let mut counters = limiter.counters.lock().await;
            counters.insert(
                "user2".to_string(),
                UserCounter {
                    day_ordinal: current_day_ordinal(),
                    daily_count: 1500,
                    burst_window: VecDeque::new(),
                },
            );
        }

        let decision = limiter.check_and_record("user2").await;
        assert_eq!(decision, RateDecision::Reject);
    }

    #[tokio::test]
    async fn burst_cap_rejects_at_limit() {
        let limiter = GeminiRateLimiter::new();
        // Fill burst window
        for _ in 0..30 {
            let d = limiter.check_and_record("user3").await;
            assert_eq!(d, RateDecision::Allow);
        }
        // 31st should be rejected
        let decision = limiter.check_and_record("user3").await;
        assert_eq!(decision, RateDecision::Reject);
    }

    #[tokio::test]
    async fn day_rollover_resets_daily_count() {
        let limiter = GeminiRateLimiter::new();

        // Set counter to yesterday with high count
        {
            let mut counters = limiter.counters.lock().await;
            counters.insert(
                "user4".to_string(),
                UserCounter {
                    day_ordinal: current_day_ordinal() - 1,
                    daily_count: 2000,
                    burst_window: VecDeque::new(),
                },
            );
        }

        // Should reset to day 1 and allow
        let decision = limiter.check_and_record("user4").await;
        assert_eq!(decision, RateDecision::Allow);

        // Verify count was reset
        let counters = limiter.counters.lock().await;
        assert_eq!(counters["user4"].daily_count, 1);
    }

    #[tokio::test]
    async fn separate_users_independent() {
        let limiter = GeminiRateLimiter::new();
        // Fill user A to soft limit
        for _ in 1..=300 {
            limiter.check_and_record("userA").await;
        }
        // User B should still be in Tier 1
        let decision = limiter.check_and_record("userB").await;
        assert_eq!(decision, RateDecision::Allow);
    }

    #[tokio::test]
    async fn evict_stale_removes_old_entries() {
        let limiter = GeminiRateLimiter::new();

        // Add a counter from 3 days ago
        {
            let mut counters = limiter.counters.lock().await;
            counters.insert(
                "old_user".to_string(),
                UserCounter {
                    day_ordinal: current_day_ordinal() - 3,
                    daily_count: 100,
                    burst_window: VecDeque::new(),
                },
            );
            counters.insert(
                "recent_user".to_string(),
                UserCounter {
                    day_ordinal: current_day_ordinal(),
                    daily_count: 50,
                    burst_window: VecDeque::new(),
                },
            );
        }

        limiter.evict_stale().await;

        let counters = limiter.counters.lock().await;
        assert!(!counters.contains_key("old_user"));
        assert!(counters.contains_key("recent_user"));
    }

    // --- Model path rewrite ---

    #[test]
    fn rewrite_pro_to_flash_on_degrade() {
        let result = maybe_rewrite_model_path(
            "models/gemini-pro-latest:generateContent",
            &RateDecision::DegradeToFlash,
            "generateContent",
        );
        assert_eq!(result, "models/gemini-3-flash-preview:generateContent");
    }

    #[test]
    fn no_rewrite_on_allow() {
        let result = maybe_rewrite_model_path(
            "models/gemini-pro-latest:generateContent",
            &RateDecision::Allow,
            "generateContent",
        );
        assert_eq!(result, "models/gemini-pro-latest:generateContent");
    }

    #[test]
    fn no_rewrite_for_embed_content() {
        let result = maybe_rewrite_model_path(
            "models/gemini-pro-latest:embedContent",
            &RateDecision::DegradeToFlash,
            "embedContent",
        );
        assert_eq!(result, "models/gemini-pro-latest:embedContent");
    }

    #[test]
    fn no_rewrite_for_batch_embed() {
        let result = maybe_rewrite_model_path(
            "models/gemini-embedding-001:batchEmbedContents",
            &RateDecision::DegradeToFlash,
            "batchEmbedContents",
        );
        assert_eq!(
            result,
            "models/gemini-embedding-001:batchEmbedContents"
        );
    }

    #[test]
    fn no_rewrite_for_flash_model() {
        let result = maybe_rewrite_model_path(
            "models/gemini-3-flash-preview:generateContent",
            &RateDecision::DegradeToFlash,
            "generateContent",
        );
        // Flash model path doesn't start with "models/gemini-pro-latest:"
        assert_eq!(result, "models/gemini-3-flash-preview:generateContent");
    }

    #[test]
    fn rewrite_pro_stream() {
        let result = maybe_rewrite_model_path(
            "models/gemini-pro-latest:streamGenerateContent",
            &RateDecision::DegradeToFlash,
            "streamGenerateContent",
        );
        assert_eq!(
            result,
            "models/gemini-3-flash-preview:streamGenerateContent"
        );
    }

    // --- 429 error JSON ---

    #[test]
    fn rate_limit_error_json_format() {
        let json =
            rate_limit_error_json("Resource exhausted: rate limit exceeded. Please try again later.");
        let parsed: serde_json::Value = serde_json::from_str(&json).unwrap();
        assert_eq!(parsed["error"]["code"], 429);
        assert_eq!(parsed["error"]["status"], "RESOURCE_EXHAUSTED");
        // Message must contain "resource exhausted" for Swift GeminiClient retry detection
        let msg = parsed["error"]["message"].as_str().unwrap();
        assert!(msg.to_lowercase().contains("resource exhausted"));
    }
}
