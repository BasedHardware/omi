// Redis service for shared metadata and fail-closed server-key metering.
// Conversation/task/app methods mirror the Python backend's redis_db.py keys.

use redis::{
    Client, ConnectionAddr, ConnectionInfo, ErrorKind, FromRedisValue, RedisConnectionInfo,
    RedisError,
};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};
use tokio::sync::Mutex;

const CONNECT_TIMEOUT: Duration = Duration::from_secs(2);
const COMMAND_TIMEOUT: Duration = Duration::from_secs(3);
const RECONNECT_ATTEMPTS: usize = 2;
const RECONNECT_COOLDOWN: Duration = Duration::from_secs(1);
static JITTER_SEQUENCE: AtomicU64 = AtomicU64::new(0);

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RedisFailureClass {
    Transport,
    Capacity,
    AuthConfig,
    CommandData,
}

impl RedisFailureClass {
    pub(crate) fn as_str(self) -> &'static str {
        match self {
            Self::Transport => "transport",
            Self::Capacity => "capacity",
            Self::AuthConfig => "auth_config",
            Self::CommandData => "command_data",
        }
    }
}

#[derive(Debug, Clone, Copy)]
enum RedisOperation {
    ConversationWrite,
    ConversationRead,
    PublicSetWrite,
    PublicSetRead,
    Health,
    TaskShareWrite,
    TaskShareRead,
    TaskShareAccept,
    RateLimit,
    TtsRateLimit,
    AppInstallsRead,
    AppReviewsRead,
}

impl RedisOperation {
    fn as_str(self) -> &'static str {
        match self {
            Self::ConversationWrite => "conversation_write",
            Self::ConversationRead => "conversation_read",
            Self::PublicSetWrite => "public_set_write",
            Self::PublicSetRead => "public_set_read",
            Self::Health => "health",
            Self::TaskShareWrite => "task_share_write",
            Self::TaskShareRead => "task_share_read",
            Self::TaskShareAccept => "task_share_accept",
            Self::RateLimit => "rate_limit",
            Self::TtsRateLimit => "tts_rate_limit",
            Self::AppInstallsRead => "app_installs_read",
            Self::AppReviewsRead => "app_reviews_read",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum ReplayPolicy {
    SafeOnce,
    Never,
}

#[derive(Clone)]
struct ConnectionLease {
    connection: redis::aio::MultiplexedConnection,
    generation: u64,
    connected_at: Instant,
}

struct ConnectionState {
    cached: Option<ConnectionLease>,
    generation: u64,
    cooldown_until: Option<Instant>,
    last_failure: Option<RedisFailureClass>,
}

impl Default for ConnectionState {
    fn default() -> Self {
        Self {
            cached: None,
            generation: 0,
            cooldown_until: None,
            last_failure: None,
        }
    }
}

/// Shared Redis command boundary and recoverable connection owner.
pub struct RedisService {
    client: Client,
    connection: Arc<Mutex<ConnectionState>>,
    jitter_seed: u64,
}

/// Review data stored in Redis
#[derive(Debug, Clone)]
pub struct RedisReview {
    pub score: i32,
}

impl RedisService {
    /// Create a new Redis service with explicit connection parameters
    /// This avoids URL encoding issues with special characters in passwords
    pub fn new_with_params(
        host: &str,
        port: u16,
        password: Option<&str>,
    ) -> Result<Self, redis::RedisError> {
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
            connection: Arc::new(Mutex::new(ConnectionState::default())),
            jitter_seed: next_jitter_seed(),
        })
    }

    /// Create a new Redis service from URL (legacy, may have encoding issues)
    pub fn new(redis_url: &str) -> Result<Self, redis::RedisError> {
        let client = Client::open(redis_url)?;
        Ok(Self {
            client,
            connection: Arc::new(Mutex::new(ConnectionState::default())),
            jitter_seed: next_jitter_seed(),
        })
    }

    /// Acquire the current generation or establish exactly one new generation.
    ///
    /// The mutex is held only while selecting/connecting a generation. Commands
    /// use cloned multiplexed leases outside the lock, so healthy traffic stays
    /// concurrent while cold starts and reconnects remain single-flight.
    async fn get_connection(
        &self,
        operation: RedisOperation,
    ) -> Result<ConnectionLease, RedisError> {
        let mut state = self.connection.lock().await;
        if let Some(cached) = state.cached.as_ref() {
            return Ok(cached.clone());
        }

        let now = Instant::now();
        if state.cooldown_until.is_some_and(|until| now < until) {
            let class = state.last_failure.unwrap_or(RedisFailureClass::Transport);
            tracing::warn!(
                event = "redis_reconnect",
                operation = operation.as_str(),
                outcome = "cooldown",
                failure_class = class.as_str(),
                generation = state.generation,
                "Redis reconnect suppressed during bounded cooldown"
            );
            return Err(synthetic_error(class, "Redis reconnect is cooling down"));
        }

        let mut last_error = None;
        for attempt in 0..RECONNECT_ATTEMPTS {
            if attempt > 0 {
                // Small generation-derived jitter prevents synchronized instances
                // from reconnecting in lockstep without introducing an unbounded
                // retry loop.
                let jitter_ms =
                    20 + ((self.jitter_seed ^ state.generation ^ (attempt as u64 * 17)) % 31);
                tokio::time::sleep(Duration::from_millis(jitter_ms)).await;
            }

            tracing::info!(
                event = "redis_reconnect",
                operation = operation.as_str(),
                outcome = "attempted",
                attempt = attempt + 1,
                generation = state.generation,
                "Redis connection attempt"
            );
            let result = tokio::time::timeout(
                CONNECT_TIMEOUT,
                self.client.get_multiplexed_async_connection(),
            )
            .await;

            match result {
                Ok(Ok(connection)) => {
                    state.generation = state.generation.saturating_add(1);
                    let lease = ConnectionLease {
                        connection,
                        generation: state.generation,
                        connected_at: Instant::now(),
                    };
                    state.cached = Some(lease.clone());
                    state.cooldown_until = None;
                    state.last_failure = None;
                    tracing::info!(
                        event = "redis_reconnect",
                        operation = operation.as_str(),
                        outcome = "succeeded",
                        attempt = attempt + 1,
                        generation = lease.generation,
                        "Redis connection generation established"
                    );
                    return Ok(lease);
                }
                Ok(Err(error)) => {
                    let class = classify_redis_error(&error);
                    tracing::warn!(
                        event = "redis_reconnect",
                        operation = operation.as_str(),
                        outcome = "failed",
                        attempt = attempt + 1,
                        failure_class = class.as_str(),
                        generation = state.generation,
                        "Redis connection attempt failed"
                    );
                    let retryable = class == RedisFailureClass::Transport;
                    last_error = Some(error);
                    if !retryable {
                        break;
                    }
                }
                Err(_) => {
                    let error = synthetic_error(
                        RedisFailureClass::Transport,
                        "Redis connection attempt timed out",
                    );
                    last_error = Some(error);
                }
            }
        }

        let error = last_error.unwrap_or_else(|| {
            synthetic_error(
                RedisFailureClass::Transport,
                "Redis connection attempts exhausted",
            )
        });
        let class = classify_redis_error(&error);
        state.cooldown_until = Some(Instant::now() + RECONNECT_COOLDOWN);
        state.last_failure = Some(class);
        tracing::error!(
            event = "redis_reconnect",
            operation = operation.as_str(),
            outcome = "exhausted",
            failure_class = class.as_str(),
            generation = state.generation,
            "Redis reconnect exhausted"
        );
        Err(error)
    }

    async fn invalidate_if_current(&self, lease: &ConnectionLease, operation: RedisOperation) {
        let mut state = self.connection.lock().await;
        let is_current = state
            .cached
            .as_ref()
            .is_some_and(|cached| cached.generation == lease.generation);
        if !is_current {
            return;
        }

        let age_bucket = connection_age_bucket(lease.connected_at.elapsed());
        state.cached = None;
        tracing::warn!(
            event = "redis_connection_invalidated",
            operation = operation.as_str(),
            generation = lease.generation,
            connection_age_bucket = age_bucket,
            "Invalidated stale Redis connection generation"
        );
    }

    async fn query<T>(
        &self,
        operation: RedisOperation,
        replay: ReplayPolicy,
        command: &redis::Cmd,
    ) -> Result<T, RedisError>
    where
        T: FromRedisValue,
    {
        let mut lease = match self.get_connection(operation).await {
            Ok(lease) => lease,
            Err(error) => {
                let class = classify_redis_error(&error);
                tracing::error!(
                    event = "redis_operation",
                    operation = operation.as_str(),
                    outcome = "acquire_exhausted",
                    attempt = 1,
                    failure_class = class.as_str(),
                    "Redis operation could not acquire a connection"
                );
                return Err(error);
            }
        };
        match query_with_timeout(command, &mut lease.connection).await {
            Ok(value) => {
                tracing::info!(
                    event = "redis_operation",
                    operation = operation.as_str(),
                    outcome = "succeeded",
                    attempt = 1,
                    generation = lease.generation,
                    "Redis operation completed"
                );
                Ok(value)
            }
            Err(first_error) => {
                let class = classify_redis_error(&first_error);
                tracing::warn!(
                    event = "redis_operation",
                    operation = operation.as_str(),
                    outcome = "failed",
                    attempt = 1,
                    failure_class = class.as_str(),
                    generation = lease.generation,
                    "Redis operation failed"
                );
                if class != RedisFailureClass::Transport {
                    return Err(first_error);
                }

                self.invalidate_if_current(&lease, operation).await;
                let reconnect = self.get_connection(operation).await;
                if replay == ReplayPolicy::Never {
                    // The server may have applied a mutating command before the
                    // transport failed. Re-establish the owner for later callers,
                    // but never risk duplicating this operation.
                    if reconnect.is_err() {
                        tracing::error!(
                            event = "redis_operation",
                            operation = operation.as_str(),
                            outcome = "reconnect_exhausted",
                            failure_class = class.as_str(),
                            "Non-replayable Redis operation remained failed"
                        );
                    }
                    return Err(first_error);
                }

                let mut retry_lease = match reconnect {
                    Ok(lease) => lease,
                    Err(error) => {
                        let reconnect_class = classify_redis_error(&error);
                        tracing::error!(
                            event = "redis_operation",
                            operation = operation.as_str(),
                            outcome = "reconnect_exhausted",
                            attempt = 2,
                            failure_class = reconnect_class.as_str(),
                            "Redis operation could not reacquire a connection"
                        );
                        return Err(error);
                    }
                };
                match query_with_timeout(command, &mut retry_lease.connection).await {
                    Ok(value) => {
                        tracing::info!(
                            event = "redis_operation",
                            operation = operation.as_str(),
                            outcome = "recovered",
                            attempt = 2,
                            generation = retry_lease.generation,
                            "Redis operation recovered after reconnect"
                        );
                        Ok(value)
                    }
                    Err(error) => {
                        let retry_class = classify_redis_error(&error);
                        if retry_class == RedisFailureClass::Transport {
                            self.invalidate_if_current(&retry_lease, operation).await;
                        }
                        tracing::error!(
                            event = "redis_operation",
                            operation = operation.as_str(),
                            outcome = "exhausted",
                            attempt = 2,
                            failure_class = retry_class.as_str(),
                            generation = retry_lease.generation,
                            "Redis operation retry exhausted"
                        );
                        Err(error)
                    }
                }
            }
        }
    }

    #[cfg(test)]
    async fn generation(&self) -> u64 {
        self.connection.lock().await.generation
    }
}

fn next_jitter_seed() -> u64 {
    let time = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_nanos() as u64)
        .unwrap_or_default();
    time ^ u64::from(std::process::id()) ^ JITTER_SEQUENCE.fetch_add(1, Ordering::Relaxed)
}

async fn query_with_timeout<T>(
    command: &redis::Cmd,
    connection: &mut redis::aio::MultiplexedConnection,
) -> Result<T, RedisError>
where
    T: FromRedisValue,
{
    match tokio::time::timeout(COMMAND_TIMEOUT, command.query_async(connection)).await {
        Ok(result) => result,
        Err(_) => Err(synthetic_error(
            RedisFailureClass::Transport,
            "Redis command timed out",
        )),
    }
}

pub fn classify_redis_error(error: &RedisError) -> RedisFailureClass {
    match error.kind() {
        ErrorKind::AuthenticationFailed | ErrorKind::InvalidClientConfig => {
            RedisFailureClass::AuthConfig
        }
        ErrorKind::BusyLoadingError
        | ErrorKind::TryAgain
        | ErrorKind::ClusterDown
        | ErrorKind::MasterDown
        | ErrorKind::ClusterConnectionNotFound
        | ErrorKind::ReadOnly => RedisFailureClass::Capacity,
        ErrorKind::IoError | ErrorKind::ParseError => RedisFailureClass::Transport,
        _ => RedisFailureClass::CommandData,
    }
}

fn synthetic_error(class: RedisFailureClass, detail: &'static str) -> RedisError {
    let kind = match class {
        RedisFailureClass::Transport => ErrorKind::IoError,
        RedisFailureClass::Capacity => ErrorKind::BusyLoadingError,
        RedisFailureClass::AuthConfig => ErrorKind::AuthenticationFailed,
        RedisFailureClass::CommandData => ErrorKind::ResponseError,
    };
    (kind, detail).into()
}

fn connection_age_bucket(age: Duration) -> &'static str {
    match age.as_secs() {
        0..=59 => "under_1m",
        60..=3599 => "1m_1h",
        3600..=86_399 => "1h_24h",
        _ => "over_24h",
    }
}

impl RedisService {
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
        let key = format!("memories-visibility:{}", conversation_id);
        let mut command = redis::cmd("SET");
        command.arg(&key).arg(uid);
        self.query::<()>(
            RedisOperation::ConversationWrite,
            ReplayPolicy::SafeOnce,
            &command,
        )
        .await?;
        tracing::info!(
            "Stored conversation visibility: {} -> {}",
            conversation_id,
            uid
        );
        Ok(())
    }

    /// Remove conversation_id -> uid mapping
    pub async fn remove_conversation_to_uid(
        &self,
        conversation_id: &str,
    ) -> Result<(), redis::RedisError> {
        let key = format!("memories-visibility:{}", conversation_id);
        let mut command = redis::cmd("DEL");
        command.arg(&key);
        self.query::<()>(
            RedisOperation::ConversationWrite,
            ReplayPolicy::SafeOnce,
            &command,
        )
        .await?;
        tracing::info!("Removed conversation visibility: {}", conversation_id);
        Ok(())
    }

    /// Get the uid that owns a public conversation
    /// Returns None if conversation is not public/shared
    pub async fn get_conversation_uid(
        &self,
        conversation_id: &str,
    ) -> Result<Option<String>, redis::RedisError> {
        let key = format!("memories-visibility:{}", conversation_id);
        let mut command = redis::cmd("GET");
        command.arg(&key);
        self.query(
            RedisOperation::ConversationRead,
            ReplayPolicy::SafeOnce,
            &command,
        )
        .await
    }

    /// Add conversation to the public conversations set
    /// Key: public-memories (SET)
    pub async fn add_public_conversation(
        &self,
        conversation_id: &str,
    ) -> Result<(), redis::RedisError> {
        let mut command = redis::cmd("SADD");
        command.arg("public-memories").arg(conversation_id);
        self.query::<()>(
            RedisOperation::PublicSetWrite,
            ReplayPolicy::SafeOnce,
            &command,
        )
        .await?;
        tracing::info!("Added conversation to public set: {}", conversation_id);
        Ok(())
    }

    /// Remove conversation from the public conversations set
    pub async fn remove_public_conversation(
        &self,
        conversation_id: &str,
    ) -> Result<(), redis::RedisError> {
        let mut command = redis::cmd("SREM");
        command.arg("public-memories").arg(conversation_id);
        self.query::<()>(
            RedisOperation::PublicSetWrite,
            ReplayPolicy::SafeOnce,
            &command,
        )
        .await?;
        tracing::info!("Removed conversation from public set: {}", conversation_id);
        Ok(())
    }

    /// Get all public conversation IDs
    pub async fn get_public_conversations(&self) -> Result<Vec<String>, redis::RedisError> {
        let mut command = redis::cmd("SMEMBERS");
        command.arg("public-memories");
        self.query(
            RedisOperation::PublicSetRead,
            ReplayPolicy::SafeOnce,
            &command,
        )
        .await
    }

    /// Check if Redis connection is healthy
    pub async fn health_check(&self) -> Result<bool, redis::RedisError> {
        let pong: String = self
            .query(
                RedisOperation::Health,
                ReplayPolicy::SafeOnce,
                &redis::cmd("PING"),
            )
            .await?;
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
        let key = format!("task_share:{}", token);
        let value = serde_json::json!({
            "uid": uid,
            "display_name": display_name,
            "task_ids": task_ids,
        });
        let mut command = redis::cmd("SETEX");
        command
            .arg(&key)
            .arg(30 * 24 * 60 * 60)
            .arg(value.to_string());
        self.query::<()>(
            RedisOperation::TaskShareWrite,
            ReplayPolicy::SafeOnce,
            &command,
        )
        .await?;
        tracing::info!("Stored task share: {} -> {} tasks", token, task_ids.len());
        Ok(())
    }

    /// Get task share data from Redis
    /// Returns (uid, display_name, task_ids) or None if expired/missing
    pub async fn get_task_share(
        &self,
        token: &str,
    ) -> Result<Option<(String, String, Vec<String>)>, redis::RedisError> {
        let key = format!("task_share:{}", token);
        let mut command = redis::cmd("GET");
        command.arg(&key);
        let raw: Option<String> = self
            .query(
                RedisOperation::TaskShareRead,
                ReplayPolicy::SafeOnce,
                &command,
            )
            .await?;
        match raw {
            Some(data) => {
                if let Ok(parsed) = serde_json::from_str::<serde_json::Value>(&data) {
                    let uid = parsed["uid"].as_str().unwrap_or("").to_string();
                    let display_name = parsed["display_name"].as_str().unwrap_or("").to_string();
                    let task_ids: Vec<String> = parsed["task_ids"]
                        .as_array()
                        .map(|arr| {
                            arr.iter()
                                .filter_map(|v| v.as_str().map(String::from))
                                .collect()
                        })
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
        let key = format!("task_share:{}:accepted", token);
        let mut add_command = redis::cmd("SADD");
        add_command.arg(&key).arg(uid);
        let added: i32 = self
            .query(
                RedisOperation::TaskShareAccept,
                ReplayPolicy::Never,
                &add_command,
            )
            .await?;
        // Set 30-day TTL on the accepted set
        let mut expire_command = redis::cmd("EXPIRE");
        expire_command.arg(&key).arg(30 * 24 * 60 * 60);
        self.query::<()>(
            RedisOperation::TaskShareAccept,
            ReplayPolicy::SafeOnce,
            &expire_command,
        )
        .await?;
        Ok(added == 1)
    }

    // ============================================================================
    // GEMINI RATE LIMITING — atomic burst + daily counters via Lua
    // Issue #6098 L2
    // ============================================================================

    /// Check and record an API request for rate limiting under the given key
    /// namespace (e.g. "gemini_rl" or "chat_rl"), keeping each budget isolated.
    /// Uses a Lua script for atomic burst (sorted set) + daily (counter) in one round-trip.
    /// Returns (daily_count, burst_count) so the caller can decide Allow/Degrade/Reject.
    pub async fn check_rate_limit(
        &self,
        key_prefix: &str,
        uid: &str,
        _burst_limit: usize,
        burst_window_secs: u64,
    ) -> Result<(i64, i64), redis::RedisError> {
        let now_ms = chrono::Utc::now().timestamp_millis();
        let day_ordinal = (now_ms / 86_400_000).to_string();
        let cutoff_ms = now_ms - (burst_window_secs as i64 * 1000);

        let burst_key = format!("{}:{}:burst", key_prefix, uid);
        let daily_key = format!("{}:{}:daily:{}", key_prefix, uid, day_ordinal);

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

        let mut command = redis::cmd("EVAL");
        command
            .arg(script)
            .arg(2) // num keys
            .arg(&burst_key)
            .arg(&daily_key)
            .arg(cutoff_ms)
            .arg(now_ms)
            .arg(burst_ttl)
            .arg(daily_ttl);
        let result: Vec<i64> = self
            .query(RedisOperation::RateLimit, ReplayPolicy::Never, &command)
            .await?;

        let daily_count = result.first().copied().unwrap_or(0);
        let burst_count = result.get(1).copied().unwrap_or(0);

        Ok((daily_count, burst_count))
    }

    /// Check and record an OpenAI TTS request for rate limiting.
    /// Uses a Lua script for atomic burst (sorted set) + daily character counter.
    /// Returns (daily_chars, burst_count) so the caller can decide Allow/Reject.
    pub async fn check_tts_rate_limit(
        &self,
        uid: &str,
        chars: usize,
        burst_window_secs: u64,
    ) -> Result<(i64, i64), redis::RedisError> {
        let now_ms = chrono::Utc::now().timestamp_millis();
        let day_ordinal = (now_ms / 86_400_000).to_string();
        let cutoff_ms = now_ms - (burst_window_secs as i64 * 1000);

        let burst_key = format!("tts_rl:{}:burst", uid);
        let daily_chars_key = format!("tts_rl:{}:chars:{}", uid, day_ordinal);

        // KEYS[1] = burst_key, KEYS[2] = daily_chars_key
        // ARGV[1] = cutoff_ms, ARGV[2] = now_ms, ARGV[3] = burst_ttl,
        // ARGV[4] = daily_ttl, ARGV[5] = character count
        let script = r#"
local chars = redis.call('INCRBY', KEYS[2], ARGV[5])
redis.call('EXPIRE', KEYS[2], ARGV[4])
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', ARGV[1])
redis.call('ZADD', KEYS[1], ARGV[2], ARGV[2] .. ':' .. tostring(chars))
local burst = redis.call('ZCARD', KEYS[1])
redis.call('EXPIRE', KEYS[1], ARGV[3])
return {chars, burst}
"#;

        let burst_ttl = (burst_window_secs * 2) as i64;
        let daily_ttl: i64 = 172_800;

        let mut command = redis::cmd("EVAL");
        command
            .arg(script)
            .arg(2)
            .arg(&burst_key)
            .arg(&daily_chars_key)
            .arg(cutoff_ms)
            .arg(now_ms)
            .arg(burst_ttl)
            .arg(daily_ttl)
            .arg(chars as i64);
        let result: Vec<i64> = self
            .query(RedisOperation::TtsRateLimit, ReplayPolicy::Never, &command)
            .await?;

        let daily_chars = result.first().copied().unwrap_or(0);
        let burst_count = result.get(1).copied().unwrap_or(0);

        Ok((daily_chars, burst_count))
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

        let keys: Vec<String> = app_ids
            .iter()
            .map(|id| format!("plugins:{}:installs", id))
            .collect();

        let mut command = redis::cmd("MGET");
        command.arg(&keys);
        let counts: Vec<Option<String>> = self
            .query(
                RedisOperation::AppInstallsRead,
                ReplayPolicy::SafeOnce,
                &command,
            )
            .await?;

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

        let keys: Vec<String> = app_ids
            .iter()
            .map(|id| format!("plugins:{}:reviews", id))
            .collect();

        let mut command = redis::cmd("MGET");
        command.arg(&keys);
        let reviews_data: Vec<Option<String>> = self
            .query(
                RedisOperation::AppReviewsRead,
                ReplayPolicy::SafeOnce,
                &command,
            )
            .await?;

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
                    reviews.push(RedisReview {
                        score: score as i32,
                    });
                }
            }
        }
        return reviews;
    }

    // Fallback: parse Python dict format using regex.
    // Compile the constant pattern once per process (and log at most once on the
    // impossible error path) instead of recompiling on every call.
    static SCORE_REGEX: std::sync::OnceLock<Option<regex::Regex>> = std::sync::OnceLock::new();
    let score_regex = SCORE_REGEX.get_or_init(|| match regex::Regex::new(r"'score':\s*(\d+)") {
        Ok(re) => Some(re),
        Err(error) => {
            tracing::error!(
                "Failed to compile Redis review score fallback regex: {}",
                error
            );
            None
        }
    });

    if let Some(score_regex) = score_regex {
        for cap in score_regex.captures_iter(raw) {
            if let Some(score_match) = cap.get(1) {
                if let Ok(score) = score_match.as_str().parse::<i32>() {
                    reviews.push(RedisReview { score });
                }
            }
        }
    }

    reviews
}

#[cfg(test)]
#[allow(clippy::unwrap_used)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicUsize, Ordering};
    use tokio::io::{AsyncBufReadExt, AsyncReadExt, AsyncWriteExt, BufReader};
    use tokio::net::{TcpListener, TcpStream};
    use tokio::sync::Barrier;

    async fn read_command(reader: &mut BufReader<TcpStream>) -> Vec<String> {
        let mut line = String::new();
        reader.read_line(&mut line).await.unwrap();
        assert!(line.starts_with('*'), "unexpected RESP frame: {line:?}");
        let count: usize = line[1..].trim().parse().unwrap();
        let mut args = Vec::with_capacity(count);
        for _ in 0..count {
            line.clear();
            reader.read_line(&mut line).await.unwrap();
            assert!(line.starts_with('$'), "unexpected bulk frame: {line:?}");
            let length: usize = line[1..].trim().parse().unwrap();
            let mut value = vec![0; length];
            reader.read_exact(&mut value).await.unwrap();
            let mut crlf = [0; 2];
            reader.read_exact(&mut crlf).await.unwrap();
            assert_eq!(&crlf, b"\r\n");
            args.push(String::from_utf8(value).unwrap());
        }
        args
    }

    async fn read_application_command(reader: &mut BufReader<TcpStream>) -> Vec<String> {
        loop {
            let command = read_command(reader).await;
            if command.first().is_some_and(|name| name == "CLIENT") {
                reader.get_mut().write_all(b"+OK\r\n").await.unwrap();
                continue;
            }
            return command;
        }
    }

    async fn complete_client_handshake(reader: &mut BufReader<TcpStream>) {
        for _ in 0..2 {
            let command = read_command(reader).await;
            assert_eq!(command.first().map(String::as_str), Some("CLIENT"));
            reader.get_mut().write_all(b"+OK\r\n").await.unwrap();
        }
    }

    async fn read_ping(reader: &mut BufReader<TcpStream>) {
        assert_eq!(read_application_command(reader).await, vec!["PING"]);
    }

    async fn pong(reader: &mut BufReader<TcpStream>) {
        reader.get_mut().write_all(b"+PONG\r\n").await.unwrap();
    }

    fn local_service(listener: &TcpListener, password: Option<&str>) -> RedisService {
        RedisService::new_with_params("127.0.0.1", listener.local_addr().unwrap().port(), password)
            .unwrap()
    }

    #[tokio::test]
    async fn stale_connection_reconnects_and_retries_safe_command_once() {
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let service = local_service(&listener, None);

        let server = tokio::spawn(async move {
            let (stale, _) = listener.accept().await.unwrap();
            let mut stale = BufReader::new(stale);
            read_ping(&mut stale).await;
            drop(stale);

            let (recovered, _) = listener.accept().await.unwrap();
            let mut recovered = BufReader::new(recovered);
            read_ping(&mut recovered).await;
            pong(&mut recovered).await;
        });

        assert!(service.health_check().await.unwrap());
        assert_eq!(service.generation().await, 2);
        server.await.unwrap();
    }

    #[tokio::test]
    async fn reconnect_exhaustion_returns_transport_error_without_process_restart() {
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let service = local_service(&listener, None);

        let server = tokio::spawn(async move {
            let (stale, _) = listener.accept().await.unwrap();
            let mut stale = BufReader::new(stale);
            read_ping(&mut stale).await;
            drop(stale);
            drop(listener);
        });

        let error = service.health_check().await.unwrap_err();
        assert_eq!(classify_redis_error(&error), RedisFailureClass::Transport);
        assert_eq!(service.generation().await, 1);
        server.await.unwrap();
    }

    #[tokio::test]
    async fn repeated_stale_cycles_replace_each_generation_once() {
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let service = local_service(&listener, None);

        let server = tokio::spawn(async move {
            let (first, _) = listener.accept().await.unwrap();
            let mut first = BufReader::new(first);
            read_ping(&mut first).await;
            drop(first);

            let (second, _) = listener.accept().await.unwrap();
            let mut second = BufReader::new(second);
            read_ping(&mut second).await;
            pong(&mut second).await;
            read_ping(&mut second).await;
            drop(second);

            let (third, _) = listener.accept().await.unwrap();
            let mut third = BufReader::new(third);
            read_ping(&mut third).await;
            pong(&mut third).await;
        });

        assert!(service.health_check().await.unwrap());
        assert!(service.health_check().await.unwrap());
        assert_eq!(service.generation().await, 3);
        server.await.unwrap();
    }

    #[tokio::test]
    async fn metering_command_reconnects_but_is_never_replayed() {
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let service = local_service(&listener, None);
        let commands_seen = Arc::new(AtomicUsize::new(0));
        let server_commands_seen = commands_seen.clone();

        let server = tokio::spawn(async move {
            let (stale, _) = listener.accept().await.unwrap();
            let mut stale = BufReader::new(stale);
            let command = read_application_command(&mut stale).await;
            assert_eq!(command.first().map(String::as_str), Some("EVAL"));
            server_commands_seen.fetch_add(1, Ordering::SeqCst);
            drop(stale);

            // The owner eagerly establishes a healthy generation for the next
            // caller, but the ambiguous EVAL must not be sent on it.
            let (recovered, _) = listener.accept().await.unwrap();
            let mut recovered = BufReader::new(recovered);
            complete_client_handshake(&mut recovered).await;
        });

        let error = service
            .check_rate_limit("test_rl", "uid", 30, 60)
            .await
            .unwrap_err();
        assert_eq!(classify_redis_error(&error), RedisFailureClass::Transport);
        assert_eq!(service.generation().await, 2);
        server.await.unwrap();
        assert_eq!(commands_seen.load(Ordering::SeqCst), 1);
    }

    #[tokio::test]
    async fn concurrent_stale_callers_share_one_reconnect_generation() {
        const CALLERS: usize = 8;

        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let service = Arc::new(local_service(&listener, None));
        let accepted = Arc::new(AtomicUsize::new(0));
        let server_accepted = accepted.clone();

        let server = tokio::spawn(async move {
            let (stale, _) = listener.accept().await.unwrap();
            let mut stale = BufReader::new(stale);
            server_accepted.fetch_add(1, Ordering::SeqCst);
            read_ping(&mut stale).await;
            pong(&mut stale).await;

            // Close the established generation as soon as the concurrent wave
            // starts. Any additional multiplexed frames already queued on it
            // fail with the same stale generation.
            read_ping(&mut stale).await;
            drop(stale);

            let (recovered, _) = listener.accept().await.unwrap();
            let mut recovered = BufReader::new(recovered);
            server_accepted.fetch_add(1, Ordering::SeqCst);
            for _ in 0..CALLERS {
                read_ping(&mut recovered).await;
                pong(&mut recovered).await;
            }
        });

        assert!(service.health_check().await.unwrap());
        let barrier = Arc::new(Barrier::new(CALLERS + 1));
        let mut callers = Vec::new();
        for _ in 0..CALLERS {
            let service = service.clone();
            let barrier = barrier.clone();
            callers.push(tokio::spawn(async move {
                barrier.wait().await;
                service.health_check().await
            }));
        }
        barrier.wait().await;

        for caller in callers {
            assert!(caller.await.unwrap().unwrap());
        }
        server.await.unwrap();
        assert_eq!(service.generation().await, 2);
        assert_eq!(accepted.load(Ordering::SeqCst), 2);
    }

    #[tokio::test]
    async fn authentication_failure_is_classified_and_not_retried_as_transport() {
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let service = local_service(&listener, Some("wrong-secret"));
        let accepted = Arc::new(AtomicUsize::new(0));
        let server_accepted = accepted.clone();

        let server = tokio::spawn(async move {
            let (connection, _) = listener.accept().await.unwrap();
            let mut connection = BufReader::new(connection);
            server_accepted.fetch_add(1, Ordering::SeqCst);
            let auth = read_command(&mut connection).await;
            assert_eq!(auth.first().map(String::as_str), Some("AUTH"));
            connection
                .get_mut()
                .write_all(b"-WRONGPASS invalid username-password pair\r\n")
                .await
                .unwrap();
        });

        let error = service.health_check().await.unwrap_err();
        assert_eq!(classify_redis_error(&error), RedisFailureClass::AuthConfig);
        assert_eq!(service.generation().await, 0);
        server.await.unwrap();
        assert_eq!(accepted.load(Ordering::SeqCst), 1);

        let config_error: RedisError =
            (ErrorKind::InvalidClientConfig, "invalid test config").into();
        assert_eq!(
            classify_redis_error(&config_error),
            RedisFailureClass::AuthConfig
        );
    }
}
