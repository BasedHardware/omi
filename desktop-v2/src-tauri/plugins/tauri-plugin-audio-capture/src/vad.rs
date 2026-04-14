//! VAD gate service — Rust port of Swift `VADGateService`.
//!
//! Runs Silero VAD (v5) on stereo Int16 audio. One model per channel (mic +
//! system). Audio is gated when BOTH channels are silent; we emit speech +
//! hangover with a pre-roll buffer.
//!
//! Ported line-for-line from `../desktop/Desktop/Sources/VADGateService.swift`.
//! Constants, hysteresis, frame-history smoothing, and state-machine transitions
//! match the Swift implementation exactly.

use std::path::{Path, PathBuf};
use std::sync::{Mutex, OnceLock};
use std::time::Instant;

use ndarray::{Array1, Array2, Array3};
use ort::session::Session;
use ort::value::Tensor;

// ---------------------------------------------------------------------------
// Constants (match Swift)
// ---------------------------------------------------------------------------

/// Pre-roll length kept before the first speech frame.
const PRE_ROLL_MS: f64 = 500.0;
/// Streaming mode hangover — controls finalize timing.
const HANGOVER_MS: f64 = 4000.0;
/// Batch mode hangover — controls chunk boundary (user-visible latency).
const BATCH_HANGOVER_MS: f64 = 2000.0;
/// Deepgram keepalive interval.
const KEEPALIVE_SEC: f64 = 20.0;
/// Silero VAD window size at 16 kHz.
const VAD_WINDOW_SAMPLES: usize = 512;
/// Audio sample rate.
const SAMPLE_RATE: u32 = 16_000;

/// Probability above which a frame counts as speech.
const SPEECH_THRESHOLD: f32 = 0.5;
/// Probability below which a frame counts as silence.
const SILENCE_THRESHOLD: f32 = 0.35;
/// Number of frames in the smoothing window.
const FRAME_HISTORY_SIZE: usize = 10;
/// Minimum speech frames in window to declare speech.
const MIN_SPEECH_FRAMES: usize = 3;

/// Stereo Int16 frame size (2 channels * 2 bytes).
const BYTES_PER_FRAME: usize = 4;

/// Combined Silero v5 state tensor: [2, 1, 128].
const STATE_SIZE: usize = 2 * 1 * 128;

// ---------------------------------------------------------------------------
// Silero VAD ONNX wrapper
// ---------------------------------------------------------------------------

/// Wraps a single Silero VAD ONNX session with its own hidden state.
pub struct SileroVADModel {
    session: Session,
    /// Combined h+c state for Silero v5 — flat [2*1*128] = 256 floats.
    state: Vec<f32>,
}

impl SileroVADModel {
    pub fn new(model_path: &Path) -> Result<Self, String> {
        let session = Session::builder()
            .map_err(|e| format!("ORT: session builder failed: {}", e))?
            .with_intra_threads(1)
            .map_err(|e| format!("ORT: set intra_threads failed: {}", e))?
            .commit_from_file(model_path)
            .map_err(|e| format!("ORT: load model {} failed: {}", model_path.display(), e))?;

        Ok(Self {
            session,
            state: vec![0.0_f32; STATE_SIZE],
        })
    }

    /// Run inference on 512 Float32 samples. Returns speech probability.
    pub fn predict(&mut self, samples: &[f32]) -> f32 {
        debug_assert_eq!(samples.len(), VAD_WINDOW_SAMPLES);

        // Input tensor: [1, 512]
        let input_arr =
            match Array2::from_shape_vec((1, VAD_WINDOW_SAMPLES), samples.to_vec()) {
                Ok(a) => a,
                Err(e) => {
                    tracing::warn!("VAD: input reshape failed: {}", e);
                    return 0.0;
                }
            };
        let input_tensor = match Tensor::from_array(input_arr) {
            Ok(t) => t,
            Err(e) => {
                tracing::warn!("VAD: input tensor creation failed: {}", e);
                return 0.0;
            }
        };

        // State tensor: [2, 1, 128]
        let state_arr = match Array3::from_shape_vec((2, 1, 128), self.state.clone()) {
            Ok(a) => a,
            Err(e) => {
                tracing::warn!("VAD: state reshape failed: {}", e);
                return 0.0;
            }
        };
        let state_tensor = match Tensor::from_array(state_arr) {
            Ok(t) => t,
            Err(e) => {
                tracing::warn!("VAD: state tensor creation failed: {}", e);
                return 0.0;
            }
        };

        // Sample rate: scalar Int64
        let sr_arr = Array1::from_vec(vec![SAMPLE_RATE as i64]);
        let sr_tensor = match Tensor::from_array(sr_arr) {
            Ok(t) => t,
            Err(e) => {
                tracing::warn!("VAD: sr tensor creation failed: {}", e);
                return 0.0;
            }
        };

        let outputs = match self.session.run(ort::inputs![
            "input" => input_tensor,
            "state" => state_tensor,
            "sr" => sr_tensor,
        ]) {
            Ok(o) => o,
            Err(e) => {
                tracing::warn!("VAD: inference failed: {}", e);
                return 0.0;
            }
        };

        // Extract probability from "output" ([1, 1]).
        let probability = match outputs.get("output") {
            Some(v) => match v.try_extract_array::<f32>() {
                Ok(arr) => arr.iter().next().copied().unwrap_or(0.0),
                Err(e) => {
                    tracing::warn!("VAD: output extract failed: {}", e);
                    return 0.0;
                }
            },
            None => {
                tracing::warn!("VAD: output missing 'output'");
                return 0.0;
            }
        };

        // Update combined state from "stateN" ([2, 1, 128]).
        if let Some(state_n) = outputs.get("stateN") {
            match state_n.try_extract_array::<f32>() {
                Ok(arr) => {
                    let slice: Vec<f32> = arr.iter().copied().collect();
                    if slice.len() >= STATE_SIZE {
                        self.state[..STATE_SIZE].copy_from_slice(&slice[..STATE_SIZE]);
                    }
                }
                Err(e) => tracing::warn!("VAD: stateN extract failed: {}", e),
            }
        }

        probability
    }

    pub fn reset_states(&mut self) {
        self.state.fill(0.0);
    }
}

// ---------------------------------------------------------------------------
// Gate state machine
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum GateState {
    Silence,
    Speech,
    Hangover,
}

/// Streaming mode output.
#[derive(Debug, Clone)]
pub struct GateOutput {
    pub audio_to_send: Vec<u8>,
    pub should_finalize: bool,
}

/// Batch mode output.
#[derive(Debug, Clone)]
pub struct BatchGateOutput {
    /// Complete speech audio (None while still accumulating).
    pub audio_buffer: Option<Vec<u8>>,
    /// Wall-time (seconds since VAD start) when speech began.
    pub speech_start_wall_time: f64,
    /// True when hangover→silence emits the buffer.
    pub is_complete: bool,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum VadDecision {
    Speech,
    Silence,
    /// Not enough evidence — maintain current state.
    Hold,
}

fn evaluate_frame_history(history: &[f32]) -> VadDecision {
    if history.is_empty() {
        return VadDecision::Hold;
    }

    let speech_frames = history.iter().filter(|&&p| p > SPEECH_THRESHOLD).count();
    let silence_frames = history.iter().filter(|&&p| p < SILENCE_THRESHOLD).count();

    if speech_frames >= MIN_SPEECH_FRAMES {
        VadDecision::Speech
    } else if silence_frames > history.len() / 2 {
        VadDecision::Silence
    } else {
        VadDecision::Hold
    }
}

fn append_to_history(history: &mut Vec<f32>, prob: f32) {
    history.push(prob);
    if history.len() > FRAME_HISTORY_SIZE {
        let excess = history.len() - FRAME_HISTORY_SIZE;
        history.drain(..excess);
    }
}

/// Deinterleave stereo Int16 bytes into (mic, sys) Float32 arrays,
/// normalized to [-1.0, 1.0].
fn deinterleave(stereo_data: &[u8]) -> (Vec<f32>, Vec<f32>) {
    let sample_count = stereo_data.len() / 2;
    let frame_count = sample_count / 2;

    let mut mic = Vec::with_capacity(frame_count);
    let mut sys = Vec::with_capacity(frame_count);

    for i in 0..frame_count {
        let base = i * 4;
        let mic_s = i16::from_le_bytes([stereo_data[base], stereo_data[base + 1]]);
        let sys_s = i16::from_le_bytes([stereo_data[base + 2], stereo_data[base + 3]]);
        mic.push(mic_s as f32 / 32768.0);
        sys.push(sys_s as f32 / 32768.0);
    }

    (mic, sys)
}

// ---------------------------------------------------------------------------
// Deepgram wall-clock timestamp mapper
// ---------------------------------------------------------------------------

struct DgWallMapperInner {
    checkpoints: Vec<(f64, f64)>,
    dg_cursor_sec: f64,
    sending: bool,
}

/// Maps Deepgram audio-time timestamps to wall-clock-relative timestamps.
pub struct DgWallMapper {
    inner: Mutex<DgWallMapperInner>,
}

impl DgWallMapper {
    const MAX_CHECKPOINTS: usize = 500;

    pub fn new() -> Self {
        Self {
            inner: Mutex::new(DgWallMapperInner {
                checkpoints: Vec::new(),
                dg_cursor_sec: 0.0,
                sending: false,
            }),
        }
    }

    pub fn on_audio_sent(&self, chunk_duration: f64, wall_time: f64) {
        let mut g = self.inner.lock().unwrap();
        if !g.sending {
            let mut adjusted_wall = wall_time;
            if let Some(last) = g.checkpoints.last() {
                let min_wall = last.1 + (g.dg_cursor_sec - last.0);
                if min_wall > adjusted_wall {
                    adjusted_wall = min_wall;
                }
            }
            let cursor = g.dg_cursor_sec;
            g.checkpoints.push((cursor, adjusted_wall));
            if g.checkpoints.len() > Self::MAX_CHECKPOINTS {
                // Keep first + suffix(max-1), matching Swift.
                let first = g.checkpoints[0];
                let split_at = g.checkpoints.len() - (Self::MAX_CHECKPOINTS - 1);
                let keep = g.checkpoints.split_off(split_at);
                g.checkpoints.clear();
                g.checkpoints.push(first);
                g.checkpoints.extend(keep);
            }
            g.sending = true;
        }
        g.dg_cursor_sec += chunk_duration;
    }

    pub fn on_silence_skipped(&self) {
        let mut g = self.inner.lock().unwrap();
        g.sending = false;
    }

    pub fn dg_to_wall(&self, dg_sec: f64) -> f64 {
        let cps = {
            let g = self.inner.lock().unwrap();
            g.checkpoints.clone()
        };
        if cps.is_empty() {
            return dg_sec;
        }

        // Binary search for greatest checkpoint whose dgSec <= dg_sec.
        let mut lo = 0usize;
        let mut hi = cps.len() - 1;
        while lo < hi {
            let mid = (lo + hi + 1) / 2;
            if cps[mid].0 <= dg_sec {
                lo = mid;
            } else {
                hi = mid - 1;
            }
        }
        let cp = cps[lo];
        cp.1 + (dg_sec - cp.0)
    }
}

impl Default for DgWallMapper {
    fn default() -> Self {
        Self::new()
    }
}

// ---------------------------------------------------------------------------
// VAD gate service
// ---------------------------------------------------------------------------

/// On-device VAD gate matching the Swift `VADGateService`.
pub struct VADGateService {
    // VAD models per channel.
    mic_vad: Option<SileroVADModel>,
    sys_vad: Option<SileroVADModel>,

    // VAD buffers (accumulate until >= 512 samples).
    mic_vad_buffer: Vec<f32>,
    sys_vad_buffer: Vec<f32>,

    // Probability history (streaming mode).
    mic_prob_history: Vec<f32>,
    sys_prob_history: Vec<f32>,

    // State machine.
    state: GateState,
    audio_cursor_ms: f64,
    last_speech_ms: f64,

    // Pre-roll.
    pre_roll_chunks: Vec<Vec<u8>>,
    pre_roll_total_ms: f64,

    // Timestamp mapper.
    pub dg_wall_mapper: DgWallMapper,

    // Timing (wall time is seconds since construction).
    start_instant: Instant,
    first_audio_wall_time: Option<f64>,
    last_send_wall_time: Option<f64>,

    // Metrics.
    bytes_received: usize,
    bytes_sent: usize,
    chunks_total: u64,
    chunks_speech: u64,
    chunks_silence: u64,
    finalize_count: u64,
    keepalive_count: u64,
    last_metrics_log_time: f64,

    // Batch mode state.
    batch_audio_buffer: Vec<u8>,
    batch_speech_start_wall_time: f64,
    batch_state: GateState,
    batch_last_speech_ms: f64,
    batch_audio_cursor_ms: f64,
    batch_pre_roll_chunks: Vec<Vec<u8>>,
    batch_pre_roll_total_ms: f64,
    batch_mic_vad_buffer: Vec<f32>,
    batch_sys_vad_buffer: Vec<f32>,
    batch_mic_vad: Option<SileroVADModel>,
    batch_sys_vad: Option<SileroVADModel>,
    batch_mic_prob_history: Vec<f32>,
    batch_sys_prob_history: Vec<f32>,

    pub model_available: bool,
}

impl VADGateService {
    const METRICS_LOG_INTERVAL: f64 = 30.0;

    /// Build a VAD gate loading the Silero ONNX model from the plugin bundle.
    pub fn new() -> Self {
        let model_path = find_model_path();

        let mic = model_path.as_ref().and_then(|p| Self::load_model(p, "mic"));
        let sys = model_path.as_ref().and_then(|p| Self::load_model(p, "sys"));
        let b_mic = model_path
            .as_ref()
            .and_then(|p| Self::load_model(p, "batch_mic"));
        let b_sys = model_path
            .as_ref()
            .and_then(|p| Self::load_model(p, "batch_sys"));

        let model_available = mic.is_some() && sys.is_some();
        if model_available {
            tracing::info!("VADGateService: Initialized with Silero VAD models");
        } else {
            tracing::warn!("VADGateService: Model load failed — running in pass-through mode");
        }

        Self {
            mic_vad: mic,
            sys_vad: sys,
            mic_vad_buffer: Vec::new(),
            sys_vad_buffer: Vec::new(),
            mic_prob_history: Vec::new(),
            sys_prob_history: Vec::new(),
            state: GateState::Silence,
            audio_cursor_ms: 0.0,
            last_speech_ms: 0.0,
            pre_roll_chunks: Vec::new(),
            pre_roll_total_ms: 0.0,
            dg_wall_mapper: DgWallMapper::new(),
            start_instant: Instant::now(),
            first_audio_wall_time: None,
            last_send_wall_time: None,
            bytes_received: 0,
            bytes_sent: 0,
            chunks_total: 0,
            chunks_speech: 0,
            chunks_silence: 0,
            finalize_count: 0,
            keepalive_count: 0,
            last_metrics_log_time: 0.0,
            batch_audio_buffer: Vec::new(),
            batch_speech_start_wall_time: 0.0,
            batch_state: GateState::Silence,
            batch_last_speech_ms: 0.0,
            batch_audio_cursor_ms: 0.0,
            batch_pre_roll_chunks: Vec::new(),
            batch_pre_roll_total_ms: 0.0,
            batch_mic_vad_buffer: Vec::new(),
            batch_sys_vad_buffer: Vec::new(),
            batch_mic_vad: b_mic,
            batch_sys_vad: b_sys,
            batch_mic_prob_history: Vec::new(),
            batch_sys_prob_history: Vec::new(),
            model_available,
        }
    }

    fn load_model(path: &Path, tag: &str) -> Option<SileroVADModel> {
        match SileroVADModel::new(path) {
            Ok(m) => Some(m),
            Err(e) => {
                tracing::warn!("VADGateService: failed to load {} model: {}", tag, e);
                None
            }
        }
    }

    fn now_wall(&self) -> f64 {
        self.start_instant.elapsed().as_secs_f64()
    }

    // -----------------------------------------------------------------------
    // Streaming mode
    // -----------------------------------------------------------------------

    /// Process stereo Int16 audio through the VAD gate. Returns audio to
    /// forward (possibly empty) and whether to finalize the downstream stream.
    pub fn process_audio(&mut self, stereo_data: &[u8]) -> GateOutput {
        if !self.model_available {
            return GateOutput {
                audio_to_send: stereo_data.to_vec(),
                should_finalize: false,
            };
        }

        let wall_time = self.now_wall();
        if self.first_audio_wall_time.is_none() {
            self.first_audio_wall_time = Some(wall_time);
            self.last_metrics_log_time = wall_time;
        }
        let wall_rel = wall_time - self.first_audio_wall_time.unwrap_or(wall_time);

        let num_frames = stereo_data.len() / BYTES_PER_FRAME;
        let chunk_ms = num_frames as f64 * 1000.0 / SAMPLE_RATE as f64;
        let chunk_duration_sec = num_frames as f64 / SAMPLE_RATE as f64;
        self.audio_cursor_ms += chunk_ms;

        self.chunks_total += 1;
        self.bytes_received += stereo_data.len();

        let (mic_samples, sys_samples) = deinterleave(stereo_data);

        self.mic_vad_buffer.extend_from_slice(&mic_samples);
        self.sys_vad_buffer.extend_from_slice(&sys_samples);

        // Drain mic buffer in 512-sample windows.
        if let Some(vad) = self.mic_vad.as_mut() {
            while self.mic_vad_buffer.len() >= VAD_WINDOW_SAMPLES {
                let window: Vec<f32> =
                    self.mic_vad_buffer.drain(..VAD_WINDOW_SAMPLES).collect();
                let prob = vad.predict(&window);
                append_to_history(&mut self.mic_prob_history, prob);
            }
        }
        if let Some(vad) = self.sys_vad.as_mut() {
            while self.sys_vad_buffer.len() >= VAD_WINDOW_SAMPLES {
                let window: Vec<f32> =
                    self.sys_vad_buffer.drain(..VAD_WINDOW_SAMPLES).collect();
                let prob = vad.predict(&window);
                append_to_history(&mut self.sys_prob_history, prob);
            }
        }

        // Cap buffers to one window to avoid unbounded growth.
        if self.mic_vad_buffer.len() > VAD_WINDOW_SAMPLES {
            let cut = self.mic_vad_buffer.len() - VAD_WINDOW_SAMPLES;
            self.mic_vad_buffer.drain(..cut);
        }
        if self.sys_vad_buffer.len() > VAD_WINDOW_SAMPLES {
            let cut = self.sys_vad_buffer.len() - VAD_WINDOW_SAMPLES;
            self.sys_vad_buffer.drain(..cut);
        }

        let mic_dec = evaluate_frame_history(&self.mic_prob_history);
        let sys_dec = evaluate_frame_history(&self.sys_prob_history);

        let is_speech = decide_is_speech(mic_dec, sys_dec, self.state);

        if is_speech {
            self.last_speech_ms = self.audio_cursor_ms;
            self.chunks_speech += 1;
        } else {
            self.chunks_silence += 1;
        }

        let output = self.update_state(
            stereo_data,
            is_speech,
            wall_rel,
            chunk_duration_sec,
            chunk_ms,
            wall_time,
        );

        self.bytes_sent += output.audio_to_send.len();
        if output.should_finalize {
            self.finalize_count += 1;
        }

        if wall_time - self.last_metrics_log_time >= Self::METRICS_LOG_INTERVAL {
            self.last_metrics_log_time = wall_time;
            self.log_metrics();
        }

        output
    }

    /// Check if a Deepgram keepalive should be sent.
    pub fn needs_keepalive(&mut self) -> bool {
        let Some(first) = self.first_audio_wall_time else {
            return false;
        };
        let ref_time = self.last_send_wall_time.unwrap_or(first);
        let now = self.now_wall();
        if now - ref_time >= KEEPALIVE_SEC {
            self.keepalive_count += 1;
            self.last_send_wall_time = Some(now);
            true
        } else {
            false
        }
    }

    pub fn remap_timestamp(&self, start: f64, end: f64) -> (f64, f64) {
        (
            self.dg_wall_mapper.dg_to_wall(start),
            self.dg_wall_mapper.dg_to_wall(end),
        )
    }

    fn update_state(
        &mut self,
        pcm_data: &[u8],
        is_speech: bool,
        wall_rel: f64,
        chunk_duration_sec: f64,
        chunk_ms: f64,
        wall_time: f64,
    ) -> GateOutput {
        match self.state {
            GateState::Silence => {
                self.pre_roll_chunks.push(pcm_data.to_vec());
                self.pre_roll_total_ms += chunk_ms;
                while self.pre_roll_total_ms > PRE_ROLL_MS && self.pre_roll_chunks.len() > 1 {
                    let evicted = self.pre_roll_chunks.remove(0);
                    let evicted_ms = (evicted.len() / BYTES_PER_FRAME) as f64 * 1000.0
                        / SAMPLE_RATE as f64;
                    self.pre_roll_total_ms -= evicted_ms;
                }

                if is_speech {
                    self.state = GateState::Speech;

                    let mut pre_roll_audio: Vec<u8> = Vec::new();
                    for chunk in &self.pre_roll_chunks {
                        pre_roll_audio.extend_from_slice(chunk);
                    }
                    let pre_roll_duration = (pre_roll_audio.len() / BYTES_PER_FRAME) as f64
                        / SAMPLE_RATE as f64;
                    let pre_roll_wall_rel =
                        (wall_rel - pre_roll_duration + chunk_duration_sec).max(0.0);

                    self.pre_roll_chunks.clear();
                    self.pre_roll_total_ms = 0.0;

                    self.dg_wall_mapper
                        .on_audio_sent(pre_roll_duration, pre_roll_wall_rel);
                    self.last_send_wall_time = Some(wall_time);

                    GateOutput {
                        audio_to_send: pre_roll_audio,
                        should_finalize: false,
                    }
                } else {
                    self.dg_wall_mapper.on_silence_skipped();
                    GateOutput {
                        audio_to_send: Vec::new(),
                        should_finalize: false,
                    }
                }
            }

            GateState::Speech => {
                self.dg_wall_mapper.on_audio_sent(chunk_duration_sec, wall_rel);
                self.last_send_wall_time = Some(wall_time);

                if !is_speech {
                    self.state = GateState::Hangover;
                }

                GateOutput {
                    audio_to_send: pcm_data.to_vec(),
                    should_finalize: false,
                }
            }

            GateState::Hangover => {
                let time_since_speech_ms = self.audio_cursor_ms - self.last_speech_ms;

                if is_speech {
                    self.state = GateState::Speech;
                    self.dg_wall_mapper.on_audio_sent(chunk_duration_sec, wall_rel);
                    self.last_send_wall_time = Some(wall_time);
                    return GateOutput {
                        audio_to_send: pcm_data.to_vec(),
                        should_finalize: false,
                    };
                }

                if time_since_speech_ms > HANGOVER_MS {
                    self.state = GateState::Silence;
                    self.pre_roll_chunks.clear();
                    self.pre_roll_total_ms = 0.0;
                    self.pre_roll_chunks.push(pcm_data.to_vec());
                    self.pre_roll_total_ms = chunk_ms;
                    self.dg_wall_mapper.on_silence_skipped();
                    return GateOutput {
                        audio_to_send: Vec::new(),
                        should_finalize: true,
                    };
                }

                self.dg_wall_mapper.on_audio_sent(chunk_duration_sec, wall_rel);
                self.last_send_wall_time = Some(wall_time);
                GateOutput {
                    audio_to_send: pcm_data.to_vec(),
                    should_finalize: false,
                }
            }
        }
    }

    fn log_metrics(&self) {
        let bytes_skipped = self.bytes_received.saturating_sub(self.bytes_sent);
        let savings_ratio = if self.bytes_received > 0 {
            bytes_skipped as f64 / self.bytes_received as f64 * 100.0
        } else {
            0.0
        };
        let session_sec = self.audio_cursor_ms / 1000.0;
        let dg_cost_per_sec = 0.0043 / 60.0; // Nova-3: $0.0043/min
        let cost_without = session_sec * dg_cost_per_sec;
        let cost_with = session_sec * (1.0 - savings_ratio / 100.0) * dg_cost_per_sec;
        tracing::info!(
            "VADGate metrics: state={:?} chunks={} (speech={} silence={}) \
             received={:.1}KB sent={:.1}KB skipped={:.1}KB savings={:.1}% \
             finalizes={} keepalives={} session={:.0}s dgCost=${:.4}→${:.4}",
            self.state,
            self.chunks_total,
            self.chunks_speech,
            self.chunks_silence,
            self.bytes_received as f64 / 1024.0,
            self.bytes_sent as f64 / 1024.0,
            bytes_skipped as f64 / 1024.0,
            savings_ratio,
            self.finalize_count,
            self.keepalive_count,
            session_sec,
            cost_without,
            cost_with,
        );
    }

    // -----------------------------------------------------------------------
    // Batch mode
    // -----------------------------------------------------------------------

    /// Accumulate stereo Int16 audio and emit a complete buffer at hangover→silence.
    pub fn process_audio_batch(&mut self, stereo_data: &[u8]) -> BatchGateOutput {
        if !self.model_available {
            return BatchGateOutput {
                audio_buffer: Some(stereo_data.to_vec()),
                speech_start_wall_time: self.now_wall(),
                is_complete: true,
            };
        }

        let wall_time = self.now_wall();

        let num_frames = stereo_data.len() / BYTES_PER_FRAME;
        let chunk_ms = num_frames as f64 * 1000.0 / SAMPLE_RATE as f64;
        self.batch_audio_cursor_ms += chunk_ms;

        let (mic_samples, sys_samples) = deinterleave(stereo_data);

        self.batch_mic_vad_buffer.extend_from_slice(&mic_samples);
        self.batch_sys_vad_buffer.extend_from_slice(&sys_samples);

        if let Some(vad) = self.batch_mic_vad.as_mut() {
            while self.batch_mic_vad_buffer.len() >= VAD_WINDOW_SAMPLES {
                let window: Vec<f32> = self
                    .batch_mic_vad_buffer
                    .drain(..VAD_WINDOW_SAMPLES)
                    .collect();
                let prob = vad.predict(&window);
                append_to_history(&mut self.batch_mic_prob_history, prob);
            }
        }
        if let Some(vad) = self.batch_sys_vad.as_mut() {
            while self.batch_sys_vad_buffer.len() >= VAD_WINDOW_SAMPLES {
                let window: Vec<f32> = self
                    .batch_sys_vad_buffer
                    .drain(..VAD_WINDOW_SAMPLES)
                    .collect();
                let prob = vad.predict(&window);
                append_to_history(&mut self.batch_sys_prob_history, prob);
            }
        }

        if self.batch_mic_vad_buffer.len() > VAD_WINDOW_SAMPLES {
            let cut = self.batch_mic_vad_buffer.len() - VAD_WINDOW_SAMPLES;
            self.batch_mic_vad_buffer.drain(..cut);
        }
        if self.batch_sys_vad_buffer.len() > VAD_WINDOW_SAMPLES {
            let cut = self.batch_sys_vad_buffer.len() - VAD_WINDOW_SAMPLES;
            self.batch_sys_vad_buffer.drain(..cut);
        }

        let mic_dec = evaluate_frame_history(&self.batch_mic_prob_history);
        let sys_dec = evaluate_frame_history(&self.batch_sys_prob_history);

        let is_speech = decide_is_speech(mic_dec, sys_dec, self.batch_state);
        if is_speech {
            self.batch_last_speech_ms = self.batch_audio_cursor_ms;
        }

        match self.batch_state {
            GateState::Silence => {
                self.batch_pre_roll_chunks.push(stereo_data.to_vec());
                self.batch_pre_roll_total_ms += chunk_ms;
                while self.batch_pre_roll_total_ms > PRE_ROLL_MS
                    && self.batch_pre_roll_chunks.len() > 1
                {
                    let evicted = self.batch_pre_roll_chunks.remove(0);
                    let evicted_ms = (evicted.len() / BYTES_PER_FRAME) as f64 * 1000.0
                        / SAMPLE_RATE as f64;
                    self.batch_pre_roll_total_ms -= evicted_ms;
                }

                if is_speech {
                    self.batch_state = GateState::Speech;
                    self.batch_audio_buffer.clear();
                    for chunk in &self.batch_pre_roll_chunks {
                        self.batch_audio_buffer.extend_from_slice(chunk);
                    }
                    self.batch_speech_start_wall_time =
                        wall_time - (self.batch_pre_roll_total_ms / 1000.0);
                    self.batch_pre_roll_chunks.clear();
                    self.batch_pre_roll_total_ms = 0.0;
                }

                BatchGateOutput {
                    audio_buffer: None,
                    speech_start_wall_time: 0.0,
                    is_complete: false,
                }
            }

            GateState::Speech => {
                self.batch_audio_buffer.extend_from_slice(stereo_data);
                if !is_speech {
                    self.batch_state = GateState::Hangover;
                }
                BatchGateOutput {
                    audio_buffer: None,
                    speech_start_wall_time: self.batch_speech_start_wall_time,
                    is_complete: false,
                }
            }

            GateState::Hangover => {
                self.batch_audio_buffer.extend_from_slice(stereo_data);
                let time_since_speech_ms =
                    self.batch_audio_cursor_ms - self.batch_last_speech_ms;

                if is_speech {
                    self.batch_state = GateState::Speech;
                    return BatchGateOutput {
                        audio_buffer: None,
                        speech_start_wall_time: self.batch_speech_start_wall_time,
                        is_complete: false,
                    };
                }

                if time_since_speech_ms > BATCH_HANGOVER_MS {
                    self.batch_state = GateState::Silence;
                    let completed = std::mem::take(&mut self.batch_audio_buffer);
                    let start_time = self.batch_speech_start_wall_time;
                    self.batch_pre_roll_chunks.clear();
                    self.batch_pre_roll_total_ms = 0.0;
                    self.batch_pre_roll_chunks.push(stereo_data.to_vec());
                    self.batch_pre_roll_total_ms = chunk_ms;

                    let duration_sec =
                        (completed.len() / BYTES_PER_FRAME) as f64 / SAMPLE_RATE as f64;
                    tracing::info!(
                        "VADGate [batch]: Speech chunk complete — {} bytes ({:.1}s)",
                        completed.len(),
                        duration_sec
                    );

                    return BatchGateOutput {
                        audio_buffer: Some(completed),
                        speech_start_wall_time: start_time,
                        is_complete: true,
                    };
                }

                BatchGateOutput {
                    audio_buffer: None,
                    speech_start_wall_time: self.batch_speech_start_wall_time,
                    is_complete: false,
                }
            }
        }
    }

    /// Flush remaining batch audio buffer (call on recording stop).
    pub fn flush_batch_buffer(&mut self) -> Option<BatchGateOutput> {
        if self.batch_state == GateState::Silence || self.batch_audio_buffer.is_empty() {
            return None;
        }

        let completed = std::mem::take(&mut self.batch_audio_buffer);
        let start_time = self.batch_speech_start_wall_time;
        self.batch_state = GateState::Silence;
        self.batch_pre_roll_chunks.clear();
        self.batch_pre_roll_total_ms = 0.0;

        let duration_sec = (completed.len() / BYTES_PER_FRAME) as f64 / SAMPLE_RATE as f64;
        tracing::info!(
            "VADGate [batch]: Flushing remaining buffer — {} bytes ({:.1}s)",
            completed.len(),
            duration_sec
        );

        Some(BatchGateOutput {
            audio_buffer: Some(completed),
            speech_start_wall_time: start_time,
            is_complete: true,
        })
    }
}

impl Default for VADGateService {
    fn default() -> Self {
        Self::new()
    }
}

/// Speech if either channel detects speech; silence only if both say silence;
/// otherwise hold the previous state.
fn decide_is_speech(mic: VadDecision, sys: VadDecision, prev_state: GateState) -> bool {
    if mic == VadDecision::Speech || sys == VadDecision::Speech {
        true
    } else if mic == VadDecision::Silence && sys == VadDecision::Silence {
        false
    } else {
        prev_state == GateState::Speech || prev_state == GateState::Hangover
    }
}

// ---------------------------------------------------------------------------
// Model path discovery
// ---------------------------------------------------------------------------

static CACHED_MODEL_PATH: OnceLock<Option<PathBuf>> = OnceLock::new();

fn find_model_path() -> Option<PathBuf> {
    CACHED_MODEL_PATH
        .get_or_init(|| {
            // 1. Next to the executable (production bundle).
            if let Ok(exe) = std::env::current_exe() {
                if let Some(dir) = exe.parent() {
                    let candidate = dir.join("models").join("silero_vad.onnx");
                    if candidate.is_file() {
                        return Some(candidate);
                    }
                    let mac_candidate = dir.join("../Resources/models/silero_vad.onnx");
                    if mac_candidate.is_file() {
                        return Some(mac_candidate);
                    }
                }
            }
            // 2. Plugin source directory (dev mode).
            let dev = Path::new(env!("CARGO_MANIFEST_DIR"))
                .join("models")
                .join("silero_vad.onnx");
            if dev.is_file() {
                return Some(dev);
            }
            None
        })
        .clone()
}
