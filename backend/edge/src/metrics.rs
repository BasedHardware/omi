//! Prometheus metrics for listen-edge, following plan B's rules:
//! - every label value comes from a closed enum below (no uid, session,
//!   path, query, peer or provider-supplied strings);
//! - every child is created at startup, so all series exist at zero and the
//!   per-frame path only touches cached counters (O4: no `.labels()` lookups
//!   per frame);
//! - the whole exporter stays inside [`SERIES_BUDGET`] (checked by a test).
use prometheus::{
    Encoder, Histogram, HistogramOpts, IntCounter, IntCounterVec, IntGauge, IntGaugeVec, Opts, Registry, TextEncoder,
};

/// Upper bound on exported series (including histogram buckets). The GMP
/// limit per target is 10,000 samples; the edge should stay tiny.
pub const SERIES_BUDGET: usize = 120;

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

        Metrics {
            registry,
            sessions_active,
            draining,
            sessions_total,
            handshakes_total,
            directions,
            upstream_connect_seconds,
            session_seconds,
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
