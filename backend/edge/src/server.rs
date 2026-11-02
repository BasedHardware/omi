//! HTTP front: websocket upgrades on proxied paths, `/healthz`, `/readyz`,
//! `/metrics`, and the SIGTERM drain sequence.
//!
//! The upstream handshake happens before the client gets its 101, so an
//! upstream rejection (401/403/...) reaches the client with the same status
//! and body it gets from listen today.
use std::convert::Infallible;
use std::io;
use std::net::SocketAddr;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::Arc;
use std::time::Instant;

use bytes::Bytes;
use http_body_util::Full;
use hyper::body::Incoming;
use hyper::header::{self, HeaderMap, HeaderName, HeaderValue};
use hyper::service::service_fn;
use hyper::{Method, Request, Response, StatusCode};
use hyper_util::rt::{TokioIo, TokioTimer};
use tokio::net::TcpListener;
use tokio::sync::{watch, Semaphore};
use tokio::task::JoinHandle;
use tokio_tungstenite::tungstenite::client::IntoClientRequest;
use tokio_tungstenite::tungstenite::handshake::derive_accept_key;
use tokio_tungstenite::tungstenite::protocol::{Role, WebSocketConfig};
use tokio_tungstenite::tungstenite::Error as WsError;
use tokio_tungstenite::WebSocketStream;
use tokio_util::sync::CancellationToken;
use tokio_util::task::TaskTracker;

use crate::config::{Config, SHADOW_PATH};
use crate::metrics::{HandshakeResult, Metrics, ShadowHandshake};
use crate::session::{drain_jitter, relay, SessionCtx};
use crate::shadow::{self, ShadowCore, ShadowMeta, ShadowPool};
use crate::silero;

type Body = Full<Bytes>;

/// Request headers that belong to this hop and are never forwarded upstream.
/// The websocket handshake headers are regenerated for the upstream leg.
const HOP_BY_HOP: &[&str] = &[
    "host",
    "connection",
    "upgrade",
    "keep-alive",
    "proxy-connection",
    "proxy-authorization",
    "proxy-authenticate",
    "te",
    "trailer",
    "transfer-encoding",
    "content-length",
    "sec-websocket-key",
    "sec-websocket-version",
    "sec-websocket-extensions",
    "sec-websocket-accept",
];

struct Shared {
    cfg: Config,
    metrics: Arc<Metrics>,
    ws_config: WebSocketConfig,
    /// True from the moment drain starts: `/readyz` answers 503.
    draining: AtomicBool,
    /// Cancelled when the listener closes: idle HTTP connections shut down.
    stop_accepting: CancellationToken,
    /// Cancelled when open sessions should start closing.
    close_sessions: CancellationToken,
    /// Every accepted connection (through its handshake) and every relayed
    /// session, so drain also waits for upgrades that were mid-handshake.
    sessions: TaskTracker,
    handshake_slots: Arc<Semaphore>,
    next_id: AtomicU64,
    /// Runtime and session slots for `/v1/shadow`; `None` when it is disabled.
    shadow_pool: Option<ShadowPool>,
}

/// A running edge. Dropping it does not stop the server; call [`Edge::drain`].
pub struct Edge {
    shared: Arc<Shared>,
    addr: SocketAddr,
    stop_accepting: CancellationToken,
    accept_loop: JoinHandle<()>,
}

/// Bind `cfg.listen_addr` and start serving.
pub async fn start(cfg: Config, metrics: Metrics) -> io::Result<Edge> {
    let listener = TcpListener::bind(cfg.listen_addr).await?;
    Ok(start_with_listener(listener, cfg, metrics))
}

/// Start serving on an already-bound listener (tests bind port 0).
pub fn start_with_listener(listener: TcpListener, cfg: Config, metrics: Metrics) -> Edge {
    let addr = listener.local_addr().expect("bound listener has an address");
    let ws_config = WebSocketConfig::default()
        .read_buffer_size(cfg.ws_read_buffer_bytes)
        .write_buffer_size(0)
        .max_message_size(Some(cfg.ws_max_message_bytes))
        .max_frame_size(Some(cfg.ws_max_message_bytes));
    let stop_accepting = CancellationToken::new();
    let shadow_pool = match &cfg.vad_model_path {
        None => None,
        Some(_) => ShadowPool::new(cfg.shadow_worker_threads, cfg.shadow_max_sessions)
            .map_err(|err| tracing::error!(error = %err, "shadow runtime failed; /v1/shadow disabled"))
            .ok(),
    };
    let shared = Arc::new(Shared {
        shadow_pool,
        handshake_slots: Arc::new(Semaphore::new(cfg.max_pending_handshakes)),
        cfg,
        metrics: Arc::new(metrics),
        ws_config,
        draining: AtomicBool::new(false),
        stop_accepting: stop_accepting.clone(),
        close_sessions: CancellationToken::new(),
        sessions: TaskTracker::new(),
        next_id: AtomicU64::new(1),
    });
    let accept_loop = tokio::spawn(accept_loop(listener, shared.clone()));
    Edge {
        shared,
        addr,
        stop_accepting,
        accept_loop,
    }
}

impl Edge {
    pub fn local_addr(&self) -> SocketAddr {
        self.addr
    }

    pub fn metrics(&self) -> Arc<Metrics> {
        self.shared.metrics.clone()
    }

    /// Drain and return when every session has ended or the drain deadline
    /// passed:
    /// 1. `/readyz` turns 503 and `omi_edge_draining` 1; new connections are
    ///    still accepted for `EDGE_DRAIN_READY_DELAY_MS` while the load
    ///    balancer deregisters the pod;
    /// 2. the listener closes;
    /// 3. each open session is sent 1012 at a per-session offset within
    ///    `EDGE_DRAIN_SPREAD_MS`, and its close handshake is relayed upstream.
    pub async fn drain(self) {
        let started = Instant::now();
        let shared = self.shared;
        shared.draining.store(true, Ordering::SeqCst);
        shared.metrics.draining.set(1);
        tokio::time::sleep(shared.cfg.drain_ready_delay).await;

        self.stop_accepting.cancel();
        let _ = self.accept_loop.await;
        shared.close_sessions.cancel();
        shared.sessions.close();

        let remaining = shared.cfg.drain_deadline().saturating_sub(started.elapsed());
        if tokio::time::timeout(remaining, shared.sessions.wait()).await.is_err() {
            tracing::warn!(open = shared.sessions.len(), "drain deadline passed with sessions open");
        }
    }
}

async fn accept_loop(listener: TcpListener, shared: Arc<Shared>) {
    loop {
        let (stream, peer) = tokio::select! {
            _ = shared.stop_accepting.cancelled() => return,
            r = listener.accept() => match r {
                Ok(x) => x,
                Err(err) => {
                    tracing::warn!(error = %err, "accept failed");
                    tokio::time::sleep(std::time::Duration::from_millis(50)).await;
                    continue;
                }
            },
        };
        let _ = stream.set_nodelay(true);
        let conn_shared = shared.clone();
        shared.sessions.spawn(async move {
            let stop = conn_shared.stop_accepting.clone();
            let header_read_timeout = conn_shared.cfg.header_read_timeout;
            // True while a request is being handled, and from a 101 onwards
            // (the connection then ends by itself when it becomes a session).
            let (busy_tx, mut busy_rx) = watch::channel(false);
            let busy_tx = Arc::new(busy_tx);
            let svc = service_fn(move |req| {
                let shared = conn_shared.clone();
                let busy = busy_tx.clone();
                async move {
                    busy.send_replace(true);
                    let resp = handle(req, peer, shared).await;
                    if !matches!(&resp, Ok(r) if r.status() == StatusCode::SWITCHING_PROTOCOLS) {
                        busy.send_replace(false);
                    }
                    resp
                }
            });
            let conn = hyper::server::conn::http1::Builder::new()
                .timer(TokioTimer::new())
                .header_read_timeout(header_read_timeout)
                .serve_connection(TokioIo::new(stream), svc)
                .with_upgrades();
            tokio::pin!(conn);
            tokio::select! {
                _ = conn.as_mut() => return,
                _ = stop.cancelled() => {}
            }
            // Listener closed. Let an in-flight request finish first: hyper's
            // graceful shutdown would add `Connection: close` to a 101 and
            // break the upgrade. Then close the idle keep-alive socket.
            tokio::select! {
                _ = conn.as_mut() => return,
                _ = busy_rx.wait_for(|busy| !busy) => {}
            }
            conn.as_mut().graceful_shutdown();
            let _ = conn.await;
        });
    }
}

fn text(status: StatusCode, body: &'static str) -> Response<Body> {
    let mut resp = Response::new(Full::new(Bytes::from_static(body.as_bytes())));
    *resp.status_mut() = status;
    resp.headers_mut().insert(
        header::CONTENT_TYPE,
        HeaderValue::from_static("text/plain; charset=utf-8"),
    );
    resp
}

async fn handle(req: Request<Incoming>, peer: SocketAddr, shared: Arc<Shared>) -> Result<Response<Body>, Infallible> {
    let path = req.uri().path();
    let resp = match (req.method(), path) {
        (&Method::GET, "/healthz") => text(StatusCode::OK, "ok\n"),
        (&Method::GET, "/readyz") => {
            if shared.draining.load(Ordering::SeqCst) {
                text(StatusCode::SERVICE_UNAVAILABLE, "draining\n")
            } else {
                text(StatusCode::OK, "ready\n")
            }
        }
        (&Method::GET, "/metrics") => {
            let mut resp = Response::new(Full::new(Bytes::from(shared.metrics.render())));
            resp.headers_mut().insert(
                header::CONTENT_TYPE,
                HeaderValue::from_static("text/plain; version=0.0.4; charset=utf-8"),
            );
            resp
        }
        (_, SHADOW_PATH) => shadow_upgrade(req, shared),
        _ if shared.cfg.proxy_paths.iter().any(|p| p == path) => proxy(req, peer, shared).await,
        _ => text(StatusCode::NOT_FOUND, "not found\n"),
    };
    Ok(resp)
}

fn header_has_token(headers: &HeaderMap, name: HeaderName, token: &str) -> bool {
    headers
        .get_all(name)
        .iter()
        .filter_map(|v| v.to_str().ok())
        .flat_map(|v| v.split(','))
        .any(|t| t.trim().eq_ignore_ascii_case(token))
}

/// Headers to forward upstream: everything but hop-by-hop and handshake
/// headers, plus the peer appended to `X-Forwarded-For`.
pub fn upstream_headers(client: &HeaderMap, peer: SocketAddr) -> HeaderMap {
    let mut out = HeaderMap::new();
    for (name, value) in client {
        if HOP_BY_HOP.contains(&name.as_str()) {
            continue;
        }
        out.append(name.clone(), value.clone());
    }
    let xff = match client.get("x-forwarded-for").and_then(|v| v.to_str().ok()) {
        Some(prev) if !prev.trim().is_empty() => format!("{prev}, {}", peer.ip()),
        _ => peer.ip().to_string(),
    };
    if let Ok(v) = HeaderValue::from_str(&xff) {
        out.insert(HeaderName::from_static("x-forwarded-for"), v);
    }
    out
}

fn overloaded() -> Response<Body> {
    let mut resp = text(StatusCode::SERVICE_UNAVAILABLE, "edge overloaded\n");
    resp.headers_mut()
        .insert(header::RETRY_AFTER, HeaderValue::from_static("1"));
    resp
}

/// The client's `Sec-WebSocket-Key` if this is a valid version-13 upgrade.
fn upgrade_key(req: &Request<Incoming>) -> Option<HeaderValue> {
    let headers = req.headers();
    let is_upgrade = req.method() == Method::GET
        && header_has_token(headers, header::CONNECTION, "upgrade")
        && header_has_token(headers, header::UPGRADE, "websocket");
    let version_ok = headers.get(header::SEC_WEBSOCKET_VERSION).map(|v| v.as_bytes()) == Some(b"13");
    headers
        .get(header::SEC_WEBSOCKET_KEY)
        .cloned()
        .filter(|_| is_upgrade && version_ok)
}

fn upgrade_required() -> Response<Body> {
    let mut resp = text(StatusCode::UPGRADE_REQUIRED, "websocket upgrade required\n");
    resp.headers_mut()
        .insert(header::SEC_WEBSOCKET_VERSION, HeaderValue::from_static("13"));
    resp
}

fn switching_protocols(key: &HeaderValue) -> Response<Body> {
    let mut resp = Response::new(Full::new(Bytes::new()));
    *resp.status_mut() = StatusCode::SWITCHING_PROTOCOLS;
    let h = resp.headers_mut();
    h.insert(header::CONNECTION, HeaderValue::from_static("Upgrade"));
    h.insert(header::UPGRADE, HeaderValue::from_static("websocket"));
    let accept = derive_accept_key(key.as_bytes());
    h.insert(
        header::SEC_WEBSOCKET_ACCEPT,
        HeaderValue::from_str(&accept).expect("base64 is a valid header"),
    );
    resp
}

/// Accept a D2 mirror from listen (see `shadow`). Not relayed anywhere.
fn shadow_upgrade(mut req: Request<Incoming>, shared: Arc<Shared>) -> Response<Body> {
    let shadow = &shared.metrics.shadow;
    let pool = match &shared.shadow_pool {
        Some(pool) if !shared.draining.load(Ordering::SeqCst) && silero::initialized() => pool,
        _ => {
            shadow.handshake(ShadowHandshake::Disabled);
            return text(StatusCode::SERVICE_UNAVAILABLE, "shadow disabled\n");
        }
    };
    let Some(key) = upgrade_key(&req) else {
        shadow.handshake(ShadowHandshake::InvalidRequest);
        return upgrade_required();
    };
    if let Some(token) = &shared.cfg.shadow_token {
        let sent = req.headers().get("x-edge-shadow-token").map(|v| v.as_bytes());
        if !sent.is_some_and(|s| constant_time_eq(s, token.as_bytes())) {
            shadow.handshake(ShadowHandshake::Unauthorized);
            return text(StatusCode::UNAUTHORIZED, "unauthorized\n");
        }
    }
    let meta = match ShadowMeta::from_query(req.uri().query().unwrap_or("")) {
        Ok(meta) => meta,
        Err(reason) => {
            shadow.handshake(ShadowHandshake::InvalidRequest);
            let mut resp = text(StatusCode::BAD_REQUEST, "bad shadow request\n");
            if let Ok(v) = HeaderValue::from_str(reason) {
                resp.headers_mut().insert("x-edge-shadow-error", v);
            }
            return resp;
        }
    };
    let Some(slot) = pool.reserve() else {
        shadow.handshake(ShadowHandshake::Overloaded);
        return overloaded();
    };
    let core = match ShadowCore::new(meta, shared.metrics.clone()) {
        Ok(core) => core,
        Err(_) => {
            shadow.handshake(ShadowHandshake::InvalidRequest);
            return text(StatusCode::BAD_REQUEST, "bad shadow request\n");
        }
    };
    shadow.handshake(ShadowHandshake::Accepted);
    let on_upgrade = hyper::upgrade::on(&mut req);
    let task_shared = shared.clone();
    // Tracked for drain, but run on the shadow runtime.
    pool.spawn(shared.sessions.track_future(async move {
        let _slot = slot;
        let Ok(upgraded) = on_upgrade.await else {
            return;
        };
        let ws =
            WebSocketStream::from_raw_socket(TokioIo::new(upgraded), Role::Server, Some(task_shared.ws_config)).await;
        shadow::serve(
            ws,
            core,
            task_shared.close_sessions.clone(),
            task_shared.cfg.close_timeout,
        )
        .await;
    }));
    switching_protocols(&key)
}

/// Compares every byte up to the longer input, so neither the position of a
/// mismatch nor a length difference returns early.
fn constant_time_eq(a: &[u8], b: &[u8]) -> bool {
    let n = a.len().max(b.len());
    let mut diff = (a.len() != b.len()) as u8;
    for i in 0..n {
        diff |= a.get(i).copied().unwrap_or(0) ^ b.get(i).copied().unwrap_or(0);
    }
    diff == 0
}

async fn proxy(mut req: Request<Incoming>, peer: SocketAddr, shared: Arc<Shared>) -> Response<Body> {
    let metrics = &shared.metrics;
    let Some(key) = upgrade_key(&req) else {
        metrics.handshake(HandshakeResult::InvalidRequest);
        return upgrade_required();
    };

    let path_and_query = req.uri().path_and_query().map(|pq| pq.as_str()).unwrap_or("/");
    let mut up_req = match format!("{}{}", shared.cfg.upstream_url, path_and_query).into_client_request() {
        Ok(r) => r,
        Err(_) => {
            metrics.handshake(HandshakeResult::InvalidRequest);
            return text(StatusCode::BAD_REQUEST, "bad request\n");
        }
    };
    for (name, value) in upstream_headers(req.headers(), peer).iter() {
        up_req.headers_mut().append(name.clone(), value.clone());
    }

    // Load shedding before any upstream work: a soft cap on open sessions
    // and a hard cap on handshakes in flight.
    if shared.metrics.sessions_active.get() >= shared.cfg.max_sessions as i64 {
        metrics.handshake(HandshakeResult::Overloaded);
        return overloaded();
    }
    let Ok(_slot) = shared.handshake_slots.clone().try_acquire_owned() else {
        metrics.handshake(HandshakeResult::Overloaded);
        return overloaded();
    };

    let connect_started = Instant::now();
    let connect = tokio_tungstenite::connect_async_with_config(up_req, Some(shared.ws_config), true);
    let (upstream, up_resp) = match tokio::time::timeout(shared.cfg.upstream_connect_timeout, connect).await {
        Ok(Ok(pair)) => pair,
        Ok(Err(WsError::Http(resp))) => {
            metrics.handshake(HandshakeResult::UpstreamRejected);
            return mirror_rejection(*resp);
        }
        Ok(Err(err)) => {
            metrics.handshake(HandshakeResult::UpstreamUnavailable);
            tracing::warn!(error = %err, "upstream connect failed");
            return text(StatusCode::BAD_GATEWAY, "upstream unavailable\n");
        }
        Err(_) => {
            metrics.handshake(HandshakeResult::UpstreamTimeout);
            return text(StatusCode::GATEWAY_TIMEOUT, "upstream timeout\n");
        }
    };
    metrics
        .upstream_connect_seconds
        .observe(connect_started.elapsed().as_secs_f64());

    let mut resp = switching_protocols(&key);
    if let Some(proto) = up_resp.headers().get(header::SEC_WEBSOCKET_PROTOCOL) {
        resp.headers_mut().insert(header::SEC_WEBSOCKET_PROTOCOL, proto.clone());
    }

    let id = shared.next_id.fetch_add(1, Ordering::Relaxed);
    let on_upgrade = hyper::upgrade::on(&mut req);
    let task_shared = shared.clone();
    shared.sessions.spawn(async move {
        let upgraded = match on_upgrade.await {
            Ok(u) => u,
            Err(_) => {
                task_shared.metrics.handshake(HandshakeResult::ClientUpgradeFailed);
                // Mirror: the client never connected, so upstream sees a drop.
                drop(upstream);
                return;
            }
        };
        task_shared.metrics.handshake(HandshakeResult::Accepted);
        let client =
            WebSocketStream::from_raw_socket(TokioIo::new(upgraded), Role::Server, Some(task_shared.ws_config)).await;
        let ctx = SessionCtx {
            id,
            close_timeout: task_shared.cfg.close_timeout,
            drain: task_shared.close_sessions.clone(),
            drain_jitter: drain_jitter(id, task_shared.cfg.drain_spread),
            metrics: task_shared.metrics.clone(),
        };
        relay(client, upstream, ctx).await;
    });
    resp
}

/// Relay an upstream handshake rejection: same status, body and the
/// headers a client may act on.
fn mirror_rejection(resp: hyper::Response<Option<Vec<u8>>>) -> Response<Body> {
    let (parts, body) = resp.into_parts();
    let mut out = Response::new(Full::new(Bytes::from(body.unwrap_or_default())));
    *out.status_mut() = parts.status;
    for name in [header::CONTENT_TYPE, header::WWW_AUTHENTICATE, header::RETRY_AFTER] {
        for v in parts.headers.get_all(&name) {
            out.headers_mut().append(name.clone(), v.clone());
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn hop_by_hop_headers_are_stripped_and_xff_appended() {
        let mut h = HeaderMap::new();
        h.insert("host", HeaderValue::from_static("edge"));
        h.insert("connection", HeaderValue::from_static("Upgrade"));
        h.insert("upgrade", HeaderValue::from_static("websocket"));
        h.insert("sec-websocket-key", HeaderValue::from_static("abc"));
        h.insert("sec-websocket-version", HeaderValue::from_static("13"));
        h.insert(
            "sec-websocket-extensions",
            HeaderValue::from_static("permessage-deflate"),
        );
        h.insert("authorization", HeaderValue::from_static("Bearer t"));
        h.insert("x-app-version", HeaderValue::from_static("1.0.500"));
        h.insert("x-forwarded-for", HeaderValue::from_static("203.0.113.9"));
        let out = upstream_headers(&h, "10.0.0.7:5555".parse().unwrap());
        assert_eq!(out.get("authorization").unwrap(), "Bearer t");
        assert_eq!(out.get("x-app-version").unwrap(), "1.0.500");
        assert_eq!(out.get("x-forwarded-for").unwrap(), "203.0.113.9, 10.0.0.7");
        for name in HOP_BY_HOP {
            assert!(out.get(*name).is_none(), "{name} forwarded");
        }
    }

    #[test]
    fn token_compare_checks_length_and_every_byte() {
        assert!(constant_time_eq(b"s3cret", b"s3cret"));
        assert!(!constant_time_eq(b"s3cret", b"s3creT"));
        assert!(!constant_time_eq(b"s3cret", b"s3cret\0"));
        assert!(!constant_time_eq(b"", b"x"));
        assert!(constant_time_eq(b"", b""));
    }

    #[test]
    fn upgrade_token_match_is_case_insensitive_and_list_aware() {
        let mut h = HeaderMap::new();
        h.insert("connection", HeaderValue::from_static("keep-alive, Upgrade"));
        assert!(header_has_token(&h, header::CONNECTION, "upgrade"));
        assert!(!header_has_token(&h, header::CONNECTION, "close"));
    }
}
