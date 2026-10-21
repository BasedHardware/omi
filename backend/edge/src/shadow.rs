//! D2 shadow: listen mirrors a cohort's raw client frames here, the edge
//! decodes them and runs listen's VAD gate, and compares its window
//! decisions with the ones listen reports for the same audio. Nothing is
//! sent to any provider and nothing goes back to the client.
//!
//! # Wire protocol (v1)
//!
//! `GET /v1/shadow?v=1&codec=<opus|opus_fs320|pcm8|pcm16>&sample_rate=<hz>&session=<16-64 hex>`
//! upgrades to a websocket. `session` is listen's hashed session key, never a
//! uid. If `EDGE_SHADOW_TOKEN` is set, `x-edge-shadow-token` must match.
//! listen sends binary messages only, big-endian, first byte the kind; the
//! edge never sends data back:
//!
//! | kind | layout after the kind byte | meaning |
//! |---|---|---|
//! | 1 `FRAME` | u64 start_sample, u32 decoded_samples, payload | one client frame as received, with the capture position and sample count listen decoded it to |
//! | 2 `GATE_START` | u16 gen, u8 variant (0 plain, 1 agc), u8 mode (0 active, 1 shadow), f64 speech_threshold, f64 continue_threshold, u32 hangover_ms, u64 origin_sample (`u64::MAX` unknown) | a listen gate scored its first chunk, which starts at `origin_sample` |
//! | 3 `WINDOWS` | u16 gen, u32 first_ordinal, f32 prob × n | Silero probabilities of consecutive windows of that gate |
//! | 4 `OPEN` | u16 gen, u64 chunk_start, u64 preroll_start | that gate went SILENCE -> SPEECH |
//!
//! # Alignment
//!
//! The edge decodes every frame on arrival (one continuous decoder, like
//! listen) but holds the PCM until listen's first gate announces its origin.
//! It then starts its own gate at that origin with the same parameters, fed
//! by the same 30 ms STT-buffer chunking, so window `k` of both gates covers
//! the same samples. Later listen gates (failover replacements fed replayed
//! audio) are counted as not comparable. If no gate is announced within
//! [`PENDING_LIMIT_SECONDS`], the edge starts a standard gate on its own so
//! its VAD load is still measured.
use std::collections::VecDeque;
use std::sync::atomic::{AtomicU64, AtomicUsize, Ordering};
use std::sync::Arc;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use futures_util::StreamExt;
use tokio::io::{AsyncRead, AsyncWrite};
use tokio_tungstenite::tungstenite::protocol::frame::coding::CloseCode;
use tokio_tungstenite::tungstenite::protocol::CloseFrame;
use tokio_tungstenite::tungstenite::Message;
use tokio_tungstenite::WebSocketStream;
use tokio_util::sync::CancellationToken;

use crate::codec::{Codec, Decoder};
use crate::gate::{Gate, GateParams, Mode, Open, SttBuffer, Variant};
use crate::metrics::{CompareResult, FrameResult, Metrics, OpenResult, ShadowOutcome, Stage};

pub const PROTOCOL_VERSION: &str = "1";
/// Decoded PCM held while waiting for listen's first gate.
pub const PENDING_LIMIT_SECONDS: u64 = 10;
/// Edge windows kept for late listen reports (~131 s).
const EDGE_WINDOW_RING: usize = 4096;
/// listen windows that arrived before the edge scored them.
const LISTEN_WAIT_LIMIT: usize = 1024;
/// Opens further apart than this are not the same open.
const OPEN_MATCH_SECONDS: u64 = 2;
const OPEN_RING: usize = 1024;
/// Non-aligned listen gates tracked for de-duplication.
const OTHER_GENS: usize = 64;
/// Disagreement lines per session, and across the process per second.
const DETAIL_PER_SESSION: u32 = 5;
const DETAIL_PER_SECOND: u64 = 20;
/// No sane client frame decodes to more than this.
const MAX_FRAME_SECONDS: u64 = 1;
const MAX_WINDOWS_PER_MESSAGE: usize = 4096;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ProtocolError(pub &'static str);

#[derive(Debug, PartialEq)]
pub enum Msg<'a> {
    Frame {
        start: u64,
        samples: u32,
        payload: &'a [u8],
    },
    GateStart {
        gen: u16,
        params: GateParams,
        origin: Option<u64>,
    },
    Windows {
        gen: u16,
        first: u32,
        probs: Vec<f32>,
    },
    Open {
        gen: u16,
        open: Open,
    },
}

struct Reader<'a>(&'a [u8]);

impl<'a> Reader<'a> {
    fn take(&mut self, n: usize) -> Result<&'a [u8], ProtocolError> {
        if self.0.len() < n {
            return Err(ProtocolError("truncated message"));
        }
        let (head, rest) = self.0.split_at(n);
        self.0 = rest;
        Ok(head)
    }
    fn u8(&mut self) -> Result<u8, ProtocolError> {
        Ok(self.take(1)?[0])
    }
    fn u16(&mut self) -> Result<u16, ProtocolError> {
        Ok(u16::from_be_bytes(self.take(2)?.try_into().unwrap()))
    }
    fn u32(&mut self) -> Result<u32, ProtocolError> {
        Ok(u32::from_be_bytes(self.take(4)?.try_into().unwrap()))
    }
    fn u64(&mut self) -> Result<u64, ProtocolError> {
        Ok(u64::from_be_bytes(self.take(8)?.try_into().unwrap()))
    }
    fn f64(&mut self) -> Result<f64, ProtocolError> {
        Ok(f64::from_be_bytes(self.take(8)?.try_into().unwrap()))
    }
    fn done(&self) -> Result<(), ProtocolError> {
        if self.0.is_empty() {
            Ok(())
        } else {
            Err(ProtocolError("trailing bytes"))
        }
    }
}

pub fn parse(msg: &[u8]) -> Result<Msg<'_>, ProtocolError> {
    let mut r = Reader(msg);
    match r.u8()? {
        1 => {
            let start = r.u64()?;
            let samples = r.u32()?;
            Ok(Msg::Frame {
                start,
                samples,
                payload: r.0,
            })
        }
        2 => {
            let gen = r.u16()?;
            let variant = match r.u8()? {
                0 => Variant::Plain,
                1 => Variant::Agc,
                _ => return Err(ProtocolError("unknown variant")),
            };
            let mode = match r.u8()? {
                0 => Mode::Active,
                1 => Mode::Shadow,
                _ => return Err(ProtocolError("unknown mode")),
            };
            let speech_threshold = r.f64()?;
            let continue_threshold = r.f64()?;
            let hangover_ms = r.u32()?;
            let origin = r.u64()?;
            r.done()?;
            let unit = |t: f64| t.is_finite() && (0.0..=1.0).contains(&t);
            if !unit(speech_threshold) || !unit(continue_threshold) || hangover_ms > 600_000 {
                return Err(ProtocolError("gate parameters out of range"));
            }
            Ok(Msg::GateStart {
                gen,
                params: GateParams {
                    variant,
                    mode,
                    speech_threshold,
                    continue_threshold,
                    hangover_ms: hangover_ms as f64,
                },
                origin: (origin != u64::MAX).then_some(origin),
            })
        }
        3 => {
            let gen = r.u16()?;
            let first = r.u32()?;
            if r.0.len() % 4 != 0 || r.0.len() / 4 > MAX_WINDOWS_PER_MESSAGE {
                return Err(ProtocolError("bad window list"));
            }
            let probs = r.0.as_chunks::<4>().0.iter().map(|b| f32::from_be_bytes(*b)).collect();
            Ok(Msg::Windows { gen, first, probs })
        }
        4 => {
            let gen = r.u16()?;
            let chunk_start = r.u64()?;
            let preroll_start = r.u64()?;
            r.done()?;
            Ok(Msg::Open {
                gen,
                open: Open {
                    chunk_start,
                    preroll_start,
                },
            })
        }
        _ => Err(ProtocolError("unknown message kind")),
    }
}

/// Handshake metadata.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ShadowMeta {
    pub codec: Codec,
    pub sample_rate: u32,
    pub session_key: String,
}

impl ShadowMeta {
    /// Parse the upgrade query. Any unknown or missing value is an error.
    pub fn from_query(query: &str) -> Result<ShadowMeta, &'static str> {
        let mut version = None;
        let mut codec = None;
        let mut rate = None;
        let mut session = None;
        for (k, v) in query.split('&').filter_map(|kv| kv.split_once('=')) {
            match k {
                "v" => version = Some(v),
                "codec" => codec = Some(v),
                "sample_rate" => rate = Some(v),
                "session" => session = Some(v),
                _ => {}
            }
        }
        if version != Some(PROTOCOL_VERSION) {
            return Err("unsupported protocol version");
        }
        let codec = codec.and_then(Codec::parse).ok_or("unsupported codec")?;
        let sample_rate: u32 = rate.and_then(|r| r.parse().ok()).ok_or("bad sample_rate")?;
        if !codec.supports_rate(sample_rate) {
            return Err("unsupported sample_rate");
        }
        let session = session.ok_or("missing session")?;
        let hex = session.bytes().all(|b| matches!(b, b'0'..=b'9' | b'a'..=b'f'));
        if !(16..=64).contains(&session.len()) || !hex {
            return Err("session must be 16-64 lowercase hex");
        }
        Ok(ShadowMeta {
            codec,
            sample_rate,
            session_key: session.to_string(),
        })
    }
}

/// Per-session tallies, logged at the end and printed by the replay tool.
#[derive(Debug, Default, Clone)]
pub struct Summary {
    pub frames: u64,
    pub decode_errors: u64,
    pub length_mismatches: u64,
    pub audio_samples: u64,
    pub edge_windows: u64,
    pub compare: [u64; 6],
    pub opens: [u64; 4],
    pub open_offsets_samples: Vec<u64>,
    pub max_prob_diff: f32,
    pub decode_seconds: f64,
    pub vad_seconds: f64,
    pub variant: Option<Variant>,
    pub hangover_ms: Option<f64>,
    pub aligned: bool,
}

impl Summary {
    pub fn compared(&self) -> u64 {
        self.compare[..4].iter().sum()
    }
    pub fn agreed(&self) -> u64 {
        self.compare[CompareResult::AgreeSpeech.idx()] + self.compare[CompareResult::AgreeSilence.idx()]
    }
    /// Agreement over compared windows; `None` when nothing was compared.
    pub fn agreement(&self) -> Option<f64> {
        let n = self.compared();
        (n > 0).then(|| self.agreed() as f64 / n as f64)
    }
}

/// CPU time of the calling thread, in seconds. Decode and VAD run inline on
/// one worker thread without awaiting, so a before/after difference is that
/// stage's CPU, unaffected by other load on the host.
fn thread_cpu_seconds() -> f64 {
    let mut ts = libc::timespec { tv_sec: 0, tv_nsec: 0 };
    // SAFETY: `ts` is a valid, writable timespec for the duration of the call.
    let rc = unsafe { libc::clock_gettime(libc::CLOCK_THREAD_CPUTIME_ID, &mut ts) };
    if rc != 0 {
        return 0.0;
    }
    ts.tv_sec as f64 + ts.tv_nsec as f64 * 1e-9
}

/// Process-wide limit on disagreement detail lines.
static DETAIL_SECOND: AtomicU64 = AtomicU64::new(0);
static DETAIL_COUNT: AtomicU64 = AtomicU64::new(0);

fn detail_allowed() -> bool {
    let now = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    if DETAIL_SECOND.swap(now, Ordering::Relaxed) != now {
        DETAIL_COUNT.store(0, Ordering::Relaxed);
    }
    DETAIL_COUNT.fetch_add(1, Ordering::Relaxed) < DETAIL_PER_SECOND
}

/// The listen gate the edge's gate is aligned with.
struct Aligned {
    gen: u16,
}

/// A gate announced by listen whose origin frame has not arrived yet.
struct AwaitingOrigin {
    gen: u16,
    params: GateParams,
    origin: u64,
}

/// One shadow session's decode, VAD and comparison. Synchronous, so the
/// websocket task and the offline replay tool share it.
pub struct ShadowCore {
    meta: ShadowMeta,
    metrics: Arc<Metrics>,
    decoder: Decoder,
    next_start: Option<u64>,
    desynced: bool,
    pending: VecDeque<(u64, Vec<u8>)>,
    pending_samples: u64,
    awaiting: Option<AwaitingOrigin>,
    gate: Option<Gate>,
    stt: Option<SttBuffer>,
    aligned: Option<Aligned>,
    /// Edge windows: (probability, threshold), the front has ordinal `edge_base`.
    edge_windows: VecDeque<(f32, f64)>,
    edge_base: u64,
    listen_waiting: VecDeque<(u64, f32)>,
    /// Next listen ordinal not yet seen (repeats are ignored).
    listen_next: u64,
    /// (gen, next unseen ordinal) of listen gates the edge is not aligned with.
    other_next: Vec<(u16, u64)>,
    /// Capture sample just past the last chunk the edge gate scored.
    scored_until: u64,
    edge_opens: VecDeque<(Open, bool)>,
    listen_opens: VecDeque<Open>,
    details: u32,
    summary: Summary,
}

impl ShadowCore {
    pub fn new(meta: ShadowMeta, metrics: Arc<Metrics>) -> Result<ShadowCore, String> {
        let decoder = Decoder::new(meta.codec, meta.sample_rate).map_err(|e| e.0)?;
        Ok(ShadowCore {
            meta,
            metrics,
            decoder,
            next_start: None,
            desynced: false,
            pending: VecDeque::new(),
            pending_samples: 0,
            awaiting: None,
            gate: None,
            stt: None,
            aligned: None,
            edge_windows: VecDeque::new(),
            edge_base: 0,
            listen_waiting: VecDeque::new(),
            listen_next: 0,
            other_next: Vec::new(),
            scored_until: 0,
            edge_opens: VecDeque::new(),
            listen_opens: VecDeque::new(),
            details: 0,
            summary: Summary::default(),
        })
    }

    pub fn meta(&self) -> &ShadowMeta {
        &self.meta
    }

    pub fn summary(&self) -> &Summary {
        &self.summary
    }

    /// Handle one binary message. `Err(outcome)` ends the session.
    pub fn on_message(&mut self, msg: &[u8]) -> Result<(), ShadowOutcome> {
        let parsed = parse(msg).map_err(|e| {
            tracing::warn!(session = %self.meta.session_key, error = e.0, "shadow protocol error");
            ShadowOutcome::ProtocolError
        })?;
        if self.desynced {
            return Ok(());
        }
        match parsed {
            Msg::Frame {
                start,
                samples,
                payload,
            } => self.on_frame(start, samples, payload),
            Msg::GateStart { gen, params, origin } => self.on_gate_start(gen, params, origin),
            Msg::Windows { gen, first, probs } => {
                self.on_windows(gen, first as u64, &probs);
                Ok(())
            }
            Msg::Open { gen, open } => {
                self.on_open(gen, open);
                Ok(())
            }
        }
    }

    fn on_frame(&mut self, start: u64, samples: u32, payload: &[u8]) -> Result<(), ShadowOutcome> {
        if samples as u64 > self.meta.sample_rate as u64 * MAX_FRAME_SECONDS {
            return Err(ShadowOutcome::ProtocolError);
        }
        if let Some(expected) = self.next_start {
            if start != expected {
                // listen stops mirroring after any dropped frame; a gap
                // means positions can no longer be trusted.
                self.desynced = true;
                return Err(ShadowOutcome::Desync);
            }
        }
        let Some(next) = start.checked_add(samples as u64) else {
            return Err(ShadowOutcome::ProtocolError);
        };
        self.next_start = Some(next);
        self.summary.frames += 1;
        self.summary.audio_samples += samples as u64;
        let codec = self.meta.codec;
        let shadow = &self.metrics.shadow;
        shadow.audio_seconds[codec.idx()].inc_by(samples as f64 / self.meta.sample_rate as f64);

        let started = thread_cpu_seconds();
        let mut pcm = Vec::new();
        let decoded = self.decoder.decode(payload, &mut pcm);
        let took = (thread_cpu_seconds() - started).max(0.0);
        shadow.processing(Stage::Decode, took);
        self.summary.decode_seconds += took;
        let result = match decoded {
            Err(_) => {
                // Keep positions aligned: score listen's length of silence.
                pcm = vec![0; samples as usize * 2];
                self.summary.decode_errors += 1;
                FrameResult::DecodeError
            }
            Ok(()) if pcm.len() / 2 != samples as usize => {
                // Keep later windows on listen's positions: truncate or pad
                // to listen's count (the frame's own windows may disagree).
                pcm.resize(samples as usize * 2, 0);
                self.summary.length_mismatches += 1;
                FrameResult::LengthMismatch
            }
            Ok(()) => FrameResult::Decoded,
        };
        shadow.frame(codec, result);
        self.accept_pcm(start, pcm)
    }

    fn accept_pcm(&mut self, start: u64, pcm: Vec<u8>) -> Result<(), ShadowOutcome> {
        if self.gate.is_some() {
            return self.score(start, &pcm);
        }
        if let Some(awaiting) = &self.awaiting {
            if start < awaiting.origin {
                return Ok(());
            }
            let awaiting = self.awaiting.take().expect("checked");
            if start == awaiting.origin {
                self.start_gate(awaiting.params, Some(awaiting.gen));
            } else {
                // The origin fell inside a frame: the chunking cannot line up.
                self.start_gate(awaiting.params, None);
            }
            return self.score(start, &pcm);
        }
        self.pending_samples += pcm.len() as u64 / 2;
        self.pending.push_back((start, pcm));
        if self.pending_samples > PENDING_LIMIT_SECONDS * self.meta.sample_rate as u64 {
            // No listen gate yet (VAD off, or audio held): score on our own.
            self.start_gate(GateParams::standard(), None);
            self.flush_pending(None)?;
        }
        Ok(())
    }

    fn start_gate(&mut self, params: GateParams, aligned_gen: Option<u16>) {
        self.gate = Some(Gate::new(self.meta.sample_rate, params));
        self.stt = Some(SttBuffer::new(self.meta.sample_rate));
        self.aligned = aligned_gen.map(|gen| Aligned { gen });
        self.summary.variant = Some(params.variant);
        self.summary.hangover_ms = Some(params.hangover_ms);
        self.summary.aligned = aligned_gen.is_some();
    }

    /// Score held frames from `origin` on (all of them when `None`).
    fn flush_pending(&mut self, origin: Option<u64>) -> Result<(), ShadowOutcome> {
        let pending = std::mem::take(&mut self.pending);
        self.pending_samples = 0;
        for (start, pcm) in pending {
            if origin.is_some_and(|o| start < o) {
                continue;
            }
            self.score(start, &pcm)?;
        }
        Ok(())
    }

    fn on_gate_start(&mut self, gen: u16, params: GateParams, origin: Option<u64>) -> Result<(), ShadowOutcome> {
        if self.gate.is_some() || self.awaiting.is_some() {
            // A later gate (failover replacement): not comparable.
            return Ok(());
        }
        let Some(origin) = origin else {
            return Ok(());
        };
        if self.pending.iter().any(|(s, _)| *s == origin) {
            self.start_gate(params, Some(gen));
            return self.flush_pending(Some(origin));
        }
        let next = self.next_start.unwrap_or(0);
        if origin >= next {
            // The origin frame has not been mirrored yet.
            self.pending.clear();
            self.pending_samples = 0;
            self.awaiting = Some(AwaitingOrigin { gen, params, origin });
            return Ok(());
        }
        // The origin is inside a held frame or older than what is held.
        self.start_gate(params, None);
        self.flush_pending(None)
    }

    fn score(&mut self, start: u64, pcm: &[u8]) -> Result<(), ShadowOutcome> {
        match self.stt.as_mut().expect("gate started").push(pcm, start) {
            Some((chunk, chunk_start)) => self.process(&chunk, chunk_start),
            None => Ok(()),
        }
    }

    /// Run one STT-buffer chunk through the edge gate and settle what it unblocks.
    fn process(&mut self, chunk: &[u8], chunk_start: u64) -> Result<(), ShadowOutcome> {
        let started = thread_cpu_seconds();
        let out = self
            .gate
            .as_mut()
            .expect("gate started")
            .process_chunk(chunk, chunk_start)
            .map_err(|e| {
                tracing::warn!(session = %self.meta.session_key, error = %e, "shadow vad failed");
                ShadowOutcome::VadError
            })?;
        let took = (thread_cpu_seconds() - started).max(0.0);
        let shadow = &self.metrics.shadow;
        shadow.processing(Stage::Vad, took);
        self.summary.vad_seconds += took;
        shadow.windows[self.meta.codec.idx()].inc_by(out.probs.len() as u64);
        self.summary.edge_windows += out.probs.len() as u64;
        self.scored_until = chunk_start.saturating_add(chunk.len() as u64 / 2);

        for p in out.probs {
            self.edge_windows.push_back((p, out.threshold));
        }
        while self.edge_windows.len() > EDGE_WINDOW_RING {
            self.edge_windows.pop_front();
            self.edge_base += 1;
        }
        if let Some(open) = out.opened {
            self.edge_opens.push_back((open, false));
            if self.edge_opens.len() > OPEN_RING {
                if let Some((_, matched)) = self.edge_opens.pop_front() {
                    if !matched {
                        self.count_open(OpenResult::EdgeOnly);
                    }
                }
            }
        }
        // listen reports that arrived ahead of the edge's chunking.
        let edge_end = self.edge_base + self.edge_windows.len() as u64;
        while let Some(&(ord, p)) = self.listen_waiting.front() {
            if ord >= edge_end {
                break;
            }
            self.listen_waiting.pop_front();
            self.compare_window(ord, p);
        }
        self.resolve_opens(false);
        Ok(())
    }

    fn variant(&self) -> Variant {
        self.gate.as_ref().map(|g| g.params().variant).unwrap_or(Variant::Plain)
    }

    fn count(&mut self, result: CompareResult, n: u64) {
        self.summary.compare[result.idx()] += n;
        let variant = self.variant();
        self.metrics.shadow.compare(self.meta.codec, variant, result, n);
    }

    fn count_open(&mut self, result: OpenResult) {
        self.summary.opens[result.idx()] += 1;
        self.metrics.shadow.open(result, 1);
    }

    fn on_windows(&mut self, gen: u16, first: u64, probs: &[f32]) {
        if self.aligned.as_ref().map(|a| a.gen) != Some(gen) {
            // Before alignment, a window of the aligned gen cannot arrive:
            // GATE_START precedes it on the same ordered socket. Other gens
            // are only counted, once per ordinal.
            let end = first + probs.len() as u64;
            let seen = match self.other_next.iter_mut().find(|(g, _)| *g == gen) {
                Some((_, next)) => std::mem::replace(next, (*next).max(end)),
                None => {
                    if self.other_next.len() >= OTHER_GENS {
                        self.other_next.remove(0);
                    }
                    self.other_next.push((gen, end));
                    0
                }
            };
            let fresh = end.saturating_sub(first.max(seen));
            self.count(CompareResult::NotComparable, fresh);
            return;
        }
        let edge_end = self.edge_base + self.edge_windows.len() as u64;
        for (i, &p) in probs.iter().enumerate() {
            let ord = first + i as u64;
            if ord < self.listen_next {
                // A repeated ordinal is already counted once.
                continue;
            }
            self.listen_next = ord + 1;
            if ord < self.edge_base {
                self.count(CompareResult::Unmatched, 1);
            } else if ord < edge_end {
                self.compare_window(ord, p);
            } else {
                self.listen_waiting.push_back((ord, p));
                if self.listen_waiting.len() > LISTEN_WAIT_LIMIT {
                    self.listen_waiting.pop_front();
                    self.count(CompareResult::Unmatched, 1);
                }
            }
        }
    }

    fn compare_window(&mut self, ord: u64, listen_prob: f32) {
        let Some(&(edge_prob, threshold)) = self.edge_windows.get((ord - self.edge_base) as usize) else {
            self.count(CompareResult::Unmatched, 1);
            return;
        };
        let edge_speech = edge_prob as f64 > threshold;
        let listen_speech = listen_prob as f64 > threshold;
        let result = match (edge_speech, listen_speech) {
            (true, true) => CompareResult::AgreeSpeech,
            (false, false) => CompareResult::AgreeSilence,
            (true, false) => CompareResult::EdgeSpeechOnly,
            (false, true) => CompareResult::ListenSpeechOnly,
        };
        self.count(result, 1);
        let diff = (edge_prob - listen_prob).abs();
        if diff.is_finite() {
            self.metrics.shadow.prob_abs_diff.observe(diff as f64);
            self.summary.max_prob_diff = self.summary.max_prob_diff.max(diff);
        }
        if edge_speech != listen_speech && self.details < DETAIL_PER_SESSION && detail_allowed() {
            self.details += 1;
            tracing::info!(
                target: "edge_shadow",
                event = "shadow_window_disagreement",
                session = %self.meta.session_key,
                codec = self.meta.codec.as_str(),
                variant = self.variant().as_str(),
                ordinal = ord,
                edge_prob = edge_prob as f64,
                listen_prob = listen_prob as f64,
                threshold,
            );
        }
    }

    fn on_open(&mut self, gen: u16, open: Open) {
        if self.aligned.as_ref().map(|a| a.gen) != Some(gen) {
            self.count_open(OpenResult::NotComparable);
            return;
        }
        self.listen_opens.push_back(open);
        if self.listen_opens.len() > OPEN_RING {
            self.listen_opens.pop_front();
            self.count_open(OpenResult::ListenOnly);
        }
        self.resolve_opens(false);
    }

    /// Pair listen opens with the nearest unmatched edge open within 2 s.
    /// A listen open waits until the edge has scored 2 s past it.
    fn resolve_opens(&mut self, last: bool) {
        let window = OPEN_MATCH_SECONDS * self.meta.sample_rate as u64;
        while let Some(&l) = self.listen_opens.front() {
            let best = self
                .edge_opens
                .iter()
                .enumerate()
                .filter(|(_, (_, matched))| !matched)
                .map(|(i, (e, _))| (i, e.chunk_start.abs_diff(l.chunk_start)))
                .filter(|(_, d)| *d <= window)
                .min_by_key(|(_, d)| *d);
            match best {
                Some((i, offset)) => {
                    self.edge_opens[i].1 = true;
                    self.listen_opens.pop_front();
                    self.count_open(OpenResult::Matched);
                    self.summary.open_offsets_samples.push(offset);
                    self.metrics
                        .shadow
                        .open_offset_seconds
                        .observe(offset as f64 / self.meta.sample_rate as f64);
                }
                None if last || self.scored_until >= l.chunk_start.saturating_add(window) => {
                    self.listen_opens.pop_front();
                    self.count_open(OpenResult::ListenOnly);
                }
                None => break,
            }
        }
    }

    /// Close out the session: unmatched leftovers, metrics and the summary line.
    pub fn finish(mut self, outcome: ShadowOutcome) -> Summary {
        if outcome == ShadowOutcome::Completed {
            // listen force-flushes its partial STT buffer at teardown; do the
            // same so the tail windows are compared, not left unmatched.
            if let Some((chunk, chunk_start)) = self.stt.as_mut().and_then(SttBuffer::take_rest) {
                let _ = self.process(&chunk, chunk_start);
            }
        }
        let waiting = self.listen_waiting.len() as u64;
        if waiting > 0 {
            self.count(CompareResult::Unmatched, waiting);
        }
        self.resolve_opens(true);
        let edge_only = self.edge_opens.iter().filter(|(_, matched)| !matched).count();
        for _ in 0..edge_only {
            self.count_open(OpenResult::EdgeOnly);
        }
        self.metrics.shadow.session_ended(outcome);
        let s = &self.summary;
        let c = &s.compare;
        tracing::info!(
            target: "edge_shadow",
            event = "shadow_session",
            session = %self.meta.session_key,
            codec = self.meta.codec.as_str(),
            sample_rate = self.meta.sample_rate,
            outcome = outcome.as_str(),
            variant = s.variant.map(|v| v.as_str()).unwrap_or("none"),
            aligned = s.aligned,
            frames = s.frames,
            decode_errors = s.decode_errors,
            length_mismatches = s.length_mismatches,
            audio_seconds = s.audio_samples as f64 / self.meta.sample_rate as f64,
            edge_windows = s.edge_windows,
            agree_speech = c[0],
            agree_silence = c[1],
            edge_speech_only = c[2],
            listen_speech_only = c[3],
            not_comparable = c[4],
            unmatched = c[5],
            agreement = s.agreement().unwrap_or(f64::NAN),
            max_prob_diff = s.max_prob_diff as f64,
            opens_matched = s.opens[0],
            opens_listen_only = s.opens[1],
            opens_edge_only = s.opens[2],
        );
        self.summary
    }
}

/// The separate runtime shadow sessions run on, so libopus and Silero never
/// occupy the workers that relay `/v4/listen` and answer health checks. Its
/// worker threads bound the shadow's CPU (each builds one ORT session). The
/// runtime lives on its own thread until the pool is dropped.
pub struct ShadowPool {
    handle: tokio::runtime::Handle,
    slots: Arc<AtomicUsize>,
    max_sessions: usize,
    _stop: tokio::sync::oneshot::Sender<()>,
}

/// One reserved shadow session; released on drop.
pub struct ShadowSlot(Arc<AtomicUsize>);

impl Drop for ShadowSlot {
    fn drop(&mut self) {
        self.0.fetch_sub(1, Ordering::AcqRel);
    }
}

impl ShadowPool {
    pub fn new(threads: usize, max_sessions: usize) -> std::io::Result<ShadowPool> {
        let rt = tokio::runtime::Builder::new_multi_thread()
            .worker_threads(threads)
            .thread_name("edge-shadow")
            .enable_all()
            .build()?;
        let handle = rt.handle().clone();
        let (stop, stopped) = tokio::sync::oneshot::channel::<()>();
        std::thread::Builder::new()
            .name("edge-shadow-rt".into())
            .spawn(move || {
                rt.block_on(async {
                    let _ = stopped.await;
                });
                rt.shutdown_timeout(Duration::from_secs(1));
            })?;
        Ok(ShadowPool {
            handle,
            slots: Arc::new(AtomicUsize::new(0)),
            max_sessions,
            _stop: stop,
        })
    }

    /// Reserve a session slot before the 101, so concurrent handshakes cannot
    /// overshoot `EDGE_SHADOW_MAX_SESSIONS`.
    pub fn reserve(&self) -> Option<ShadowSlot> {
        self.slots
            .try_update(Ordering::AcqRel, Ordering::Acquire, |n| {
                (n < self.max_sessions).then_some(n + 1)
            })
            .ok()
            .map(|_| ShadowSlot(self.slots.clone()))
    }

    pub fn spawn(&self, task: impl std::future::Future<Output = ()> + Send + 'static) {
        self.handle.spawn(task);
    }
}

struct ActiveGuard(Arc<Metrics>);

impl Drop for ActiveGuard {
    fn drop(&mut self) {
        self.0.shadow.sessions_active.dec();
    }
}

/// Serve one accepted mirror until listen closes it, it fails, or the edge
/// drains. The edge only reads; it sends nothing but its close.
pub async fn serve<S>(
    mut ws: WebSocketStream<S>,
    mut core: ShadowCore,
    drain: CancellationToken,
    close_timeout: Duration,
) -> ShadowOutcome
where
    S: AsyncRead + AsyncWrite + Unpin,
{
    let metrics = core.metrics.clone();
    metrics.shadow.sessions_active.inc();
    let _active = ActiveGuard(metrics);
    let mut closing = false;
    let outcome = loop {
        tokio::select! {
            _ = drain.cancelled(), if !closing => {
                close(&mut ws, CloseCode::Away, "edge draining", close_timeout).await;
                break ShadowOutcome::Drained;
            }
            msg = ws.next() => match msg {
                // listen's close (echoed by tungstenite on the next poll), a
                // drop, or an error all end the session normally.
                None | Some(Err(_)) => break ShadowOutcome::Completed,
                Some(Ok(Message::Close(_))) => closing = true,
                Some(Ok(Message::Binary(data))) => {
                    if let Err(outcome) = core.on_message(&data) {
                        let code = match outcome {
                            ShadowOutcome::VadError => CloseCode::Error,
                            _ => CloseCode::Policy,
                        };
                        close(&mut ws, code, outcome.as_str(), close_timeout).await;
                        break outcome;
                    }
                }
                Some(Ok(Message::Text(_))) => {
                    close(&mut ws, CloseCode::Unsupported, "binary only", close_timeout).await;
                    break ShadowOutcome::ProtocolError;
                }
                Some(Ok(_)) => {}
            },
        }
    };
    core.finish(outcome);
    outcome
}

async fn close<S>(ws: &mut WebSocketStream<S>, code: CloseCode, reason: &'static str, limit: Duration)
where
    S: AsyncRead + AsyncWrite + Unpin,
{
    let frame = CloseFrame {
        code,
        reason: reason.into(),
    };
    let _ = tokio::time::timeout(limit, async {
        if ws.close(Some(frame)).await.is_ok() {
            while let Some(Ok(_)) = ws.next().await {}
        }
    })
    .await;
}

#[cfg(test)]
mod tests {
    use super::*;

    fn frame(start: u64, samples: u32, payload: &[u8]) -> Vec<u8> {
        let mut m = vec![1];
        m.extend_from_slice(&start.to_be_bytes());
        m.extend_from_slice(&samples.to_be_bytes());
        m.extend_from_slice(payload);
        m
    }

    #[test]
    fn parses_every_kind() {
        let f = frame(320, 320, &[9, 9]);
        assert_eq!(
            parse(&f).unwrap(),
            Msg::Frame {
                start: 320,
                samples: 320,
                payload: &[9, 9]
            }
        );

        let mut g = vec![2, 0, 1, 1, 0];
        g.extend_from_slice(&0.65f64.to_be_bytes());
        g.extend_from_slice(&0.5f64.to_be_bytes());
        g.extend_from_slice(&300u32.to_be_bytes());
        g.extend_from_slice(&u64::MAX.to_be_bytes());
        let Msg::GateStart { gen, params, origin } = parse(&g).unwrap() else {
            panic!()
        };
        assert_eq!((gen, origin), (1, None));
        assert_eq!(params.variant, Variant::Agc);
        assert_eq!(params.mode, Mode::Active);
        assert_eq!(params.hangover_ms, 300.0);

        let mut w = vec![3, 0, 1, 0, 0, 0, 7];
        w.extend_from_slice(&0.25f32.to_be_bytes());
        w.extend_from_slice(&0.75f32.to_be_bytes());
        assert_eq!(
            parse(&w).unwrap(),
            Msg::Windows {
                gen: 1,
                first: 7,
                probs: vec![0.25, 0.75]
            }
        );

        let mut o = vec![4, 0, 1];
        o.extend_from_slice(&960u64.to_be_bytes());
        o.extend_from_slice(&0u64.to_be_bytes());
        assert!(matches!(parse(&o).unwrap(), Msg::Open { gen: 1, .. }));
    }

    #[test]
    fn rejects_malformed_messages() {
        assert!(parse(&[]).is_err());
        assert!(parse(&[9]).is_err());
        assert!(parse(&[1, 0, 0]).is_err());
        assert!(parse(&[3, 0, 1, 0, 0, 0, 0, 1]).is_err());
        let mut g = vec![2, 0, 1, 0, 0];
        g.extend_from_slice(&1.5f64.to_be_bytes());
        g.extend_from_slice(&0.5f64.to_be_bytes());
        g.extend_from_slice(&300u32.to_be_bytes());
        g.extend_from_slice(&0u64.to_be_bytes());
        assert_eq!(parse(&g), Err(ProtocolError("gate parameters out of range")));
    }

    #[test]
    fn handshake_query_is_strict() {
        let ok = ShadowMeta::from_query("v=1&codec=opus_fs320&sample_rate=16000&session=0123456789abcdef").unwrap();
        assert_eq!(ok.codec, Codec::Opus);
        for bad in [
            "v=2&codec=opus&sample_rate=16000&session=0123456789abcdef",
            "v=1&codec=lc3&sample_rate=16000&session=0123456789abcdef",
            "v=1&codec=opus&sample_rate=44100&session=0123456789abcdef",
            "v=1&codec=pcm16&sample_rate=16000&session=0123",
            "v=1&codec=pcm16&sample_rate=16000&session=0123456789ABCDEF",
            "v=1&codec=pcm16&sample_rate=16000",
        ] {
            assert!(ShadowMeta::from_query(bad).is_err(), "{bad}");
        }
    }

    fn pcm16_core() -> ShadowCore {
        let meta = ShadowMeta::from_query("v=1&codec=pcm16&sample_rate=16000&session=0123456789abcdef").unwrap();
        ShadowCore::new(meta, Arc::new(Metrics::new(""))).unwrap()
    }

    #[test]
    fn length_mismatch_keeps_listen_positions() {
        let mut core = pcm16_core();
        // listen says 320 samples, the payload holds 300: padded to 320.
        core.on_message(&frame(0, 320, &[1; 600])).unwrap();
        assert_eq!(core.pending.back().unwrap().1.len(), 640);
        // Too long is truncated.
        core.on_message(&frame(320, 320, &[1; 700])).unwrap();
        assert_eq!(core.pending.back().unwrap().1.len(), 640);
        assert_eq!(core.summary().length_mismatches, 2);
        core.on_message(&frame(640, 320, &[1; 640])).unwrap();
    }

    #[test]
    fn non_aligned_gen_windows_are_counted_once() {
        let mut core = pcm16_core();
        let mut w = vec![3, 0, 5, 0, 0, 0, 0];
        for _ in 0..4 {
            w.extend_from_slice(&0.5f32.to_be_bytes());
        }
        core.on_message(&w).unwrap();
        core.on_message(&w).unwrap(); // exact repeat
        let mut overlap = vec![3, 0, 5, 0, 0, 0, 2]; // ordinals 2..6: two new
        for _ in 0..4 {
            overlap.extend_from_slice(&0.5f32.to_be_bytes());
        }
        core.on_message(&overlap).unwrap();
        assert_eq!(core.summary().compare[CompareResult::NotComparable.idx()], 6);
    }

    #[test]
    fn position_overflow_is_a_protocol_error() {
        let mut core = pcm16_core();
        assert_eq!(
            core.on_message(&frame(u64::MAX - 10, 320, &[0; 640])),
            Err(ShadowOutcome::ProtocolError)
        );
    }

    #[test]
    fn pool_slots_are_reserved_atomically_and_released() {
        let pool = ShadowPool::new(1, 2).unwrap();
        let a = pool.reserve().unwrap();
        let b = pool.reserve().unwrap();
        assert!(pool.reserve().is_none());
        drop(a);
        let c = pool.reserve().unwrap();
        assert!(pool.reserve().is_none());
        drop((b, c));
        assert!(pool.reserve().is_some());
    }

    #[test]
    fn gap_in_frames_is_a_desync() {
        let meta = ShadowMeta::from_query("v=1&codec=pcm16&sample_rate=16000&session=0123456789abcdef").unwrap();
        let mut core = ShadowCore::new(meta, Arc::new(Metrics::new(""))).unwrap();
        core.on_message(&frame(0, 320, &[0; 640])).unwrap();
        assert_eq!(core.on_message(&frame(960, 320, &[0; 640])), Err(ShadowOutcome::Desync));
    }
}
