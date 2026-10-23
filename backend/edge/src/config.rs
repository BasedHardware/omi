//! Configuration from the environment. Every key has a default except
//! `EDGE_UPSTREAM_URL`; invalid values fail startup instead of being ignored.
use std::fmt;
use std::net::SocketAddr;
use std::time::Duration;

/// Default max message size: uvicorn's `ws_max_size` (16 MiB), so the edge
/// never rejects a message that listen would accept.
pub const DEFAULT_MAX_MESSAGE_BYTES: usize = 16 * 1024 * 1024;

#[derive(Clone, Debug)]
pub struct Config {
    /// `EDGE_LISTEN_ADDR`: websocket, health and metrics port.
    pub listen_addr: SocketAddr,
    /// `EDGE_UPSTREAM_URL`: `ws://host:port` of backend-listen. The client's
    /// path and query are appended unchanged.
    pub upstream_url: String,
    /// `EDGE_PROXY_PATHS`: comma-separated websocket paths that are relayed.
    pub proxy_paths: Vec<String>,
    /// `EDGE_UPSTREAM_CONNECT_TIMEOUT_MS`: TCP connect plus websocket handshake.
    pub upstream_connect_timeout: Duration,
    /// `EDGE_DRAIN_READY_DELAY_MS`: after SIGTERM, how long `/readyz` reports
    /// 503 while new connections are still accepted (load balancer deregistration).
    pub drain_ready_delay: Duration,
    /// `EDGE_DRAIN_SPREAD_MS`: window over which open sessions are asked to
    /// close, so clients do not all reconnect in the same instant.
    pub drain_spread: Duration,
    /// `EDGE_CLOSE_TIMEOUT_MS`: how long a close handshake may take before
    /// the session is torn down.
    pub close_timeout: Duration,
    /// `EDGE_WS_READ_BUFFER_BYTES`: per-socket read buffer (prototype: 4 KiB
    /// cut idle memory per session about 5x against the 128 KiB default).
    pub ws_read_buffer_bytes: usize,
    /// `EDGE_WS_MAX_MESSAGE_BYTES`.
    pub ws_max_message_bytes: usize,
    /// `EDGE_MAX_SESSIONS`: open relayed sessions above which new upgrades get 503.
    pub max_sessions: usize,
    /// `EDGE_MAX_PENDING_HANDSHAKES`: concurrent upstream handshakes above
    /// which new upgrades get 503 (bounds connect storms against listen).
    pub max_pending_handshakes: usize,
    /// `EDGE_HEADER_READ_TIMEOUT_MS`: time a client has to send its request
    /// headers (slow-header protection).
    pub header_read_timeout: Duration,
    /// `EDGE_WORKER_THREADS`: tokio worker threads; unset means one per CPU.
    pub worker_threads: Option<usize>,
    /// `OMI_RELEASE_SHA`: release identity exported on `omi_edge_build_info`.
    pub release_sha: String,
    /// `EDGE_VAD_MODEL_PATH`: Silero VAD ONNX file. Unset disables the
    /// shadow ingest path (`/v1/shadow` answers 503).
    pub vad_model_path: Option<String>,
    /// `EDGE_SHADOW_MAX_SESSIONS`: open shadow sessions above which new
    /// mirrors get 503 (listen then stops mirroring that session).
    pub shadow_max_sessions: usize,
    /// `EDGE_SHADOW_TOKEN`: when set, mirrors must send it in
    /// `x-edge-shadow-token`.
    pub shadow_token: Option<String>,
    /// `EDGE_SHADOW_WORKER_THREADS`: threads of the separate runtime that
    /// decodes and scores mirrored audio, so shadow CPU never runs on the
    /// relay and health workers.
    pub shadow_worker_threads: usize,
}

/// Websocket path of the D2 shadow ingest (not relayed).
pub const SHADOW_PATH: &str = "/v1/shadow";

#[derive(Debug, PartialEq, Eq)]
pub struct ConfigError(pub String);

impl fmt::Display for ConfigError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.0)
    }
}

impl std::error::Error for ConfigError {}

impl Config {
    pub fn from_env() -> Result<Self, ConfigError> {
        Self::from_lookup(|key| std::env::var(key).ok())
    }

    pub fn from_lookup(lookup: impl Fn(&str) -> Option<String>) -> Result<Self, ConfigError> {
        let get = |key: &str| lookup(key).map(|v| v.trim().to_string()).filter(|v| !v.is_empty());

        let listen_addr = match get("EDGE_LISTEN_ADDR") {
            Some(v) => v
                .parse()
                .map_err(|_| ConfigError(format!("EDGE_LISTEN_ADDR: not a socket address: {v}")))?,
            None => SocketAddr::from(([0, 0, 0, 0], 8080)),
        };

        let upstream_url = parse_upstream_url(&get("EDGE_UPSTREAM_URL").ok_or_else(|| {
            ConfigError("EDGE_UPSTREAM_URL is required (for example ws://backend-listen:8080)".into())
        })?)?;

        let proxy_paths = match get("EDGE_PROXY_PATHS") {
            Some(v) => parse_paths(&v)?,
            None => vec!["/v4/listen".to_string()],
        };

        let ms = |key: &str, default: u64, min: u64, max: u64| -> Result<Duration, ConfigError> {
            let v = parse_u64(key, get(key), default)?;
            if v < min || v > max {
                return Err(ConfigError(format!("{key}: {v} outside [{min}, {max}]")));
            }
            Ok(Duration::from_millis(v))
        };

        let ws_read_buffer_bytes = parse_u64("EDGE_WS_READ_BUFFER_BYTES", get("EDGE_WS_READ_BUFFER_BYTES"), 4096)?;
        if !(1024..=1 << 20).contains(&ws_read_buffer_bytes) {
            return Err(ConfigError(format!(
                "EDGE_WS_READ_BUFFER_BYTES: {ws_read_buffer_bytes} outside [1024, 1048576]"
            )));
        }
        let ws_max_message_bytes = parse_u64(
            "EDGE_WS_MAX_MESSAGE_BYTES",
            get("EDGE_WS_MAX_MESSAGE_BYTES"),
            DEFAULT_MAX_MESSAGE_BYTES as u64,
        )?;
        if !(1024..=64 << 20).contains(&ws_max_message_bytes) {
            return Err(ConfigError(format!(
                "EDGE_WS_MAX_MESSAGE_BYTES: {ws_max_message_bytes} outside [1024, 67108864]"
            )));
        }

        let count = |key: &str, default: u64, max: u64| -> Result<usize, ConfigError> {
            let v = parse_u64(key, get(key), default)?;
            if v == 0 || v > max {
                return Err(ConfigError(format!("{key}: {v} outside [1, {max}]")));
            }
            Ok(v as usize)
        };

        let worker_threads = match get("EDGE_WORKER_THREADS") {
            None => None,
            Some(v) => match v.parse::<usize>() {
                Ok(n) if (1..=256).contains(&n) => Some(n),
                _ => return Err(ConfigError(format!("EDGE_WORKER_THREADS: expected 1..=256, got {v}"))),
            },
        };

        Ok(Config {
            listen_addr,
            upstream_url,
            proxy_paths,
            upstream_connect_timeout: ms("EDGE_UPSTREAM_CONNECT_TIMEOUT_MS", 5_000, 100, 60_000)?,
            drain_ready_delay: ms("EDGE_DRAIN_READY_DELAY_MS", 5_000, 0, 120_000)?,
            drain_spread: ms("EDGE_DRAIN_SPREAD_MS", 10_000, 0, 120_000)?,
            close_timeout: ms("EDGE_CLOSE_TIMEOUT_MS", 5_000, 100, 60_000)?,
            ws_read_buffer_bytes: ws_read_buffer_bytes as usize,
            ws_max_message_bytes: ws_max_message_bytes as usize,
            max_sessions: count("EDGE_MAX_SESSIONS", 5_000, 100_000)?,
            max_pending_handshakes: count("EDGE_MAX_PENDING_HANDSHAKES", 512, 10_000)?,
            header_read_timeout: ms("EDGE_HEADER_READ_TIMEOUT_MS", 10_000, 100, 120_000)?,
            worker_threads,
            release_sha: get("OMI_RELEASE_SHA").unwrap_or_default(),
            vad_model_path: get("EDGE_VAD_MODEL_PATH"),
            shadow_max_sessions: count("EDGE_SHADOW_MAX_SESSIONS", 500, 100_000)?,
            shadow_token: get("EDGE_SHADOW_TOKEN"),
            shadow_worker_threads: count("EDGE_SHADOW_WORKER_THREADS", 2, 64)?,
        })
    }

    /// Upper bound on the whole drain. The last session's close starts at
    /// ready delay + spread; its handshake may take the close timeout, then
    /// up to one second for its own abort close and one for the final flush
    /// (`session::ABORT_GRACE` each), plus one second of scheduling slack.
    pub fn drain_deadline(&self) -> Duration {
        self.drain_ready_delay + self.drain_spread + self.close_timeout + Duration::from_secs(3)
    }
}

fn parse_u64(key: &str, value: Option<String>, default: u64) -> Result<u64, ConfigError> {
    match value {
        None => Ok(default),
        Some(v) => v
            .parse()
            .map_err(|_| ConfigError(format!("{key}: not an unsigned integer: {v}"))),
    }
}

fn parse_upstream_url(raw: &str) -> Result<String, ConfigError> {
    let rest = raw.strip_prefix("ws://").ok_or_else(|| {
        ConfigError(format!(
            "EDGE_UPSTREAM_URL must start with ws:// (in-cluster), got {raw}"
        ))
    })?;
    let rest = rest.trim_end_matches('/');
    if rest.is_empty() || rest.contains('/') || rest.contains('?') || rest.contains('#') || rest.contains('@') {
        return Err(ConfigError(format!(
            "EDGE_UPSTREAM_URL must be ws://host[:port] with no path, query or userinfo, got {raw}"
        )));
    }
    Ok(format!("ws://{rest}"))
}

fn parse_paths(raw: &str) -> Result<Vec<String>, ConfigError> {
    let mut paths = Vec::new();
    for p in raw.split(',').map(str::trim).filter(|p| !p.is_empty()) {
        if !p.starts_with('/') || p.contains('?') || p.contains(' ') {
            return Err(ConfigError(format!("EDGE_PROXY_PATHS: invalid path {p}")));
        }
        if matches!(p, "/healthz" | "/readyz" | "/metrics" | SHADOW_PATH) {
            return Err(ConfigError(format!("EDGE_PROXY_PATHS: {p} is reserved")));
        }
        paths.push(p.to_string());
    }
    if paths.is_empty() {
        return Err(ConfigError("EDGE_PROXY_PATHS: no paths".into()));
    }
    Ok(paths)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::HashMap;

    fn cfg(pairs: &[(&str, &str)]) -> Result<Config, ConfigError> {
        let map: HashMap<String, String> = pairs.iter().map(|(k, v)| (k.to_string(), v.to_string())).collect();
        Config::from_lookup(|k| map.get(k).cloned())
    }

    #[test]
    fn defaults_need_only_upstream() {
        let c = cfg(&[("EDGE_UPSTREAM_URL", "ws://backend-listen:8080/")]).unwrap();
        assert_eq!(c.upstream_url, "ws://backend-listen:8080");
        assert_eq!(c.proxy_paths, vec!["/v4/listen"]);
        assert_eq!(c.listen_addr, "0.0.0.0:8080".parse().unwrap());
        assert_eq!(c.ws_read_buffer_bytes, 4096);
        assert_eq!(c.ws_max_message_bytes, DEFAULT_MAX_MESSAGE_BYTES);
        assert_eq!(c.drain_deadline(), Duration::from_secs(23));
        assert_eq!(c.max_sessions, 5_000);
        assert_eq!(c.max_pending_handshakes, 512);
        assert_eq!(c.worker_threads, None);
        assert_eq!(c.vad_model_path, None);
        assert_eq!(c.shadow_max_sessions, 500);
        assert_eq!(c.shadow_token, None);
        assert_eq!(c.shadow_worker_threads, 2);
    }

    #[test]
    fn missing_upstream_fails() {
        assert!(cfg(&[]).is_err());
    }

    #[test]
    fn upstream_must_be_plain_ws_origin() {
        for bad in [
            "http://x",
            "wss://x",
            "ws://",
            "ws://x/v4/listen",
            "ws://x?a=1",
            "ws://u:p@x",
        ] {
            assert!(cfg(&[("EDGE_UPSTREAM_URL", bad)]).is_err(), "{bad} accepted");
        }
    }

    #[test]
    fn paths_and_ranges_validate() {
        let ok = cfg(&[
            ("EDGE_UPSTREAM_URL", "ws://x"),
            ("EDGE_PROXY_PATHS", "/v4/listen, /v4/web/listen"),
        ])
        .unwrap();
        assert_eq!(ok.proxy_paths, vec!["/v4/listen", "/v4/web/listen"]);
        assert!(cfg(&[("EDGE_UPSTREAM_URL", "ws://x"), ("EDGE_PROXY_PATHS", "v4/listen")]).is_err());
        assert!(cfg(&[("EDGE_UPSTREAM_URL", "ws://x"), ("EDGE_PROXY_PATHS", "/metrics")]).is_err());
        assert!(cfg(&[("EDGE_UPSTREAM_URL", "ws://x"), ("EDGE_PROXY_PATHS", "/v1/shadow")]).is_err());
        assert!(cfg(&[("EDGE_UPSTREAM_URL", "ws://x"), ("EDGE_SHADOW_MAX_SESSIONS", "0")]).is_err());
        assert!(cfg(&[("EDGE_UPSTREAM_URL", "ws://x"), ("EDGE_CLOSE_TIMEOUT_MS", "5")]).is_err());
        assert!(cfg(&[("EDGE_UPSTREAM_URL", "ws://x"), ("EDGE_DRAIN_SPREAD_MS", "abc")]).is_err());
        assert!(cfg(&[("EDGE_UPSTREAM_URL", "ws://x"), ("EDGE_WORKER_THREADS", "0")]).is_err());
        assert!(cfg(&[("EDGE_UPSTREAM_URL", "ws://x"), ("EDGE_MAX_SESSIONS", "0")]).is_err());
        assert!(cfg(&[("EDGE_UPSTREAM_URL", "ws://x"), ("EDGE_WS_READ_BUFFER_BYTES", "10")]).is_err());
    }
}
