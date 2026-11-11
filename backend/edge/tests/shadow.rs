//! D2 shadow: golden parity with listen's VAD gate, and the `/v1/shadow`
//! websocket endpoint end to end.
//!
//! `tests/fixtures/shadow/*.shadow` are mirror streams recorded from listen's
//! real gate by `backend/scripts/edge_shadow_goldens.py --write-edge-fixtures`
//! (speech fixture `backend/testing/release_fixtures/transcription-release-probe.wav`
//! between room-noise gaps): opus_fs320 at 16 kHz on the standard and window
//! profiles, and pcm8 at 8 kHz (resample + AGC) on the window profile.
mod common;

use std::sync::Arc;
use std::time::Duration;

use common::*;
use futures_util::{SinkExt, StreamExt};
use omi_edge::metrics::{Metrics, ShadowOutcome};
use omi_edge::shadow::{ShadowCore, ShadowMeta};
use tokio_tungstenite::tungstenite::client::IntoClientRequest;
use tokio_tungstenite::tungstenite::protocol::frame::coding::CloseCode;
use tokio_tungstenite::tungstenite::Message;

const SESSION: &str = "0123456789abcdef0123456789abcdef";

fn model_path() -> String {
    format!("{}/../utils/stt/assets/silero_vad.onnx", env!("CARGO_MANIFEST_DIR"))
}

fn init_model() {
    omi_edge::silero::init(&model_path()).expect("silero model loads");
}

/// (handshake query, messages) of a recorded stream.
fn fixture(name: &str) -> (String, Vec<Vec<u8>>) {
    let path = format!("{}/tests/fixtures/shadow/{name}", env!("CARGO_MANIFEST_DIR"));
    let bytes = std::fs::read(&path).unwrap_or_else(|e| panic!("{path}: {e}"));
    let mut records = Vec::new();
    let mut rest = &bytes[..];
    while !rest.is_empty() {
        let n = u32::from_be_bytes(rest[..4].try_into().unwrap()) as usize;
        records.push(rest[4..4 + n].to_vec());
        rest = &rest[4 + n..];
    }
    let query = String::from_utf8(records.remove(0)).unwrap();
    (query, records)
}

const FIXTURES: [&str; 3] = [
    "transcription-release-probe.opus_fs320_16k.standard.shadow",
    "transcription-release-probe.opus_fs320_16k.window.shadow",
    "transcription-release-probe.pcm8_8k.window.shadow",
];

#[test]
fn goldens_agree_with_listen() {
    init_model();
    for name in FIXTURES {
        let (query, messages) = fixture(name);
        let meta = ShadowMeta::from_query(&query).unwrap();
        let mut core = ShadowCore::new(meta, Arc::new(Metrics::new(""))).unwrap();
        for m in &messages {
            core.on_message(m).unwrap();
        }
        let s = core.finish(ShadowOutcome::Completed);
        assert!(s.aligned, "{name}: edge gate not aligned with listen's");
        assert_eq!((s.decode_errors, s.length_mismatches), (0, 0), "{name}");
        // Every listen window was compared (none unmatched or not comparable).
        assert_eq!(s.compare[4] + s.compare[5], 0, "{name}: {:?}", s.compare);
        assert!(s.compared() > 400, "{name}: only {} windows", s.compared());
        assert!(
            s.compare[0] > 100 && s.compare[1] > 100,
            "{name}: speech/silence {:?}",
            s.compare
        );
        let agreement = s.agreement().unwrap();
        assert!(agreement >= 0.995, "{name}: agreement {agreement}");
        assert!(s.max_prob_diff < 1e-3, "{name}: max prob diff {}", s.max_prob_diff);
        // Gate opens: same chunk on both sides.
        assert!(s.opens[0] >= 2, "{name}: opens {:?}", s.opens);
        assert_eq!((s.opens[1], s.opens[2]), (0, 0), "{name}: opens {:?}", s.opens);
        assert!(s.open_offsets_samples.iter().all(|o| *o == 0), "{name}");
    }
}

#[test]
fn repeated_window_reports_are_counted_once() {
    init_model();
    let (query, messages) = fixture(FIXTURES[0]);
    let run = |extra: bool| {
        let mut core = ShadowCore::new(ShadowMeta::from_query(&query).unwrap(), Arc::new(Metrics::new(""))).unwrap();
        for m in &messages {
            core.on_message(m).unwrap();
        }
        if extra {
            for m in messages.iter().filter(|m| m[0] == 3) {
                core.on_message(m).unwrap();
            }
        }
        core.finish(ShadowOutcome::Completed).compare
    };
    assert_eq!(run(false), run(true));
}

#[test]
fn wrong_profile_is_detected() {
    // Negative control: claim the plain variant for a window-lane (AGC)
    // stream. The edge then scores ungained audio, so its probabilities must
    // move away from listen's (the parity above is not vacuous).
    init_model();
    let (query, mut messages) = fixture("transcription-release-probe.pcm8_8k.window.shadow");
    let gate_start = messages.iter_mut().find(|m| m[0] == 2).unwrap();
    assert_eq!(gate_start[3], 1, "fixture should be the agc variant");
    gate_start[3] = 0;
    let mut core = ShadowCore::new(ShadowMeta::from_query(&query).unwrap(), Arc::new(Metrics::new(""))).unwrap();
    for m in &messages {
        core.on_message(m).unwrap();
    }
    let s = core.finish(ShadowOutcome::Completed);
    assert!(
        s.max_prob_diff > 1e-2,
        "AGC removal moved probabilities by only {}",
        s.max_prob_diff
    );
}

async fn connect_shadow(
    addr: std::net::SocketAddr,
    query: &str,
    token: Option<&str>,
) -> Result<
    tokio_tungstenite::WebSocketStream<tokio_tungstenite::MaybeTlsStream<tokio::net::TcpStream>>,
    tokio_tungstenite::tungstenite::Error,
> {
    let mut req = format!("ws://{addr}/v1/shadow?{query}").into_client_request().unwrap();
    if let Some(t) = token {
        req.headers_mut().insert("x-edge-shadow-token", t.parse().unwrap());
    }
    tokio_tungstenite::connect_async(req).await.map(|(ws, _)| ws)
}

fn http_status(err: tokio_tungstenite::tungstenite::Error) -> u16 {
    match err {
        tokio_tungstenite::tungstenite::Error::Http(resp) => resp.status().as_u16(),
        other => panic!("expected an HTTP rejection, got {other}"),
    }
}

#[tokio::test]
async fn endpoint_scores_a_mirrored_session() {
    init_model();
    let model = model_path();
    let edge = start_edge(test_config_with("ws://127.0.0.1:9", &[("EDGE_VAD_MODEL_PATH", &model)])).await;
    let (query, messages) = fixture("transcription-release-probe.opus_fs320_16k.standard.shadow");
    let mut ws = connect_shadow(edge.local_addr(), &query, None).await.unwrap();
    for m in &messages {
        ws.send(Message::binary(m.clone())).await.unwrap();
    }
    ws.close(None).await.unwrap();
    while let Some(Ok(_)) = ws.next().await {}

    let metrics = edge.metrics();
    wait_metric(&metrics, "omi_edge_shadow_sessions_total{outcome=\"completed\"}", 1.0).await;
    let text = metrics.render();
    let agree = sample(
        &text,
        "omi_edge_shadow_window_compare_total{codec=\"opus\",result=\"agree_speech\",variant=\"plain\"}",
    ) + sample(
        &text,
        "omi_edge_shadow_window_compare_total{codec=\"opus\",result=\"agree_silence\",variant=\"plain\"}",
    );
    let disagree = sample(
        &text,
        "omi_edge_shadow_window_compare_total{codec=\"opus\",result=\"edge_speech_only\",variant=\"plain\"}",
    ) + sample(
        &text,
        "omi_edge_shadow_window_compare_total{codec=\"opus\",result=\"listen_speech_only\",variant=\"plain\"}",
    );
    assert!(agree > 400.0, "agree {agree}");
    assert!(agree / (agree + disagree) >= 0.995);
    assert!(sample(&text, "omi_edge_shadow_gate_opens_total{result=\"matched\"}") >= 2.0);
    assert!(sample(&text, "omi_edge_shadow_frames_total{codec=\"opus\",result=\"decoded\"}") > 400.0);
    assert_eq!(sample(&text, "omi_edge_shadow_sessions_active"), 0.0);
    assert_eq!(
        sample(&text, "omi_edge_shadow_handshakes_total{result=\"accepted\"}"),
        1.0
    );
}

#[tokio::test]
async fn endpoint_rejects_bad_requests() {
    init_model();
    let model = model_path();
    let q = format!("v=1&codec=pcm16&sample_rate=16000&session={SESSION}");

    // No model configured: disabled.
    let edge = start_edge(test_config_with("ws://127.0.0.1:9", &[])).await;
    assert_eq!(
        http_status(connect_shadow(edge.local_addr(), &q, None).await.unwrap_err()),
        503
    );
    let text = edge.metrics().render();
    assert_eq!(
        sample(&text, "omi_edge_shadow_handshakes_total{result=\"disabled\"}"),
        1.0
    );

    let edge = start_edge(test_config_with(
        "ws://127.0.0.1:9",
        &[("EDGE_VAD_MODEL_PATH", &model), ("EDGE_SHADOW_TOKEN", "s3cret")],
    ))
    .await;
    let addr = edge.local_addr();
    assert_eq!(http_status(connect_shadow(addr, &q, None).await.unwrap_err()), 401);
    assert_eq!(
        http_status(connect_shadow(addr, &q, Some("nope")).await.unwrap_err()),
        401
    );
    for bad in [
        format!("v=1&codec=lc3&sample_rate=16000&session={SESSION}"),
        "v=1&codec=pcm16&sample_rate=16000&session=uid-like-value".to_string(),
        "v=1&codec=pcm16&sample_rate=16000".to_string(),
    ] {
        assert_eq!(
            http_status(connect_shadow(addr, &bad, Some("s3cret")).await.unwrap_err()),
            400,
            "{bad}"
        );
    }
    let text = edge.metrics().render();
    assert_eq!(
        sample(&text, "omi_edge_shadow_handshakes_total{result=\"unauthorized\"}"),
        2.0
    );
    assert_eq!(
        sample(&text, "omi_edge_shadow_handshakes_total{result=\"invalid_request\"}"),
        3.0
    );

    // A text message is a protocol error: the edge closes with 1003.
    let mut ws = connect_shadow(addr, &q, Some("s3cret")).await.unwrap();
    ws.send(Message::text("hello")).await.unwrap();
    let close = loop {
        match ws.next().await {
            Some(Ok(Message::Close(frame))) => break frame,
            Some(Ok(_)) => continue,
            other => panic!("expected close, got {other:?}"),
        }
    };
    assert_eq!(close.unwrap().code, CloseCode::Unsupported);
    wait_metric(
        &edge.metrics(),
        "omi_edge_shadow_sessions_total{outcome=\"protocol_error\"}",
        1.0,
    )
    .await;
}

#[tokio::test]
async fn shadow_sessions_close_on_drain_and_are_capped() {
    init_model();
    let model = model_path();
    let edge = start_edge(test_config_with(
        "ws://127.0.0.1:9",
        &[("EDGE_VAD_MODEL_PATH", &model), ("EDGE_SHADOW_MAX_SESSIONS", "1")],
    ))
    .await;
    let addr = edge.local_addr();
    let metrics = edge.metrics();
    let q = format!("v=1&codec=pcm16&sample_rate=16000&session={SESSION}");
    let mut first = connect_shadow(addr, &q, None).await.unwrap();
    wait_metric(&metrics, "omi_edge_shadow_sessions_active", 1.0).await;
    assert_eq!(http_status(connect_shadow(addr, &q, None).await.unwrap_err()), 503);

    let drained = tokio::spawn(edge.drain());
    let close = tokio::time::timeout(Duration::from_secs(5), async {
        loop {
            match first.next().await {
                Some(Ok(Message::Close(frame))) => break frame,
                Some(Ok(_)) => continue,
                other => panic!("expected close, got {other:?}"),
            }
        }
    })
    .await
    .unwrap();
    assert_eq!(close.unwrap().code, CloseCode::Away);
    drained.await.unwrap();
    let text = metrics.render();
    assert_eq!(
        sample(&text, "omi_edge_shadow_sessions_total{outcome=\"drained\"}"),
        1.0
    );
    assert_eq!(
        sample(&text, "omi_edge_shadow_handshakes_total{result=\"overloaded\"}"),
        1.0
    );
}
