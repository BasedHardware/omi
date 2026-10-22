//! Integration tests: client <-> listen-edge <-> FakeListen over real sockets.
mod common;

use std::time::Duration;

use common::*;
use futures_util::{SinkExt, StreamExt};
use tokio_tungstenite::tungstenite::client::IntoClientRequest;
use tokio_tungstenite::tungstenite::protocol::frame::coding::CloseCode;
use tokio_tungstenite::tungstenite::protocol::CloseFrame;
use tokio_tungstenite::tungstenite::{Error as WsError, Message};

const WAIT: Duration = Duration::from_secs(10);

fn sent_message(i: usize) -> Message {
    if i.is_multiple_of(10) {
        Message::text(format!("t{i}"))
    } else {
        Message::binary(payload(i))
    }
}

async fn connect(
    edge: &omi_edge::server::Edge,
    query: &str,
) -> tokio_tungstenite::WebSocketStream<tokio_tungstenite::MaybeTlsStream<tokio::net::TcpStream>> {
    let url = format!("ws://{}/v4/listen?{}", edge.local_addr(), query);
    tokio_tungstenite::connect_async(url)
        .await
        .expect("connect through edge")
        .0
}

/// Send `n` messages and read `n` echoes concurrently; return the echoes.
async fn round_trip(edge: &omi_edge::server::Edge, conn: &str, n: usize) -> (Vec<Message>, Vec<Message>) {
    let ws = connect(edge, &format!("conn={conn}")).await;
    let (mut tx, mut rx) = ws.split();
    let reader = tokio::spawn(async move {
        let mut got = Vec::with_capacity(n);
        while got.len() < n {
            match rx.next().await {
                Some(Ok(m @ (Message::Binary(_) | Message::Text(_)))) => got.push(m),
                Some(Ok(_)) => {}
                other => panic!("stream ended early: {other:?}"),
            }
        }
        (got, rx)
    });
    let sent: Vec<Message> = (0..n).map(sent_message).collect();
    for m in &sent {
        tx.send(m.clone()).await.unwrap();
    }
    let (got, rx) = tokio::time::timeout(WAIT, reader).await.unwrap().unwrap();
    let mut ws = tx.reunite(rx).unwrap();
    ws.close(None).await.unwrap();
    while let Some(Ok(_)) = ws.next().await {}
    (sent, got)
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn passthrough_is_lossless_and_ordered_both_ways() {
    let fake = FakeListen::start().await;
    let edge = start_edge(test_config(&fake.url())).await;

    let (sent, echoed) = round_trip(&edge, "single", 3000).await;
    assert_eq!(echoed, sent, "upstream -> client stream differs");
    let rec = fake.wait_ended("single", WAIT).await;
    assert_eq!(rec.received, sent, "client -> upstream stream differs");

    let m = edge.metrics().render();
    assert_eq!(
        sample(
            &m,
            "omi_edge_frames_total{direction=\"client_to_upstream\",kind=\"binary\"}"
        ),
        2700.0
    );
    assert_eq!(
        sample(
            &m,
            "omi_edge_frames_total{direction=\"client_to_upstream\",kind=\"text\"}"
        ),
        300.0
    );
    let bytes: usize = sent
        .iter()
        .map(|m| match m {
            Message::Binary(b) => b.len(),
            Message::Text(t) => t.len(),
            _ => 0,
        })
        .sum();
    assert_eq!(
        sample(&m, "omi_edge_bytes_total{direction=\"client_to_upstream\"}"),
        bytes as f64
    );
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn concurrent_sessions_do_not_interleave() {
    let fake = FakeListen::start().await;
    let edge = std::sync::Arc::new(start_edge(test_config(&fake.url())).await);
    let mut set = tokio::task::JoinSet::new();
    for s in 0..32 {
        let edge = edge.clone();
        set.spawn(async move {
            let conn = format!("c{s}");
            let (sent, echoed) = round_trip(&edge, &conn, 300).await;
            assert_eq!(echoed, sent, "{conn}: echo stream differs");
            (conn, sent)
        });
    }
    while let Some(r) = set.join_next().await {
        let (conn, sent) = r.unwrap();
        assert_eq!(
            fake.wait_ended(&conn, WAIT).await.received,
            sent,
            "{conn}: upstream stream differs"
        );
    }
    wait_metric(
        &edge.metrics(),
        "omi_edge_sessions_total{outcome=\"client_closed\"}",
        32.0,
    )
    .await;
    wait_metric_eq(&edge.metrics(), "omi_edge_sessions_active", 0.0).await;
    assert_eq!(sample(&edge.metrics().render(), "omi_edge_sessions_active"), 0.0);
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn upstream_messages_sent_first_arrive_in_order() {
    let fake = FakeListen::start().await;
    let edge = start_edge(test_config(&fake.url())).await;
    let mut ws = connect(&edge, "conn=flood&flood=500&echo=0").await;
    for i in 0..500 {
        let m = tokio::time::timeout(WAIT, ws.next()).await.unwrap().unwrap().unwrap();
        assert_eq!(m, Message::text(format!("u{i}")));
    }
    ws.close(None).await.unwrap();
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn client_close_code_and_reason_reach_upstream() {
    let fake = FakeListen::start().await;
    let edge = start_edge(test_config(&fake.url())).await;
    let mut ws = connect(&edge, "conn=cc").await;
    ws.send(Message::binary(vec![1, 2, 3])).await.unwrap();
    let frame = CloseFrame {
        code: CloseCode::from(4001),
        reason: "bye".into(),
    };
    ws.close(Some(frame.clone())).await.unwrap();
    let mut echo = None;
    while let Some(Ok(m)) = ws.next().await {
        if let Message::Close(f) = m {
            echo = Some(f);
        }
    }
    assert_eq!(echo, Some(Some(frame.clone())), "client did not get its close echo");
    let rec = fake.wait_ended("cc", WAIT).await;
    assert_eq!(rec.close, Some(Some(frame)));
    assert_eq!(rec.received, vec![Message::binary(vec![1, 2, 3])]);
    wait_metric(
        &edge.metrics(),
        "omi_edge_sessions_total{outcome=\"client_closed\"}",
        1.0,
    )
    .await;
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn upstream_close_code_and_reason_reach_client() {
    let fake = FakeListen::start().await;
    let edge = start_edge(test_config(&fake.url())).await;
    let mut ws = connect(&edge, "conn=uc&close_after=3&code=1008&reason=Bad%20uid").await;
    for i in 0..3u8 {
        ws.send(Message::binary(vec![i])).await.unwrap();
    }
    let mut got = Vec::new();
    while let Some(Ok(m)) = tokio::time::timeout(WAIT, ws.next()).await.unwrap() {
        got.push(m);
    }
    assert_eq!(
        got,
        vec![
            Message::binary(vec![0]),
            Message::binary(vec![1]),
            Message::binary(vec![2]),
            Message::Close(Some(CloseFrame {
                code: CloseCode::Policy,
                reason: "Bad uid".into()
            })),
        ]
    );
    let rec = fake.wait_ended("uc", WAIT).await;
    // The upstream got the close echo relayed from the client.
    assert_eq!(
        rec.close,
        Some(Some(CloseFrame {
            code: CloseCode::Policy,
            reason: "Bad uid".into()
        }))
    );
    wait_metric(
        &edge.metrics(),
        "omi_edge_sessions_total{outcome=\"upstream_closed\"}",
        1.0,
    )
    .await;
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn upstream_handshake_rejection_is_mirrored() {
    let fake = FakeListen::start().await;
    let edge = start_edge(test_config(&fake.url())).await;
    let url = format!("ws://{}/v4/listen?conn=rej&reject=403", edge.local_addr());
    match tokio_tungstenite::connect_async(url).await {
        Err(WsError::Http(resp)) => {
            assert_eq!(resp.status().as_u16(), 403);
            assert_eq!(resp.body().as_deref(), Some(&b"rejected by fake listen"[..]));
        }
        other => panic!("expected HTTP 403, got {other:?}"),
    }
    let m = edge.metrics().render();
    assert_eq!(
        sample(&m, "omi_edge_handshakes_total{result=\"upstream_rejected\"}"),
        1.0
    );
    assert_eq!(sample(&m, "omi_edge_handshakes_total{result=\"accepted\"}"), 0.0);
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn upstream_down_returns_502() {
    // Bind and drop a listener to get a port nothing listens on.
    let port = tokio::net::TcpListener::bind("127.0.0.1:0")
        .await
        .unwrap()
        .local_addr()
        .unwrap()
        .port();
    let edge = start_edge(test_config(&format!("ws://127.0.0.1:{port}"))).await;
    let url = format!("ws://{}/v4/listen?conn=down", edge.local_addr());
    match tokio_tungstenite::connect_async(url).await {
        Err(WsError::Http(resp)) => assert_eq!(resp.status().as_u16(), 502),
        other => panic!("expected HTTP 502, got {other:?}"),
    }
    assert_eq!(
        sample(
            &edge.metrics().render(),
            "omi_edge_handshakes_total{result=\"upstream_unavailable\"}"
        ),
        1.0
    );
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn upstream_drop_is_mirrored_to_client_without_close_frame() {
    let fake = FakeListen::start().await;
    let edge = start_edge(test_config(&fake.url())).await;
    let mut ws = connect(&edge, "conn=ud&drop_after=2").await;
    ws.send(Message::binary(vec![1])).await.unwrap();
    ws.send(Message::binary(vec![2])).await.unwrap();
    let mut got = Vec::new();
    // Ends with an error or end of stream; either way no close frame.
    while let Some(Ok(m)) = tokio::time::timeout(WAIT, ws.next()).await.unwrap() {
        got.push(m);
    }
    assert!(
        !got.iter().any(|m| matches!(m, Message::Close(_))),
        "client got a close frame: {got:?}"
    );
    assert_eq!(got, vec![Message::binary(vec![1]), Message::binary(vec![2])]);
    wait_metric(
        &edge.metrics(),
        "omi_edge_sessions_total{outcome=\"upstream_dropped\"}",
        1.0,
    )
    .await;
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn client_drop_is_mirrored_to_upstream_without_close_frame() {
    let fake = FakeListen::start().await;
    let edge = start_edge(test_config(&fake.url())).await;
    let mut ws = connect(&edge, "conn=cd&echo=0").await;
    for i in 0..5u8 {
        ws.send(Message::binary(vec![i])).await.unwrap();
    }
    drop(ws);
    let rec = fake.wait_ended("cd", WAIT).await;
    assert_eq!(rec.close, None, "upstream got a close frame");
    assert_eq!(
        rec.received,
        (0..5u8).map(|i| Message::binary(vec![i])).collect::<Vec<_>>()
    );
    wait_metric(
        &edge.metrics(),
        "omi_edge_sessions_total{outcome=\"client_dropped\"}",
        1.0,
    )
    .await;
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn path_query_and_headers_reach_upstream() {
    let fake = FakeListen::start().await;
    let edge = start_edge(test_config(&fake.url())).await;
    let url = format!(
        "ws://{}/v4/listen?conn=hdr&language=en&codec=opus&sample_rate=16000",
        edge.local_addr()
    );
    let mut req = url.into_client_request().unwrap();
    req.headers_mut()
        .insert("authorization", "Bearer test-token".parse().unwrap());
    req.headers_mut().insert("x-app-version", "1.0.530".parse().unwrap());
    let (mut ws, _) = tokio_tungstenite::connect_async(req).await.unwrap();
    ws.close(None).await.unwrap();
    while let Some(Ok(_)) = ws.next().await {}
    let rec = fake.wait_ended("hdr", WAIT).await;
    assert_eq!(
        rec.path_and_query,
        "/v4/listen?conn=hdr&language=en&codec=opus&sample_rate=16000"
    );
    assert_eq!(rec.header("authorization"), Some("Bearer test-token"));
    assert_eq!(rec.header("x-app-version"), Some("1.0.530"));
    assert_eq!(rec.header("x-forwarded-for"), Some("127.0.0.1"));
    assert_eq!(rec.headers.iter().filter(|(k, _)| k == "sec-websocket-key").count(), 1);
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn close_handshake_timeout_tears_down() {
    let fake = FakeListen::start().await;
    let edge = start_edge(test_config(&fake.url())).await;
    let mut ws = connect(&edge, "conn=mute&mute=1").await;
    ws.close(None).await.unwrap();
    while let Some(Ok(_)) = ws.next().await {}
    // close_timeout is 1s in the test config, plus up to 1s abort grace.
    wait_metric(
        &edge.metrics(),
        "omi_edge_sessions_total{outcome=\"close_timeout\"}",
        1.0,
    )
    .await;
    wait_metric_eq(&edge.metrics(), "omi_edge_sessions_active", 0.0).await;
}

/// Found by the real-listen smoke: listen keeps its TCP socket open after
/// the close handshake while it finalizes. The edge must finish on the
/// handshake, not on TCP EOF (close_timeout is 1s in the test config).
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn close_completes_while_upstream_keeps_tcp_open() {
    let fake = FakeListen::start().await;
    let edge = start_edge(test_config(&fake.url())).await;
    let fast = Duration::from_millis(800);

    let mut ws = connect(&edge, "conn=lc&linger=1").await;
    let t0 = std::time::Instant::now();
    ws.close(Some(CloseFrame {
        code: CloseCode::Normal,
        reason: "done".into(),
    }))
    .await
    .unwrap();
    while let Some(Ok(_)) = ws.next().await {}
    wait_metric(
        &edge.metrics(),
        "omi_edge_sessions_total{outcome=\"client_closed\"}",
        1.0,
    )
    .await;
    assert!(t0.elapsed() < fast, "client close took {:?}", t0.elapsed());

    let mut ws = connect(&edge, "conn=lu&linger=1&close_after=1&code=1000&reason=bye").await;
    let t0 = std::time::Instant::now();
    ws.send(Message::binary(vec![9])).await.unwrap();
    while let Some(Ok(_)) = ws.next().await {}
    wait_metric(
        &edge.metrics(),
        "omi_edge_sessions_total{outcome=\"upstream_closed\"}",
        1.0,
    )
    .await;
    assert!(t0.elapsed() < fast, "upstream close took {:?}", t0.elapsed());

    let m = edge.metrics().render();
    assert_eq!(sample(&m, "omi_edge_sessions_total{outcome=\"close_timeout\"}"), 0.0);
    assert_eq!(
        fake.record("lc").await.unwrap().close.unwrap().unwrap().reason.as_str(),
        "done"
    );
}

/// Review finding: no unbounded sessions or handshakes.
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn session_cap_sheds_with_503() {
    let fake = FakeListen::start().await;
    let edge = start_edge(test_config_with(&fake.url(), &[("EDGE_MAX_SESSIONS", "1")])).await;
    let mut first = connect(&edge, "conn=cap1").await;
    wait_metric(&edge.metrics(), "omi_edge_sessions_active", 1.0).await;
    let url = format!("ws://{}/v4/listen?conn=cap2", edge.local_addr());
    match tokio_tungstenite::connect_async(url).await {
        Err(WsError::Http(resp)) => assert_eq!(resp.status().as_u16(), 503),
        other => panic!("expected HTTP 503, got {other:?}"),
    }
    assert!(fake.record("cap2").await.is_none(), "shed request reached upstream");
    assert_eq!(
        sample(
            &edge.metrics().render(),
            "omi_edge_handshakes_total{result=\"overloaded\"}"
        ),
        1.0
    );
    first.close(None).await.unwrap();
}

/// Review finding: a client that never finishes its request headers is cut
/// off by the header read timeout instead of holding a task forever.
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn slow_headers_are_timed_out() {
    use tokio::io::{AsyncReadExt, AsyncWriteExt};
    let fake = FakeListen::start().await;
    let edge = start_edge(test_config_with(&fake.url(), &[("EDGE_HEADER_READ_TIMEOUT_MS", "300")])).await;
    let mut s = tokio::net::TcpStream::connect(edge.local_addr()).await.unwrap();
    s.write_all(b"GET /v4/listen HTTP/1.1\r\nHost: edge\r\n").await.unwrap();
    let mut buf = Vec::new();
    // The edge closes the socket (with or without a 408) well before 5s.
    let read = tokio::time::timeout(Duration::from_secs(5), s.read_to_end(&mut buf)).await;
    assert!(read.is_ok(), "slow-header connection was not closed");
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn health_ready_metrics_and_routing() {
    let fake = FakeListen::start().await;
    let edge = start_edge(test_config(&fake.url())).await;
    let addr = edge.local_addr();
    assert_eq!(http_get(addr, "/healthz").await.0, 200);
    assert_eq!(http_get(addr, "/readyz").await.0, 200);
    let (status, body) = http_get(addr, "/metrics").await;
    assert_eq!(status, 200);
    assert!(body.contains("omi_edge_sessions_active 0"));
    assert!(body.contains("omi_edge_build_info{release_sha=\"0123456789ab\"} 1"));
    assert_eq!(http_get(addr, "/nope").await.0, 404);
    assert_eq!(http_get(addr, "/v4/listen").await.0, 426);
    assert_eq!(
        sample(
            &edge.metrics().render(),
            "omi_edge_handshakes_total{result=\"invalid_request\"}"
        ),
        1.0
    );
}
