#![deny(dead_code, unreachable_pub)]

use redis::aio::ConnectionManager;
use redis::{Client, ConnectionAddr, ConnectionInfo, RedisConnectionInfo};
use std::sync::Arc;
use tokio::sync::RwLock;

pub(crate) struct RedisService {
    client: Client,
    // ConnectionManager (not a bare MultiplexedConnection) so a dropped link
    // reconnects internally. A cached MultiplexedConnection stayed broken forever
    // once the Redis link dropped, so every later command errored — which made the
    // rate limiter fail open (unmetered) permanently until process restart.
    connection: Arc<RwLock<Option<ConnectionManager>>>,
}

impl RedisService {
    pub(crate) fn new_with_params(
        host: &str,
        port: u16,
        password: Option<&str>,
    ) -> Result<Self, redis::RedisError> {
        let info = ConnectionInfo {
            addr: ConnectionAddr::Tcp(host.to_owned(), port),
            redis: RedisConnectionInfo {
                db: 0,
                username: Some("default".to_owned()),
                password: password.map(str::to_owned),
            },
        };
        Ok(Self {
            client: Client::open(info)?,
            connection: Arc::new(RwLock::new(None)),
        })
    }

    /// Get or create a connection.
    ///
    /// Returns a clone of a shared `ConnectionManager`, which transparently
    /// re-establishes the underlying link after a transient failure, so a dropped
    /// Redis connection recovers on the next command instead of erroring forever.
    async fn get_connection(&self) -> Result<ConnectionManager, redis::RedisError> {
        // Check if we have a cached connection manager
        {
            let conn = self.connection.read().await;
            if let Some(c) = conn.as_ref() {
                return Ok(c.clone());
            }
        }

        // Create a new connection manager
        let conn = ConnectionManager::new(self.client.clone()).await?;

        // Cache it (double-check under the write lock in case another task raced us)
        {
            let mut cached = self.connection.write().await;
            if let Some(existing) = cached.as_ref() {
                return Ok(existing.clone());
            }
            *cached = Some(conn.clone());
        }

        Ok(conn)
    }

    pub(crate) async fn check_rate_limit(
        &self,
        key_prefix: &str,
        uid: &str,
        _burst_limit: usize,
        burst_window_secs: u64,
    ) -> Result<(i64, i64), redis::RedisError> {
        let mut connection = self.get_connection().await?;
        let now_ms = chrono::Utc::now().timestamp_millis();
        let cutoff_ms = now_ms - (burst_window_secs as i64 * 1000);
        let (burst_key, daily_key) = rate_limit_keys(key_prefix, uid, now_ms);

        // The daily counter is also the nonce for the sorted-set member. That keeps
        // concurrent requests in the same millisecond from overwriting each other.
        let script = r#"
local daily = redis.call('INCR', KEYS[2])
redis.call('EXPIRE', KEYS[2], ARGV[4])
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', ARGV[1])
redis.call('ZADD', KEYS[1], ARGV[2], ARGV[2] .. ':' .. tostring(daily))
local burst = redis.call('ZCARD', KEYS[1])
redis.call('EXPIRE', KEYS[1], ARGV[3])
return {daily, burst}
"#;
        let result: Vec<i64> = redis::cmd("EVAL")
            .arg(script)
            .arg(2)
            .arg(&burst_key)
            .arg(&daily_key)
            .arg(cutoff_ms)
            .arg(now_ms)
            .arg((burst_window_secs * 2) as i64)
            .arg(172_800_i64)
            .query_async(&mut connection)
            .await?;

        Ok((
            result.first().copied().unwrap_or(0),
            result.get(1).copied().unwrap_or(0),
        ))
    }

    pub(crate) async fn check_tts_rate_limit(
        &self,
        uid: &str,
        chars: usize,
        burst_window_secs: u64,
    ) -> Result<(i64, i64), redis::RedisError> {
        let mut connection = self.get_connection().await?;
        let now_ms = chrono::Utc::now().timestamp_millis();
        let cutoff_ms = now_ms - (burst_window_secs as i64 * 1000);
        let (burst_key, daily_chars_key) = tts_rate_limit_keys(uid, now_ms);

        let script = r#"
local chars = redis.call('INCRBY', KEYS[2], ARGV[5])
redis.call('EXPIRE', KEYS[2], ARGV[4])
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', ARGV[1])
redis.call('ZADD', KEYS[1], ARGV[2], ARGV[2] .. ':' .. tostring(chars))
local burst = redis.call('ZCARD', KEYS[1])
redis.call('EXPIRE', KEYS[1], ARGV[3])
return {chars, burst}
"#;
        let result: Vec<i64> = redis::cmd("EVAL")
            .arg(script)
            .arg(2)
            .arg(&burst_key)
            .arg(&daily_chars_key)
            .arg(cutoff_ms)
            .arg(now_ms)
            .arg((burst_window_secs * 2) as i64)
            .arg(172_800_i64)
            .arg(chars as i64)
            .query_async(&mut connection)
            .await?;

        Ok((
            result.first().copied().unwrap_or(0),
            result.get(1).copied().unwrap_or(0),
        ))
    }
}

fn rate_limit_keys(prefix: &str, uid: &str, now_ms: i64) -> (String, String) {
    let day = now_ms / 86_400_000;
    (
        format!("{prefix}:{uid}:burst"),
        format!("{prefix}:{uid}:daily:{day}"),
    )
}

fn tts_rate_limit_keys(uid: &str, now_ms: i64) -> (String, String) {
    let day = now_ms / 86_400_000;
    (
        format!("tts_rl:{uid}:burst"),
        format!("tts_rl:{uid}:chars:{day}"),
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rate_limit_keys_isolate_namespaces_users_and_days() {
        let first = rate_limit_keys("gemini_rl", "user-a", 86_400_000);
        let other_namespace = rate_limit_keys("chat_rl", "user-a", 86_400_000);
        let other_user = rate_limit_keys("gemini_rl", "user-b", 86_400_000);
        let next_day = rate_limit_keys("gemini_rl", "user-a", 172_800_000);

        assert_eq!(first.0, "gemini_rl:user-a:burst");
        assert_eq!(first.1, "gemini_rl:user-a:daily:1");
        assert_ne!(first, other_namespace);
        assert_ne!(first, other_user);
        assert_ne!(first.1, next_day.1);
    }

    #[test]
    fn tts_keys_keep_character_budget_separate_from_burst_budget() {
        assert_eq!(
            tts_rate_limit_keys("user-a", 86_400_000),
            (
                "tts_rl:user-a:burst".to_owned(),
                "tts_rl:user-a:chars:1".to_owned()
            )
        );
    }
}
