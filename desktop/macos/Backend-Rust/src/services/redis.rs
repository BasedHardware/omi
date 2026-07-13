#![deny(dead_code, unreachable_pub)]

// Redis service for fail-closed server-key metering and dependency readiness.

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
pub(crate) enum RedisFailureClass {
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
    Health,
    RateLimit,
    TtsRateLimit,
}

impl RedisOperation {
    fn as_str(self) -> &'static str {
        match self {
            Self::Health => "health",
            Self::RateLimit => "rate_limit",
            Self::TtsRateLimit => "tts_rate_limit",
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
pub(crate) struct RedisService {
    client: Client,
    connection: Arc<Mutex<ConnectionState>>,
    jitter_seed: u64,
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

pub(crate) fn classify_redis_error(error: &RedisError) -> RedisFailureClass {
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
    pub(crate) async fn health_check(&self) -> Result<bool, redis::RedisError> {
        let pong: String = self
            .query(
                RedisOperation::Health,
                ReplayPolicy::SafeOnce,
                &redis::cmd("PING"),
            )
            .await?;
        Ok(pong == "PONG")
    }

    pub(crate) async fn check_rate_limit(
        &self,
        key_prefix: &str,
        uid: &str,
        _burst_limit: usize,
        burst_window_secs: u64,
    ) -> Result<(i64, i64), redis::RedisError> {
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

        let mut command = redis::cmd("EVAL");
        command
            .arg(script)
            .arg(2)
            .arg(&burst_key)
            .arg(&daily_key)
            .arg(cutoff_ms)
            .arg(now_ms)
            .arg((burst_window_secs * 2) as i64)
            .arg(172_800_i64);
        let result: Vec<i64> = self
            .query(RedisOperation::RateLimit, ReplayPolicy::Never, &command)
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

        let mut command = redis::cmd("EVAL");
        command
            .arg(script)
            .arg(2)
            .arg(&burst_key)
            .arg(&daily_chars_key)
            .arg(cutoff_ms)
            .arg(now_ms)
            .arg((burst_window_secs * 2) as i64)
            .arg(172_800_i64)
            .arg(chars as i64);
        let result: Vec<i64> = self
            .query(RedisOperation::TtsRateLimit, ReplayPolicy::Never, &command)
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
mod key_tests {
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
