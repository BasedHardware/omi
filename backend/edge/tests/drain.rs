//! Drain: SIGTERM-equivalent `Edge::drain()` with live sessions streaming.
//!
//! Proves the property the gateway exists for: a deploy hands sockets back
//! with a clean close (1012) and drops no frame the client sent before it
//! saw that close.
mod common;

use std::time::{Duration, Instant};

use common::*;
use futures_util::{SinkExt, StreamExt};
use omi_edge::session::DRAIN_CLOSE_REASON;
use tokio_tungstenite::tungstenite::protocol::frame::coding::CloseCode;
use tokio_tungstenite::tungstenite::protocol::CloseFrame;
use tokio_tungstenite::tungstenite::Message;

const SESSIONS: usize = 16;

/// Stream sequence-numbered frames until the edge closes; return how many
/// sends succeeded and the close frame received.
async fn stream_until_closed(addr: std::net::SocketAddr, conn: String) -> (String, u32, Option<CloseFrame>) {
    let url = format!("ws://{addr}/v4/listen?conn={conn}");
    let (ws, _) = tokio_tungstenite::connect_async(url).await.unwrap();
    let (mut tx, mut rx) = ws.split();
    let (close_tx, mut close_rx) = tokio::sync::oneshot::channel::<Option<CloseFrame>>();
    let reader = tokio::spawn(async move {
        let mut close_tx = Some(close_tx);
        let mut frame = None;
        while let Some(Ok(m)) = rx.next().await {
            if let Message::Close(f) = m {
                frame = f.clone();
                if let Some(c) = close_tx.take() {
                    let _ = c.send(f);
                }
            }
        }
        frame
    });
    let mut seq: u32 = 0;
    loop {
        if close_rx.try_recv().is_ok() {
            break;
        }
        // 20 ms Opus-sized frame stand-in, sent every 2 ms to keep frames in flight.
        let mut body = seq.to_be_bytes().to_vec();
        body.extend(std::iter::repeat_n(0xA5u8, 70));
        if tx.send(Message::binary(body)).await.is_err() {
            break;
        }
        seq += 1;
        tokio::time::sleep(Duration::from_millis(2)).await;
    }
    let frame = tokio::time::timeout(Duration::from_secs(10), reader)
        .await
        .unwrap()
        .unwrap();
    (conn, seq, frame)
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn drain_closes_with_1012_and_relays_every_inflight_frame() {
    let fake = FakeListen::start().await;
    let cfg = test_config(&fake.url());
    let deadline = cfg.drain_deadline();
    let edge = start_edge(cfg).await;
    let addr = edge.local_addr();
    let metrics = edge.metrics();

    let mut clients = tokio::task::JoinSet::new();
    for i in 0..SESSIONS {
        clients.spawn(stream_until_closed(addr, format!("d{i}")));
    }
    // Let every session stream for a while.
    wait_metric(&metrics, "omi_edge_sessions_active", SESSIONS as f64).await;
    tokio::time::sleep(Duration::from_millis(150)).await;

    let drain_started = Instant::now();
    let drain = tokio::spawn(edge.drain());

    // Readiness flips at once; liveness stays up; new sockets still accepted
    // during the deregistration delay.
    tokio::time::sleep(Duration::from_millis(50)).await;
    assert_eq!(http_get(addr, "/readyz").await.0, 503);
    assert_eq!(http_get(addr, "/healthz").await.0, 200);
    assert_eq!(sample(&metrics.render(), "omi_edge_draining"), 1.0);
    let late = stream_until_closed(addr, "late".to_string());
    clients.spawn(late);

    let mut results = Vec::new();
    while let Some(r) = clients.join_next().await {
        results.push(r.unwrap());
    }
    drain.await.unwrap();
    assert!(
        drain_started.elapsed() < deadline,
        "drain took {:?}",
        drain_started.elapsed()
    );

    let expected_close = CloseFrame {
        code: CloseCode::Restart,
        reason: DRAIN_CLOSE_REASON.into(),
    };
    for (conn, sent, close) in results {
        assert_eq!(close.as_ref(), Some(&expected_close), "{conn}: client close frame");
        assert!(sent > 0, "{conn}: nothing streamed");
        let rec = fake.wait_ended(&conn, Duration::from_secs(10)).await;
        let seqs: Vec<u32> = rec
            .received
            .iter()
            .map(|m| match m {
                Message::Binary(b) => u32::from_be_bytes(b[..4].try_into().unwrap()),
                other => panic!("{conn}: unexpected {other:?}"),
            })
            .collect();
        assert_eq!(
            seqs,
            (0..sent).collect::<Vec<_>>(),
            "{conn}: upstream missed or reordered frames"
        );
        // Listen sees a normal client close carrying the edge's 1012.
        assert_eq!(
            rec.close,
            Some(Some(expected_close.clone())),
            "{conn}: upstream close frame"
        );
    }

    let m = metrics.render();
    assert_eq!(
        sample(&m, "omi_edge_sessions_total{outcome=\"drained\"}"),
        (SESSIONS + 1) as f64
    );
    assert_eq!(sample(&m, "omi_edge_sessions_active"), 0.0);
    // The listener is closed after drain.
    assert!(
        tokio::net::TcpStream::connect(addr).await.is_err(),
        "edge still accepting after drain"
    );
}

/// Found by the real-listen smoke: some clients drop TCP on the drain close
/// without echoing it. Listen must still get a clean 1012 close, not a drop.
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn drain_gives_listen_a_clean_close_when_client_vanishes() {
    let fake = FakeListen::start().await;
    let edge = start_edge(test_config(&fake.url())).await;
    let metrics = edge.metrics();
    let url = format!("ws://{}/v4/listen?conn=gone&echo=0", edge.local_addr());
    let (mut ws, _) = tokio_tungstenite::connect_async(url).await.unwrap();
    for i in 0..3u8 {
        ws.send(Message::binary(vec![i])).await.unwrap();
    }
    let drain = tokio::spawn(edge.drain());
    loop {
        match tokio::time::timeout(Duration::from_secs(5), ws.next()).await.unwrap() {
            Some(Ok(Message::Close(_))) => break,
            Some(Ok(_)) => {}
            other => panic!("no drain close: {other:?}"),
        }
    }
    // Drop without polling again, so the queued close echo is never sent.
    drop(ws);
    let rec = fake.wait_ended("gone", Duration::from_secs(10)).await;
    assert_eq!(
        rec.close,
        Some(Some(CloseFrame {
            code: CloseCode::Restart,
            reason: DRAIN_CLOSE_REASON.into()
        }))
    );
    assert_eq!(
        rec.received,
        (0..3u8).map(|i| Message::binary(vec![i])).collect::<Vec<_>>()
    );
    drain.await.unwrap();
    assert_eq!(
        sample(&metrics.render(), "omi_edge_sessions_total{outcome=\"drained\"}"),
        1.0
    );
}
