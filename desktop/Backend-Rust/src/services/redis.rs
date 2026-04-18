// Redis service for conversation visibility
// Mirrors the Python backend's redis_db.py functionality for sharing conversations

use redis::{AsyncCommands, Client, ConnectionAddr, ConnectionInfo, RedisConnectionInfo};
use std::sync::Arc;
use tokio::sync::RwLock;

/// Redis service for conversation visibility and sharing
pub struct RedisService {
    client: Client,
    connection: Arc<RwLock<Option<redis::aio::MultiplexedConnection>>>,
}

/// Review data stored in Redis
#[derive(Debug, Clone)]
pub struct RedisReview {
    pub score: i32,
}

impl RedisService {
    /// Create a new Redis service with explicit connection parameters
    /// This avoids URL encoding issues with special characters in passwords
    pub fn new_with_params(host: &str, port: u16, password: Option<&str>) -> Result<Self, redis::RedisError> {
        let info = ConnectionInfo {
            addr: ConnectionAddr::Tcp(host.to_string(), port),
            redis: RedisConnectionInfo {
                db: 0,
                username: Some("default".to_string()),
                password: password.map(|p| p.to_string()),
            },
        };
        let client = Client::open(info)?;
        Ok(Self {
            client,
            connection: Arc::new(RwLock::new(None)),
        })
    }

    /// Create a new Redis service from URL (legacy, may have encoding issues)
    pub fn new(redis_url: &str) -> Result<Self, redis::RedisError> {
        let client = Client::open(redis_url)?;
        Ok(Self {
            client,
            connection: Arc::new(RwLock::new(None)),
        })
    }

    /// Get or create a connection
    async fn get_connection(&self) -> Result<redis::aio::MultiplexedConnection, redis::RedisError> {
        // Check if we have a cached connection
        {
            let conn = self.connection.read().await;
            if let Some(c) = conn.as_ref() {
                return Ok(c.clone());
            }
        }

        // Create new connection
        let conn = self.client.get_multiplexed_async_connection().await?;

        // Cache it
        {
            let mut cached = self.connection.write().await;
            *cached = Some(conn.clone());
        }

        Ok(conn)
    }

    // ============================================================================
    // CONVERSATION VISIBILITY - matches Python backend redis_db.py
    // ============================================================================

    /// Store conversation_id -> uid mapping for visibility lookup
    /// Key format: memories-visibility:{conversation_id}
    pub async fn store_conversation_to_uid(
        &self,
        conversation_id: &str,
        uid: &str,
    ) -> Result<(), redis::RedisError> {
        let mut conn = self.get_connection().await?;
        let key = format!("memories-visibility:{}", conversation_id);
        let _: () = conn.set(&key, uid).await?;
        tracing::info!("Stored conversation visibility: {} -> {}", conversation_id, uid);
        Ok(())
    }

    /// Remove conversation_id -> uid mapping
    pub async fn remove_conversation_to_uid(
        &self,
        conversation_id: &str,
    ) -> Result<(), redis::RedisError> {
        let mut conn = self.get_connection().await?;
        let key = format!("memories-visibility:{}", conversation_id);
        let _: () = conn.del(&key).await?;
        tracing::info!("Removed conversation visibility: {}", conversation_id);
        Ok(())
    }

    /// Get the uid that owns a public conversation
    /// Returns None if conversation is not public/shared
    pub async fn get_conversation_uid(
        &self,
        conversation_id: &str,
    ) -> Result<Option<String>, redis::RedisError> {
        let mut conn = self.get_connection().await?;
        let key = format!("memories-visibility:{}", conversation_id);
        let uid: Option<String> = conn.get(&key).await?;
        Ok(uid)
    }

    /// Add conversation to the public conversations set
    /// Key: public-memories (SET)
    pub async fn add_public_conversation(
        &self,
        conversation_id: &str,
    ) -> Result<(), redis::RedisError> {
        let mut conn = self.get_connection().await?;
        let _: () = conn.sadd("public-memories", conversation_id).await?;
        tracing::info!("Added conversation to public set: {}", conversation_id);
        Ok(())
    }

    /// Remove conversation from the public conversations set
    pub async fn remove_public_conversation(
        &self,
        conversation_id: &str,
    ) -> Result<(), redis::RedisError> {
        let mut conn = self.get_connection().await?;
        let _: () = conn.srem("public-memories", conversation_id).await?;
        tracing::info!("Removed conversation from public set: {}", conversation_id);
        Ok(())
    }

    /// Get all public conversation IDs
    pub async fn get_public_conversations(&self) -> Result<Vec<String>, redis::RedisError> {
        let mut conn = self.get_connection().await?;
        let ids: Vec<String> = conn.smembers("public-memories").await?;
        Ok(ids)
    }

    /// Check if Redis connection is healthy
    pub async fn health_check(&self) -> Result<bool, redis::RedisError> {
        let mut conn = self.get_connection().await?;
        let pong: String = redis::cmd("PING").query_async(&mut conn).await?;
        Ok(pong == "PONG")
    }

    // ============================================================================
    // TASK SHARING
    // ============================================================================

    /// Store task share data in Redis with 30-day TTL
    /// Key format: task_share:{token}
    pub async fn store_task_share(
        &self,
        token: &str,
        uid: &str,
        display_name: &str,
        task_ids: &[String],
    ) -> Result<(), redis::RedisError> {
        let mut conn = self.get_connection().await?;
        let key = format!("task_share:{}", token);
        let value = serde_json::json!({
            "uid": uid,
            "display_name": display_name,
            "task_ids": task_ids,
        });
        let _: () = conn.set_ex(&key, value.to_string(), 30 * 24 * 60 * 60).await?;
        tracing::info!("Stored task share: {} -> {} tasks", token, task_ids.len());
        Ok(())
    }

    /// Get task share data from Redis
    /// Returns (uid, display_name, task_ids) or None if expired/missing
    pub async fn get_task_share(
        &self,
        token: &str,
    ) -> Result<Option<(String, String, Vec<String>)>, redis::RedisError> {
        let mut conn = self.get_connection().await?;
        let key = format!("task_share:{}", token);
        let raw: Option<String> = conn.get(&key).await?;
        match raw {
            Some(data) => {
                if let Ok(parsed) = serde_json::from_str::<serde_json::Value>(&data) {
                    let uid = parsed["uid"].as_str().unwrap_or("").to_string();
                    let display_name = parsed["display_name"].as_str().unwrap_or("").to_string();
                    let task_ids: Vec<String> = parsed["task_ids"]
                        .as_array()
                        .map(|arr| arr.iter().filter_map(|v| v.as_str().map(String::from)).collect())
                        .unwrap_or_default();
                    Ok(Some((uid, display_name, task_ids)))
                } else {
                    Ok(None)
                }
            }
            None => Ok(None),
        }
    }

    /// Atomically try to accept a task share for a user
    /// Returns true if this is a new acceptance, false if already accepted
    pub async fn try_accept_task_share(
        &self,
        token: &str,
        uid: &str,
    ) -> Result<bool, redis::RedisError> {
        let mut conn = self.get_connection().await?;
        let key = format!("task_share:{}:accepted", token);
        let added: i32 = conn.sadd(&key, uid).await?;
        // Set 30-day TTL on the accepted set
        let _: () = conn.expire(&key, 30 * 24 * 60 * 60).await?;
        Ok(added == 1)
    }

    // ============================================================================
    // GEMINI RATE LIMITING — atomic burst + daily counters via Lua
    // Issue #6098 L2
    // ============================================================================

    /// Check and record a Gemini API request for rate limiting.
    /// Uses a Lua script for atomic burst (sorted set) + daily (counter) in one round-trip.
    /// Returns (daily_count, burst_count) so the caller can decide Allow/Degrade/Reject.
    pub async fn check_gemini_rate_limit(
        &self,
        uid: &str,
        _burst_limit: usize,
        burst_window_secs: u64,
    ) -> Result<(i64, i64), redis::RedisError> {
        let mut conn = self.get_connection().await?;

        let now_ms = chrono::Utc::now().timestamp_millis();
        let day_ordinal = (now_ms / 86_400_000).to_string();
        let cutoff_ms = now_ms - (burst_window_secs as i64 * 1000);

        let burst_key = format!("gemini_rl:{}:burst", uid);
        let daily_key = format!("gemini_rl:{}:daily:{}", uid, day_ordinal);

        // Lua script: increment daily first (for unique member), prune burst, add, count.
        // KEYS[1] = burst_key, KEYS[2] = daily_key
        // ARGV[1] = cutoff_ms, ARGV[2] = now_ms, ARGV[3] = burst_ttl, ARGV[4] = daily_ttl
        //
        // The daily counter doubles as a nonce for the burst sorted set member.
        // Without it, concurrent requests in the same millisecond would overwrite the
        // same member (score=now_ms, member=now_ms) and ZCARD would undercount.
        let script = r#"
local daily = redis.call('INCR', KEYS[2])
redis.call('EXPIRE', KEYS[2], ARGV[4])
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', ARGV[1])
redis.call('ZADD', KEYS[1], ARGV[2], ARGV[2] .. ':' .. tostring(daily))
local burst = redis.call('ZCARD', KEYS[1])
redis.call('EXPIRE', KEYS[1], ARGV[3])
return {daily, burst}
"#;

        let burst_ttl = (burst_window_secs * 2) as i64; // 2x window for safety
        let daily_ttl: i64 = 172_800; // 48h

        let result: Vec<i64> = redis::cmd("EVAL")
            .arg(script)
            .arg(2) // num keys
            .arg(&burst_key)
            .arg(&daily_key)
            .arg(cutoff_ms)
            .arg(now_ms)
            .arg(burst_ttl)
            .arg(daily_ttl)
            .query_async(&mut conn)
            .await?;

        let daily_count = result.first().copied().unwrap_or(0);
        let burst_count = result.get(1).copied().unwrap_or(0);

        Ok((daily_count, burst_count))
    }

    // ============================================================================
    // TTS (ElevenLabs) RATE LIMITING - issue #6622
    // ============================================================================

    /// Check and record a TTS request for rate limiting.
    /// Tracks burst (requests/minute) and daily character usage in one Lua script.
    /// Returns TtsRateResult indicating whether the request is allowed.
    pub async fn check_tts_rate_limit(
        &self,
        uid: &str,
        burst_limit: i64,
        burst_window_secs: u64,
        char_count: i64,
        daily_char_limit: i64,
    ) -> Result<crate::routes::tts::TtsRateResult, redis::RedisError> {
        let mut conn = self.get_connection().await?;

        let now_ms = chrono::Utc::now().timestamp_millis();
        let day_ordinal = (now_ms / 86_400_000).to_string();
        let cutoff_ms = now_ms - (burst_window_secs as i64 * 1000);

        let burst_key = format!("tts_rl:{}:burst", uid);
        let daily_chars_key = format!("tts_rl:{}:chars:{}", uid, day_ordinal);

        // Lua script: atomic burst + daily char check and record.
        // KEYS[1] = burst_key, KEYS[2] = daily_chars_key
        // ARGV[1] = cutoff_ms, ARGV[2] = now_ms, ARGV[3] = burst_ttl
        // ARGV[4] = daily_ttl, ARGV[5] = char_count, ARGV[6] = burst_limit, ARGV[7] = daily_char_limit
        //
        // Returns {burst_count, daily_chars, 0=allow/1=burst_exceeded/2=chars_exceeded}
        let script = r#"
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', ARGV[1])
local burst = redis.call('ZCARD', KEYS[1])
if burst >= tonumber(ARGV[6]) then
    return {burst, 0, 1}
end
local daily_chars = tonumber(redis.call('GET', KEYS[2]) or '0')
if daily_chars + tonumber(ARGV[5]) > tonumber(ARGV[7]) then
    return {burst, daily_chars, 2}
end
redis.call('ZADD', KEYS[1], ARGV[2], ARGV[2] .. ':' .. tostring(burst))
redis.call('EXPIRE', KEYS[1], ARGV[3])
redis.call('INCRBY', KEYS[2], ARGV[5])
redis.call('EXPIRE', KEYS[2], ARGV[4])
local new_chars = tonumber(redis.call('GET', KEYS[2]) or '0')
return {burst + 1, new_chars, 0}
"#;

        let burst_ttl = (burst_window_secs * 2) as i64;
        let daily_ttl: i64 = 172_800; // 48h

        let result: Vec<i64> = redis::cmd("EVAL")
            .arg(script)
            .arg(2)
            .arg(&burst_key)
            .arg(&daily_chars_key)
            .arg(cutoff_ms)
            .arg(now_ms)
            .arg(burst_ttl)
            .arg(daily_ttl)
            .arg(char_count)
            .arg(burst_limit)
            .arg(daily_char_limit)
            .query_async(&mut conn)
            .await?;

        let decision = result.get(2).copied().unwrap_or(0);
        match decision {
            1 => Ok(crate::routes::tts::TtsRateResult::BurstExceeded),
            2 => Ok(crate::routes::tts::TtsRateResult::DailyCharsExceeded),
            _ => Ok(crate::routes::tts::TtsRateResult::Allow),
        }
    }

    // ============================================================================
    // APP INSTALLS - matches Python backend redis_db.py
    // ============================================================================

    /// Get installs count for multiple apps
    /// Key format: plugins:{app_id}:installs
    /// Returns a HashMap of app_id -> installs count
    pub async fn get_apps_installs_count(
        &self,
        app_ids: &[String],
    ) -> Result<std::collections::HashMap<String, i32>, redis::RedisError> {
        if app_ids.is_empty() {
            return Ok(std::collections::HashMap::new());
        }

        let mut conn = self.get_connection().await?;
        let keys: Vec<String> = app_ids
            .iter()
            .map(|id| format!("plugins:{}:installs", id))
            .collect();

        let counts: Vec<Option<String>> = conn.mget(&keys).await?;

        let result: std::collections::HashMap<String, i32> = app_ids
            .iter()
            .zip(counts.iter())
            .map(|(id, count)| {
                let installs = count
                    .as_ref()
                    .and_then(|s| s.parse::<i32>().ok())
                    .unwrap_or(0);
                (id.clone(), installs)
            })
            .collect();

        Ok(result)
    }

    // ============================================================================
    // APP REVIEWS - matches Python backend redis_db.py
    // ============================================================================

    /// Get reviews for multiple apps
    /// Key format: plugins:{app_id}:reviews
    /// Returns a HashMap of app_id -> HashMap of uid -> review
    /// Python stores reviews as: {uid: {score: int, review: str, ...}}
    pub async fn get_apps_reviews(
        &self,
        app_ids: &[String],
    ) -> Result<std::collections::HashMap<String, Vec<RedisReview>>, redis::RedisError> {
        if app_ids.is_empty() {
            return Ok(std::collections::HashMap::new());
        }

        let mut conn = self.get_connection().await?;
        let keys: Vec<String> = app_ids
            .iter()
            .map(|id| format!("plugins:{}:reviews", id))
            .collect();

        let reviews_data: Vec<Option<String>> = conn.mget(&keys).await?;

        let mut result: std::collections::HashMap<String, Vec<RedisReview>> =
            std::collections::HashMap::new();

        for (id, data) in app_ids.iter().zip(reviews_data.iter()) {
            if let Some(raw) = data {
                // Python stores reviews as a dict: {uid: {score: int, review: str, ...}}
                // We need to parse this to extract scores
                let reviews = parse_python_reviews(raw);
                if !reviews.is_empty() {
                    result.insert(id.clone(), reviews);
                }
            }
        }

        Ok(result)
    }
}

/// Parse Python dict format for reviews
/// Format: {'uid1': {'score': 5, 'review': 'text', ...}, 'uid2': {...}}
fn parse_python_reviews(raw: &str) -> Vec<RedisReview> {
    let mut reviews = Vec::new();

    // Try to parse as JSON first (newer format)
    if let Ok(parsed) = serde_json::from_str::<serde_json::Value>(raw) {
        if let Some(obj) = parsed.as_object() {
            for (_uid, review) in obj {
                if let Some(score) = review.get("score").and_then(|s| s.as_i64()) {
                    reviews.push(RedisReview { score: score as i32 });
                }
            }
        }
        return reviews;
    }

    // Fallback: parse Python dict format using regex
    // Looking for 'score': <number> patterns
    let score_regex = regex::Regex::new(r"'score':\s*(\d+)").unwrap();
    for cap in score_regex.captures_iter(raw) {
        if let Some(score_match) = cap.get(1) {
            if let Ok(score) = score_match.as_str().parse::<i32>() {
                reviews.push(RedisReview { score });
            }
        }
    }

    reviews
}
