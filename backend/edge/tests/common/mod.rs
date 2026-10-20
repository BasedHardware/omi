//! Test harness: `FakeListen`, a stand-in for backend-listen's `/v4/listen`
//! websocket, plus small client helpers.
//!
//! Behaviour is chosen per connection by query parameters, so one fake
//! serves every scenario:
//! - `conn=<id>` (required): key under which the connection is recorded;
//! - `reject=<status>`: fail the handshake with that HTTP status;
//! - `slow_handshake_ms=<ms>`: delay the handshake response;
//! - `flood=<n>`: send `n` text messages `u0..u{n-1}` right after accept;
//! - `echo=0`: do not echo data messages (default echoes each one back);
//! - `close_after=<n>&code=<c>&reason=<r>`: after `n` data messages, start a
//!   close handshake with that code and reason;
//! - `drop_after=<n>`: after `n` data messages, drop TCP without a close frame;
//! - `mute=1`: complete the handshake, then never read or write again;
//! - `blob=<n>`: send `n` 64 KiB binary messages from a separate writer
//!   while still reading (fills the path to a client that stops reading);
//! - `linger=1`: after the close handshake, keep the TCP socket open for 30s
//!   (listen holds its socket while it finalizes).
#![allow(dead_code)]

use std::collections::HashMap;
use std::net::SocketAddr;
use std::sync::Arc;
use std::time::Duration;

use futures_util::{SinkExt, StreamExt};
use omi_edge::config::Config;
use omi_edge::metrics::Metrics;
use omi_edge::server::{start_with_listener, Edge};
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::{TcpListener, TcpStream};
use tokio::sync::{Mutex, Notify};
use tokio_tungstenite::tungstenite::handshake::server::{ErrorResponse, Request, Response};
use tokio_tungstenite::tungstenite::http::StatusCode;
use tokio_tungstenite::tungstenite::protocol::frame::coding::CloseCode;
use tokio_tungstenite::tungstenite::protocol::CloseFrame;
use tokio_tungstenite::tungstenite::Message;

#[derive(Clone, Debug, Default)]
pub struct ConnRecord {
    pub path_and_query: String,
    pub headers: Vec<(String, String)>,
    /// Data messages received, in order.
    pub received: Vec<Message>,
    /// `Some(frame)` once a close frame arrived from the edge.
    pub close: Option<Option<CloseFrame>>,
    pub ended: bool,
}

impl ConnRecord {
    pub fn header(&self, name: &str) -> Option<&str> {
        self.headers.iter().find(|(k, _)| k == name).map(|(_, v)| v.as_str())
    }
}

#[derive(Default)]
struct State {
    conns: Mutex<HashMap<String, ConnRecord>>,
    notify: Notify,
}

pub struct FakeListen {
    pub addr: SocketAddr,
    state: Arc<State>,
}

pub fn query_map(pq: &str) -> HashMap<String, String> {
    pq.split_once('?')
        .map(|(_, q)| q)
        .unwrap_or("")
        .split('&')
        .filter_map(|kv| kv.split_once('='))
        .map(|(k, v)| (k.to_string(), v.replace("%20", " ")))
        .collect()
}

impl FakeListen {
    pub async fn start() -> FakeListen {
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let addr = listener.local_addr().unwrap();
        let state = Arc::new(State::default());
        let st = state.clone();
        tokio::spawn(async move {
            loop {
                let Ok((stream, _)) = listener.accept().await else {
                    continue;
                };
                tokio::spawn(serve_conn(stream, st.clone()));
            }
        });
        FakeListen { addr, state }
    }

    pub fn url(&self) -> String {
        format!("ws://{}", self.addr)
    }

    pub async fn record(&self, conn: &str) -> Option<ConnRecord> {
        self.state.conns.lock().await.get(conn).cloned()
    }

    /// Wait until the connection has ended (TCP closed) and return its record.
    pub async fn wait_ended(&self, conn: &str, timeout: Duration) -> ConnRecord {
        let deadline = tokio::time::Instant::now() + timeout;
        loop {
            let notified = self.state.notify.notified();
            tokio::pin!(notified);
            notified.as_mut().enable();
            if let Some(r) = self.record(conn).await {
                if r.ended {
                    return r;
                }
            }
            if tokio::time::timeout_at(deadline, notified).await.is_err() {
                panic!(
                    "fake upstream conn {conn} did not end within {timeout:?}: {:?}",
                    self.record(conn).await
                );
            }
        }
    }
}

async fn update(state: &State, conn: &str, f: impl FnOnce(&mut ConnRecord)) {
    let mut conns = state.conns.lock().await;
    f(conns.entry(conn.to_string()).or_default());
    drop(conns);
    state.notify.notify_waiters();
}

/// Path-and-query plus headers seen in the handshake.
type Handshake = (String, Vec<(String, String)>);

#[allow(clippy::result_large_err)] // the error type is tungstenite's callback contract
async fn serve_conn(stream: TcpStream, state: Arc<State>) {
    let captured: Arc<std::sync::Mutex<Option<Handshake>>> = Default::default();
    let cap = captured.clone();
    let callback = move |req: &Request, resp: Response| -> Result<Response, ErrorResponse> {
        let pq = req
            .uri()
            .path_and_query()
            .map(|p| p.as_str().to_string())
            .unwrap_or_default();
        let headers = req
            .headers()
            .iter()
            .map(|(k, v)| (k.as_str().to_string(), v.to_str().unwrap_or("").to_string()))
            .collect();
        let q = query_map(&pq);
        *cap.lock().unwrap() = Some((pq, headers));
        if let Some(status) = q.get("reject") {
            let mut err = ErrorResponse::new(Some("rejected by fake listen".to_string()));
            *err.status_mut() = StatusCode::from_u16(status.parse().unwrap()).unwrap();
            err.headers_mut().insert("content-type", "text/plain".parse().unwrap());
            return Err(err);
        }
        Ok(resp)
    };
    // `slow_handshake_ms`: peek at the request line and wait before answering
    // (the handshake callback itself is synchronous and must not block).
    let mut head = [0u8; 512];
    let n = stream.peek(&mut head).await.unwrap_or(0);
    let line = String::from_utf8_lossy(&head[..n])
        .lines()
        .next()
        .unwrap_or("")
        .to_string();
    if let Some(ms) = query_map(line.split(' ').nth(1).unwrap_or(""))
        .get("slow_handshake_ms")
        .and_then(|v| v.parse::<u64>().ok())
    {
        tokio::time::sleep(Duration::from_millis(ms)).await;
    }
    let ws = tokio_tungstenite::accept_hdr_async(stream, callback).await;
    let Some((pq, headers)) = captured.lock().unwrap().take() else {
        return;
    };
    let q = query_map(&pq);
    let conn = q.get("conn").cloned().unwrap_or_default();
    let Ok(mut ws) = ws else {
        update(&state, &conn, |r| {
            r.path_and_query = pq;
            r.headers = headers;
            r.ended = true;
        })
        .await;
        return;
    };
    update(&state, &conn, |r| {
        r.path_and_query = pq.clone();
        r.headers = headers;
    })
    .await;

    if q.get("mute").map(String::as_str) == Some("1") {
        tokio::time::sleep(Duration::from_secs(30)).await;
        return;
    }

    let num = |k: &str| q.get(k).and_then(|v| v.parse::<usize>().ok());

    if let Some(n) = num("blob") {
        // Write n x 64 KiB from a separate task (it blocks once the path
        // back to a non-reading client is full) while still reading, so a
        // close from the edge is recorded.
        let (mut tx, mut rx) = ws.split();
        let writer = tokio::spawn(async move {
            for _ in 0..n {
                if tx.send(Message::binary(vec![0u8; 64 * 1024])).await.is_err() {
                    break;
                }
            }
        });
        while let Some(Ok(msg)) = rx.next().await {
            if let Message::Close(f) = msg {
                update(&state, &conn, |r| r.close = Some(f.clone())).await;
            }
        }
        writer.abort();
        update(&state, &conn, |r| r.ended = true).await;
        return;
    }

    let echo = q.get("echo").map(String::as_str) != Some("0");
    let close_after = num("close_after");
    let drop_after = num("drop_after");

    if let Some(n) = num("flood") {
        for i in 0..n {
            if ws.send(Message::text(format!("u{i}"))).await.is_err() {
                break;
            }
        }
    }

    let mut count = 0usize;
    while let Some(msg) = ws.next().await {
        let Ok(msg) = msg else { break };
        match msg {
            Message::Binary(_) | Message::Text(_) => {
                count += 1;
                update(&state, &conn, |r| r.received.push(msg.clone())).await;
                if echo {
                    let _ = ws.send(msg).await;
                }
                if drop_after == Some(count) {
                    // Drop the TCP stream without a close frame.
                    update(&state, &conn, |r| r.ended = true).await;
                    return;
                }
                if close_after == Some(count) {
                    let code: u16 = num("code").unwrap_or(1000) as u16;
                    let reason = q.get("reason").cloned().unwrap_or_default();
                    let _ = ws
                        .close(Some(CloseFrame {
                            code: CloseCode::from(code),
                            reason: reason.into(),
                        }))
                        .await;
                }
            }
            Message::Close(f) => {
                update(&state, &conn, |r| r.close = Some(f.clone())).await;
            }
            _ => {}
        }
    }
    update(&state, &conn, |r| r.ended = true).await;
    if q.get("linger").map(String::as_str) == Some("1") {
        // Like listen finalizing: the close handshake is done but the TCP
        // socket stays open until the handler returns.
        tokio::time::sleep(Duration::from_secs(30)).await;
        drop(ws);
    }
}

/// Edge config for tests: fast drain, short timeouts.
pub fn test_config(upstream_url: &str) -> Config {
    test_config_with(upstream_url, &[])
}

/// `test_config` plus env overrides.
pub fn test_config_with(upstream_url: &str, extra: &[(&str, &str)]) -> Config {
    let upstream_url = upstream_url.to_string();
    let extra: HashMap<String, String> = extra.iter().map(|(k, v)| (k.to_string(), v.to_string())).collect();
    Config::from_lookup(|k| match k {
        _ if extra.contains_key(k) => extra.get(k).cloned(),
        "EDGE_UPSTREAM_URL" => Some(upstream_url.clone()),
        "EDGE_LISTEN_ADDR" => Some("127.0.0.1:0".into()),
        "EDGE_UPSTREAM_CONNECT_TIMEOUT_MS" => Some("2000".into()),
        "EDGE_DRAIN_READY_DELAY_MS" => Some("300".into()),
        "EDGE_DRAIN_SPREAD_MS" => Some("200".into()),
        "EDGE_CLOSE_TIMEOUT_MS" => Some("1000".into()),
        _ => None,
    })
    .unwrap()
}

pub async fn start_edge(cfg: Config) -> Edge {
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    start_with_listener(listener, cfg, Metrics::new("0123456789abcdef"))
}

/// Minimal HTTP/1.1 GET; returns (status, body).
pub async fn http_get(addr: SocketAddr, path: &str) -> (u16, String) {
    let mut s = TcpStream::connect(addr).await.unwrap();
    s.write_all(format!("GET {path} HTTP/1.1\r\nHost: edge\r\nConnection: close\r\n\r\n").as_bytes())
        .await
        .unwrap();
    let mut buf = Vec::new();
    s.read_to_end(&mut buf).await.unwrap();
    let text = String::from_utf8_lossy(&buf).to_string();
    let status = text.split_whitespace().nth(1).unwrap().parse().unwrap();
    let body = text
        .split_once("\r\n\r\n")
        .map(|(_, b)| b.to_string())
        .unwrap_or_default();
    (status, body)
}

/// Read one sample value from Prometheus text, e.g.
/// `omi_edge_sessions_total{outcome="drained"}`.
pub fn sample(text: &str, series: &str) -> f64 {
    text.lines()
        .find_map(|l| l.strip_prefix(series).and_then(|rest| rest.trim().parse::<f64>().ok()))
        .unwrap_or_else(|| panic!("series {series} not found"))
}

/// Wait until `series` reaches at least `want` in the edge's metrics.
pub async fn wait_metric(edge_metrics: &Metrics, series: &str, want: f64) {
    let deadline = tokio::time::Instant::now() + Duration::from_secs(5);
    loop {
        let v = sample(&edge_metrics.render(), series);
        if v >= want {
            return;
        }
        if tokio::time::Instant::now() > deadline {
            panic!("{series} = {v}, wanted >= {want}");
        }
        tokio::time::sleep(Duration::from_millis(10)).await;
    }
}

/// Wait until `series` is exactly `want` (for gauges that go down).
pub async fn wait_metric_eq(edge_metrics: &Metrics, series: &str, want: f64) {
    let deadline = tokio::time::Instant::now() + Duration::from_secs(5);
    loop {
        let v = sample(&edge_metrics.render(), series);
        if v == want {
            return;
        }
        if tokio::time::Instant::now() > deadline {
            panic!("{series} = {v}, wanted {want}");
        }
        tokio::time::sleep(Duration::from_millis(10)).await;
    }
}

/// Deterministic payload for message `i`: varied sizes including empty.
pub fn payload(i: usize) -> Vec<u8> {
    let len = (i * 37) % 1500;
    (0..len).map(|j| ((i * 31 + j * 7) % 251) as u8).collect()
}
