//! Prometheus metrics for listen-edge, following plan B's rules:
//! - every label value comes from a closed enum below (no uid, session,
//!   path, query, peer or provider-supplied strings);
//! - every child is created at startup, so all series exist at zero and the
//!   per-frame path only touches cached counters (O4: no `.labels()` lookups
//!   per frame);
//! - the whole exporter stays inside [`SERIES_BUDGET`] (checked by a test).
use prometheus::{
    Counter, CounterVec, Encoder, Histogram, HistogramOpts, IntCounter, IntCounterVec, IntGauge, IntGaugeVec, Opts,
    Registry, TextEncoder,
};

use crate::codec::Codec;
use crate::gate::Variant;

/// Upper bound on exported series (including histogram buckets). The GMP
/// limit per target is 10,000 samples; the edge should stay tiny.
pub const SERIES_BUDGET: usize = 200;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Direction {
    ClientToUpstream,
    UpstreamToClient,
}

impl Direction {
    pub const ALL: [Direction; 2] = [Direction::ClientToUpstream, Direction::UpstreamToClient];
    pub fn as_str(self) -> &'static str {
        match self {
            Direction::ClientToUpstream => "client_to_upstream",
            Direction::UpstreamToClient => "upstream_to_client",
        }
    }
    fn idx(self) -> usize {
        self as usize
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum FrameKind {
    Binary,
    Text,
}

impl FrameKind {
    pub const ALL: [FrameKind; 2] = [FrameKind::Binary, FrameKind::Text];
    pub fn as_str(self) -> &'static str {
        match self {
            FrameKind::Binary => "binary",
            FrameKind::Text => "text",
        }
    }
    fn idx(self) -> usize {
        self as usize
    }
}

/// Result of a websocket upgrade request on a proxied path.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum HandshakeResult {
    /// Upstream accepted; the client got 101.
    Accepted,
    /// Upstream answered the handshake with a non-101 status; mirrored to the client.
    UpstreamRejected,
    /// Upstream refused or failed the connection; the client got 502.
    UpstreamUnavailable,
    /// Upstream did not complete the handshake in time; the client got 504.
    UpstreamTimeout,
    /// The request was not a valid websocket upgrade; the client got 4xx.
    InvalidRequest,
    /// Upstream accepted but the client's upgrade did not complete.
    ClientUpgradeFailed,
    /// `EDGE_MAX_SESSIONS` or `EDGE_MAX_PENDING_HANDSHAKES` reached; the client got 503.
    Overloaded,
}

impl HandshakeResult {
    pub const ALL: [HandshakeResult; 7] = [
        HandshakeResult::Accepted,
        HandshakeResult::UpstreamRejected,
        HandshakeResult::UpstreamUnavailable,
        HandshakeResult::UpstreamTimeout,
        HandshakeResult::InvalidRequest,
        HandshakeResult::ClientUpgradeFailed,
        HandshakeResult::Overloaded,
    ];
    pub fn as_str(self) -> &'static str {
        match self {
            HandshakeResult::Accepted => "accepted",
            HandshakeResult::UpstreamRejected => "upstream_rejected",
            HandshakeResult::UpstreamUnavailable => "upstream_unavailable",
            HandshakeResult::UpstreamTimeout => "upstream_timeout",
            HandshakeResult::InvalidRequest => "invalid_request",
            HandshakeResult::ClientUpgradeFailed => "client_upgrade_failed",
            HandshakeResult::Overloaded => "overloaded",
        }
    }
}

/// How a relayed session ended.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum SessionOutcome {
    /// The client started the close handshake; it was forwarded upstream.
    ClientClosed,
    /// Upstream (listen) started the close handshake; it was forwarded to the client.
    UpstreamClosed,
    /// The client connection ended without a close frame (mirrored upstream as a drop).
    ClientDropped,
    /// The upstream connection ended without a close frame (mirrored to the client as a drop).
    UpstreamDropped,
    /// The edge asked the client to reconnect (1012) during drain and the handshake completed.
    Drained,
    /// A close handshake did not finish within `EDGE_CLOSE_TIMEOUT_MS`.
    CloseTimeout,
}

impl SessionOutcome {
    pub const ALL: [SessionOutcome; 6] = [
        SessionOutcome::ClientClosed,
        SessionOutcome::UpstreamClosed,
        SessionOutcome::ClientDropped,
        SessionOutcome::UpstreamDropped,
        SessionOutcome::Drained,
        SessionOutcome::CloseTimeout,
    ];
    pub fn as_str(self) -> &'static str {
        match self {
            SessionOutcome::ClientClosed => "client_closed",
            SessionOutcome::UpstreamClosed => "upstream_closed",
            SessionOutcome::ClientDropped => "client_dropped",
            SessionOutcome::UpstreamDropped => "upstream_dropped",
            SessionOutcome::Drained => "drained",
            SessionOutcome::CloseTimeout => "close_timeout",
        }
    }
}

/// Result of an upgrade request on the shadow ingest path.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ShadowHandshake {
    Accepted,
    /// Bad upgrade, version, codec, rate or session key; the caller got 4xx.
    InvalidRequest,
    /// `EDGE_SHADOW_TOKEN` is set and the request did not carry it.
    Unauthorized,
    /// `EDGE_SHADOW_MAX_SESSIONS` reached; 503.
    Overloaded,
    /// No VAD model configured (`EDGE_VAD_MODEL_PATH` unset), or draining; 503.
    Disabled,
}

impl ShadowHandshake {
    pub const ALL: [ShadowHandshake; 5] = [
        ShadowHandshake::Accepted,
        ShadowHandshake::InvalidRequest,
        ShadowHandshake::Unauthorized,
        ShadowHandshake::Overloaded,
        ShadowHandshake::Disabled,
    ];
    pub fn as_str(self) -> &'static str {
        match self {
            ShadowHandshake::Accepted => "accepted",
            ShadowHandshake::InvalidRequest => "invalid_request",
            ShadowHandshake::Unauthorized => "unauthorized",
            ShadowHandshake::Overloaded => "overloaded",
            ShadowHandshake::Disabled => "disabled",
        }
    }
}

/// How a shadow session ended.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ShadowOutcome {
    /// listen closed the mirror (session over, or listen stopped mirroring).
    Completed,
    /// Frames were not contiguous (listen dropped mirror frames); comparison stopped.
    Desync,
    /// A message did not parse; the edge closed the mirror.
    ProtocolError,
    /// Silero failed; the edge closed the mirror.
    VadError,
    /// The edge drained (SIGTERM) and closed the mirror.
    Drained,
}

impl ShadowOutcome {
    pub const ALL: [ShadowOutcome; 5] = [
        ShadowOutcome::Completed,
        ShadowOutcome::Desync,
        ShadowOutcome::ProtocolError,
        ShadowOutcome::VadError,
        ShadowOutcome::Drained,
    ];
    pub fn as_str(self) -> &'static str {
        match self {
            ShadowOutcome::Completed => "completed",
            ShadowOutcome::Desync => "desync",
            ShadowOutcome::ProtocolError => "protocol_error",
            ShadowOutcome::VadError => "vad_error",
            ShadowOutcome::Drained => "drained",
        }
    }
}

/// Per mirrored frame.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum FrameResult {
    /// Decoded to the same sample count listen reported.
    Decoded,
    /// The edge could not decode a frame listen decoded (scored as silence).
    DecodeError,
    /// Decoded, but to a different sample count than listen's.
    LengthMismatch,
}

impl FrameResult {
    pub const ALL: [FrameResult; 3] = [
        FrameResult::Decoded,
        FrameResult::DecodeError,
        FrameResult::LengthMismatch,
    ];
    pub fn as_str(self) -> &'static str {
        match self {
            FrameResult::Decoded => "decoded",
            FrameResult::DecodeError => "decode_error",
            FrameResult::LengthMismatch => "length_mismatch",
        }
    }
}

/// One listen VAD window against the edge's window with the same ordinal.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum CompareResult {
    AgreeSpeech,
    AgreeSilence,
    EdgeSpeechOnly,
    ListenSpeechOnly,
    /// From a listen gate the edge is not aligned with (a later gate after
    /// failover, or one that started mid-frame).
    NotComparable,
    /// No edge window to compare (evicted, or never scored).
    Unmatched,
}

impl CompareResult {
    pub const ALL: [CompareResult; 6] = [
        CompareResult::AgreeSpeech,
        CompareResult::AgreeSilence,
        CompareResult::EdgeSpeechOnly,
        CompareResult::ListenSpeechOnly,
        CompareResult::NotComparable,
        CompareResult::Unmatched,
    ];
    pub fn as_str(self) -> &'static str {
        match self {
            CompareResult::AgreeSpeech => "agree_speech",
            CompareResult::AgreeSilence => "agree_silence",
            CompareResult::EdgeSpeechOnly => "edge_speech_only",
            CompareResult::ListenSpeechOnly => "listen_speech_only",
            CompareResult::NotComparable => "not_comparable",
            CompareResult::Unmatched => "unmatched",
        }
    }
    pub fn idx(self) -> usize {
        self as usize
    }
}

/// Gate opens (SILENCE -> SPEECH) matched between listen and the edge.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum OpenResult {
    /// Both opened within 2 s; the offset goes to `omi_edge_shadow_gate_open_offset_seconds`.
    Matched,
    ListenOnly,
    EdgeOnly,
    NotComparable,
}

impl OpenResult {
    pub const ALL: [OpenResult; 4] = [
        OpenResult::Matched,
        OpenResult::ListenOnly,
        OpenResult::EdgeOnly,
        OpenResult::NotComparable,
    ];
    pub fn as_str(self) -> &'static str {
        match self {
            OpenResult::Matched => "matched",
            OpenResult::ListenOnly => "listen_only",
            OpenResult::EdgeOnly => "edge_only",
            OpenResult::NotComparable => "not_comparable",
        }
    }
    pub fn idx(self) -> usize {
        self as usize
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Stage {
    Decode,
    Vad,
}

impl Stage {
    pub const ALL: [Stage; 2] = [Stage::Decode, Stage::Vad];
    pub fn as_str(self) -> &'static str {
        match self {
            Stage::Decode => "decode",
            Stage::Vad => "vad",
        }
    }
}

/// Shadow (D2) series. Every child is cached; the frame path indexes arrays.
pub struct ShadowMetrics {
    pub sessions_active: IntGauge,
    sessions_total: Vec<IntCounter>,
    handshakes_total: Vec<IntCounter>,
    /// [codec][frame result]
    frames: Vec<[IntCounter; 3]>,
    /// [codec]
    pub audio_seconds: Vec<Counter>,
    /// [codec]
    pub windows: Vec<IntCounter>,
    /// [codec][variant][compare result]
    compare: Vec<[[IntCounter; 6]; 2]>,
    pub prob_abs_diff: Histogram,
    opens: [IntCounter; 4],
    pub open_offset_seconds: Histogram,
    /// [stage]
    processing_seconds: [Counter; 2],
}

impl ShadowMetrics {
    pub fn session_ended(&self, outcome: ShadowOutcome) {
        self.sessions_total[ShadowOutcome::ALL.iter().position(|o| *o == outcome).unwrap()].inc();
    }
    pub fn handshake(&self, result: ShadowHandshake) {
        self.handshakes_total[ShadowHandshake::ALL.iter().position(|r| *r == result).unwrap()].inc();
    }
    pub fn frame(&self, codec: Codec, result: FrameResult) {
        self.frames[codec.idx()][FrameResult::ALL.iter().position(|r| *r == result).unwrap()].inc();
    }
    pub fn compare(&self, codec: Codec, variant: Variant, result: CompareResult, n: u64) {
        self.compare[codec.idx()][variant.idx()][result.idx()].inc_by(n);
    }
    pub fn open(&self, result: OpenResult, n: u64) {
        self.opens[result.idx()].inc_by(n);
    }
    pub fn processing(&self, stage: Stage, seconds: f64) {
        self.processing_seconds[stage as usize].inc_by(seconds);
    }
}

/// Cached per-direction counters handed to a relay pump.
#[derive(Clone)]
pub struct DirectionCounters {
    pub frames: [IntCounter; 2],
    pub bytes: IntCounter,
    pub discarded: IntCounter,
}

impl DirectionCounters {
    #[inline]
    pub fn record(&self, kind: FrameKind, len: usize) {
        self.frames[kind.idx()].inc();
        self.bytes.inc_by(len as u64);
    }
}

pub struct Metrics {
    registry: Registry,
    pub sessions_active: IntGauge,
    pub draining: IntGauge,
    sessions_total: Vec<IntCounter>,
    handshakes_total: Vec<IntCounter>,
    directions: [DirectionCounters; 2],
    pub upstream_connect_seconds: Histogram,
    pub session_seconds: Histogram,
    pub shadow: ShadowMetrics,
}

/// Release SHA as a bounded label value: 7-40 lowercase hex, else "unknown".
pub fn sanitize_release_sha(raw: &str) -> String {
    let s = raw.trim().to_ascii_lowercase();
    if (7..=40).contains(&s.len()) && s.bytes().all(|b| b.is_ascii_hexdigit()) {
        s[..s.len().min(12)].to_string()
    } else {
        "unknown".to_string()
    }
}

impl Metrics {
    pub fn new(release_sha: &str) -> Self {
        let registry = Registry::new();
        let reg = |c: Box<dyn prometheus::core::Collector>| registry.register(c).expect("metric registration");

        let sessions_active =
            IntGauge::new("omi_edge_sessions_active", "Relayed websocket sessions currently open").unwrap();
        reg(Box::new(sessions_active.clone()));

        let draining = IntGauge::new("omi_edge_draining", "1 while the edge is draining after SIGTERM").unwrap();
        reg(Box::new(draining.clone()));

        let build = IntGaugeVec::new(
            Opts::new("omi_edge_build_info", "Release identity of the running edge (always 1)"),
            &["release_sha"],
        )
        .unwrap();
        reg(Box::new(build.clone()));
        build.with_label_values(&[&sanitize_release_sha(release_sha)]).set(1);

        let sessions_vec = IntCounterVec::new(
            Opts::new("omi_edge_sessions_total", "Relayed sessions by how they ended"),
            &["outcome"],
        )
        .unwrap();
        reg(Box::new(sessions_vec.clone()));
        let sessions_total = SessionOutcome::ALL
            .iter()
            .map(|o| sessions_vec.with_label_values(&[o.as_str()]))
            .collect();

        let handshake_vec = IntCounterVec::new(
            Opts::new(
                "omi_edge_handshakes_total",
                "Websocket upgrade requests on proxied paths by result",
            ),
            &["result"],
        )
        .unwrap();
        reg(Box::new(handshake_vec.clone()));
        let handshakes_total = HandshakeResult::ALL
            .iter()
            .map(|r| handshake_vec.with_label_values(&[r.as_str()]))
            .collect();

        let frames_vec = IntCounterVec::new(
            Opts::new("omi_edge_frames_total", "Websocket messages relayed"),
            &["direction", "kind"],
        )
        .unwrap();
        reg(Box::new(frames_vec.clone()));
        let bytes_vec = IntCounterVec::new(
            Opts::new("omi_edge_bytes_total", "Payload bytes relayed"),
            &["direction"],
        )
        .unwrap();
        reg(Box::new(bytes_vec.clone()));
        let discarded_vec = IntCounterVec::new(
            Opts::new(
                "omi_edge_frames_discarded_total",
                "Messages that arrived after the destination had closed (cannot be relayed by protocol)",
            ),
            &["direction"],
        )
        .unwrap();
        reg(Box::new(discarded_vec.clone()));

        let dir = |d: Direction| DirectionCounters {
            frames: FrameKind::ALL.map(|k| frames_vec.with_label_values(&[d.as_str(), k.as_str()])),
            bytes: bytes_vec.with_label_values(&[d.as_str()]),
            discarded: discarded_vec.with_label_values(&[d.as_str()]),
        };
        let directions = Direction::ALL.map(dir);

        let upstream_connect_seconds = Histogram::with_opts(
            HistogramOpts::new(
                "omi_edge_upstream_connect_seconds",
                "Upstream TCP connect plus websocket handshake time, per session",
            )
            .buckets(vec![0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]),
        )
        .unwrap();
        reg(Box::new(upstream_connect_seconds.clone()));

        let session_seconds = Histogram::with_opts(
            HistogramOpts::new("omi_edge_session_seconds", "Relayed session duration")
                .buckets(vec![1.0, 10.0, 60.0, 300.0, 900.0, 1800.0, 3600.0, 7200.0, 14400.0]),
        )
        .unwrap();
        reg(Box::new(session_seconds.clone()));

        let shadow = {
            let gauge = IntGauge::new(
                "omi_edge_shadow_sessions_active",
                "Shadow mirror sessions currently open",
            )
            .unwrap();
            reg(Box::new(gauge.clone()));
            let sessions_vec = IntCounterVec::new(
                Opts::new(
                    "omi_edge_shadow_sessions_total",
                    "Shadow mirror sessions by how they ended",
                ),
                &["outcome"],
            )
            .unwrap();
            reg(Box::new(sessions_vec.clone()));
            let handshakes_vec = IntCounterVec::new(
                Opts::new(
                    "omi_edge_shadow_handshakes_total",
                    "Upgrade requests on the shadow path by result",
                ),
                &["result"],
            )
            .unwrap();
            reg(Box::new(handshakes_vec.clone()));
            let frames_vec = IntCounterVec::new(
                Opts::new(
                    "omi_edge_shadow_frames_total",
                    "Mirrored client frames by decode result",
                ),
                &["codec", "result"],
            )
            .unwrap();
            reg(Box::new(frames_vec.clone()));
            let audio_vec = CounterVec::new(
                Opts::new(
                    "omi_edge_shadow_audio_seconds_total",
                    "Mirrored audio, seconds, as listen decoded it",
                ),
                &["codec"],
            )
            .unwrap();
            reg(Box::new(audio_vec.clone()));
            let windows_vec = IntCounterVec::new(
                Opts::new("omi_edge_shadow_vad_windows_total", "Silero windows scored by the edge"),
                &["codec"],
            )
            .unwrap();
            reg(Box::new(windows_vec.clone()));
            let compare_vec = IntCounterVec::new(
                Opts::new(
                    "omi_edge_shadow_window_compare_total",
                    "listen VAD windows compared with the edge window of the same ordinal",
                ),
                &["codec", "variant", "result"],
            )
            .unwrap();
            reg(Box::new(compare_vec.clone()));
            let prob_abs_diff = Histogram::with_opts(
                HistogramOpts::new(
                    "omi_edge_shadow_prob_abs_diff",
                    "Absolute difference of edge and listen speech probability per compared window",
                )
                .buckets(vec![1e-6, 1e-5, 1e-4, 1e-3, 0.01, 0.05, 0.1, 0.25, 0.5]),
            )
            .unwrap();
            reg(Box::new(prob_abs_diff.clone()));
            let opens_vec = IntCounterVec::new(
                Opts::new(
                    "omi_edge_shadow_gate_opens_total",
                    "Gate opens matched between listen and the edge",
                ),
                &["result"],
            )
            .unwrap();
            reg(Box::new(opens_vec.clone()));
            let open_offset_seconds = Histogram::with_opts(
                HistogramOpts::new(
                    "omi_edge_shadow_gate_open_offset_seconds",
                    "Absolute offset between matched listen and edge gate opens",
                )
                .buckets(vec![0.0, 0.016, 0.032, 0.064, 0.128, 0.256, 0.512, 1.0, 2.0]),
            )
            .unwrap();
            reg(Box::new(open_offset_seconds.clone()));
            let processing_vec = CounterVec::new(
                Opts::new(
                    "omi_edge_shadow_processing_seconds_total",
                    "CPU time (thread clock) the edge spent decoding and scoring mirrored audio",
                ),
                &["stage"],
            )
            .unwrap();
            reg(Box::new(processing_vec.clone()));

            ShadowMetrics {
                sessions_active: gauge,
                sessions_total: ShadowOutcome::ALL
                    .iter()
                    .map(|o| sessions_vec.with_label_values(&[o.as_str()]))
                    .collect(),
                handshakes_total: ShadowHandshake::ALL
                    .iter()
                    .map(|r| handshakes_vec.with_label_values(&[r.as_str()]))
                    .collect(),
                frames: Codec::ALL
                    .iter()
                    .map(|c| FrameResult::ALL.map(|r| frames_vec.with_label_values(&[c.as_str(), r.as_str()])))
                    .collect(),
                audio_seconds: Codec::ALL
                    .iter()
                    .map(|c| audio_vec.with_label_values(&[c.as_str()]))
                    .collect(),
                windows: Codec::ALL
                    .iter()
                    .map(|c| windows_vec.with_label_values(&[c.as_str()]))
                    .collect(),
                compare: Codec::ALL
                    .iter()
                    .map(|c| {
                        Variant::ALL.map(|v| {
                            CompareResult::ALL
                                .map(|r| compare_vec.with_label_values(&[c.as_str(), v.as_str(), r.as_str()]))
                        })
                    })
                    .collect(),
                prob_abs_diff,
                opens: OpenResult::ALL.map(|r| opens_vec.with_label_values(&[r.as_str()])),
                open_offset_seconds,
                processing_seconds: Stage::ALL.map(|s| processing_vec.with_label_values(&[s.as_str()])),
            }
        };

        Metrics {
            registry,
            sessions_active,
            draining,
            sessions_total,
            handshakes_total,
            directions,
            upstream_connect_seconds,
            session_seconds,
            shadow,
        }
    }

    pub fn session_ended(&self, outcome: SessionOutcome) {
        self.sessions_total[SessionOutcome::ALL.iter().position(|o| *o == outcome).unwrap()].inc();
    }

    pub fn handshake(&self, result: HandshakeResult) {
        self.handshakes_total[HandshakeResult::ALL.iter().position(|r| *r == result).unwrap()].inc();
    }

    pub fn direction(&self, d: Direction) -> DirectionCounters {
        self.directions[d.idx()].clone()
    }

    pub fn render(&self) -> String {
        let mut buf = Vec::new();
        TextEncoder::new()
            .encode(&self.registry.gather(), &mut buf)
            .expect("text encoding");
        String::from_utf8(buf).expect("prometheus text is utf-8")
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::{BTreeSet, HashMap};

    /// Allowed values per label name. Any other value is a cardinality bug.
    fn allowed() -> HashMap<&'static str, BTreeSet<String>> {
        let mut m: HashMap<&'static str, BTreeSet<String>> = HashMap::new();
        m.insert(
            "direction",
            Direction::ALL.iter().map(|d| d.as_str().to_string()).collect(),
        );
        m.insert("kind", FrameKind::ALL.iter().map(|k| k.as_str().to_string()).collect());
        m.insert(
            "result",
            HandshakeResult::ALL.iter().map(|r| r.as_str().to_string()).collect(),
        );
        m.insert(
            "outcome",
            SessionOutcome::ALL.iter().map(|o| o.as_str().to_string()).collect(),
        );
        m.insert(
            "release_sha",
            ["0123456789ab".to_string(), "unknown".to_string()].into(),
        );
        // Shadow labels. `outcome` and `result` are shared names across
        // metrics, so their allowed sets are the union of the enums.
        m.get_mut("outcome")
            .unwrap()
            .extend(ShadowOutcome::ALL.iter().map(|o| o.as_str().to_string()));
        let result = m.get_mut("result").unwrap();
        result.extend(ShadowHandshake::ALL.iter().map(|r| r.as_str().to_string()));
        result.extend(FrameResult::ALL.iter().map(|r| r.as_str().to_string()));
        result.extend(CompareResult::ALL.iter().map(|r| r.as_str().to_string()));
        result.extend(OpenResult::ALL.iter().map(|r| r.as_str().to_string()));
        m.insert("codec", Codec::ALL.iter().map(|c| c.as_str().to_string()).collect());
        m.insert("variant", Variant::ALL.iter().map(|v| v.as_str().to_string()).collect());
        m.insert("stage", Stage::ALL.iter().map(|s| s.as_str().to_string()).collect());
        m
    }

    fn series(text: &str) -> Vec<String> {
        text.lines()
            .filter(|l| !l.starts_with('#') && !l.trim().is_empty())
            .map(|l| l.to_string())
            .collect()
    }

    #[test]
    fn every_label_value_is_from_an_enum_and_series_fit_the_budget() {
        let m = Metrics::new("0123456789abcdef0123456789abcdef01234567");
        for o in SessionOutcome::ALL {
            m.session_ended(o);
        }
        for r in HandshakeResult::ALL {
            m.handshake(r);
        }
        for d in Direction::ALL {
            for k in FrameKind::ALL {
                m.direction(d).record(k, 10);
            }
            m.direction(d).discarded.inc();
        }
        m.upstream_connect_seconds.observe(0.01);
        m.session_seconds.observe(30.0);
        let s = &m.shadow;
        for o in ShadowOutcome::ALL {
            s.session_ended(o);
        }
        for r in ShadowHandshake::ALL {
            s.handshake(r);
        }
        for c in Codec::ALL {
            for r in FrameResult::ALL {
                s.frame(c, r);
            }
            for v in Variant::ALL {
                for r in CompareResult::ALL {
                    s.compare(c, v, r, 1);
                }
            }
            s.windows[c.idx()].inc();
            s.audio_seconds[c.idx()].inc_by(0.5);
        }
        for r in OpenResult::ALL {
            s.open(r, 1);
        }
        for st in Stage::ALL {
            s.processing(st, 0.001);
        }
        s.prob_abs_diff.observe(0.001);
        s.open_offset_seconds.observe(0.02);

        let text = m.render();
        let lines = series(&text);
        assert!(
            lines.len() <= SERIES_BUDGET,
            "{} series > budget {}",
            lines.len(),
            SERIES_BUDGET
        );

        let allowed = allowed();
        for line in &lines {
            let Some(start) = line.find('{') else { continue };
            let end = line.find('}').unwrap();
            for pair in line[start + 1..end].split(',').filter(|p| !p.is_empty()) {
                let (k, v) = pair.split_once('=').unwrap();
                let v = v.trim_matches('"');
                if k == "le" {
                    continue;
                }
                let ok = allowed
                    .get(k)
                    .unwrap_or_else(|| panic!("unbudgeted label {k} in {line}"));
                assert!(ok.contains(v), "label {k}={v} not in its enum ({line})");
            }
        }
    }

    #[test]
    fn all_children_exist_at_zero() {
        let text = Metrics::new("").render();
        for o in SessionOutcome::ALL {
            assert!(text.contains(&format!("omi_edge_sessions_total{{outcome=\"{}\"}} 0", o.as_str())));
        }
        for r in HandshakeResult::ALL {
            assert!(text.contains(&format!("omi_edge_handshakes_total{{result=\"{}\"}} 0", r.as_str())));
        }
        assert!(text.contains("omi_edge_build_info{release_sha=\"unknown\"} 1"));
    }

    #[test]
    fn release_sha_is_bounded() {
        assert_eq!(sanitize_release_sha("ABCDEF1234567890"), "abcdef123456");
        assert_eq!(sanitize_release_sha("abc"), "unknown");
        assert_eq!(sanitize_release_sha("not-a-sha!"), "unknown");
        assert_eq!(sanitize_release_sha(&"a".repeat(41)), "unknown");
    }
}
