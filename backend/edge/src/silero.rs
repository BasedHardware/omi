//! Silero VAD v6 through ONNX Runtime (`ort`), mirroring listen's
//! `backend/utils/stt/local_vad.py`: 512-sample windows at 16 kHz with the
//! previous window's 64-sample tail prepended, recurrent state carried per
//! stream, one intra-op and one inter-op thread, sequential execution.
//!
//! The model bytes are loaded once per process ([`init`]); each worker thread
//! builds its own session on first use, so `run` never takes a lock.
use std::cell::RefCell;
use std::fmt;
use std::sync::OnceLock;

use ort::session::builder::GraphOptimizationLevel;
use ort::session::Session;
use ort::value::Tensor;

pub const SAMPLE_RATE: i64 = 16_000;
/// Samples per window at 16 kHz (32 ms).
pub const WINDOW: usize = 512;
/// Tail of the previous window prepended to each call.
pub const CONTEXT: usize = 64;
const STATE_LEN: usize = 2 * 128;

static MODEL: OnceLock<Vec<u8>> = OnceLock::new();

thread_local! {
    static SESSION: RefCell<Option<Session>> = const { RefCell::new(None) };
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct VadError(pub String);

impl fmt::Display for VadError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.0)
    }
}

impl std::error::Error for VadError {}

fn err(e: impl fmt::Display) -> VadError {
    VadError(e.to_string())
}

/// Load the model file once and check that it runs. Later calls with any
/// path are no-ops (one model per process).
pub fn init(path: &str) -> Result<(), VadError> {
    if MODEL.get().is_none() {
        let bytes = std::fs::read(path).map_err(|e| VadError(format!("read {path}: {e}")))?;
        let _ = MODEL.set(bytes);
    }
    // Fail at startup, not on the first session, if the runtime cannot load it.
    let mut probe = Stream::new();
    probe.run(&[0.0; WINDOW]).map(|_| ())
}

pub fn initialized() -> bool {
    MODEL.get().is_some()
}

fn build_session(model: &[u8]) -> Result<Session, VadError> {
    Session::builder()
        .map_err(err)?
        .with_optimization_level(GraphOptimizationLevel::Level3)
        .map_err(err)?
        .with_intra_threads(1)
        .map_err(err)?
        .with_inter_threads(1)
        .map_err(err)?
        .with_parallel_execution(false)
        .map_err(err)?
        .commit_from_memory(model)
        .map_err(err)
}

/// Recurrent state and context of one VAD stream (listen's `make_fresh_state`).
#[derive(Clone)]
pub struct Stream {
    state: Vec<f32>,
    context: [f32; CONTEXT],
}

impl Default for Stream {
    fn default() -> Self {
        Self::new()
    }
}

impl Stream {
    pub fn new() -> Self {
        Stream {
            state: vec![0.0; STATE_LEN],
            context: [0.0; CONTEXT],
        }
    }

    /// Speech probability of one 512-sample window; advances the state.
    pub fn run(&mut self, window: &[f32]) -> Result<f32, VadError> {
        if window.len() != WINDOW {
            return Err(VadError(format!("window has {} samples, want {WINDOW}", window.len())));
        }
        let model = MODEL.get().ok_or_else(|| VadError("silero model not loaded".into()))?;
        let mut input = Vec::with_capacity(CONTEXT + WINDOW);
        input.extend_from_slice(&self.context);
        input.extend_from_slice(window);
        let state = self.state.clone();
        let (prob, next_state) = SESSION.with(|cell| -> Result<(f32, Vec<f32>), VadError> {
            let mut slot = cell.borrow_mut();
            if slot.is_none() {
                *slot = Some(build_session(model)?);
            }
            let session = slot.as_mut().expect("session built above");
            let outputs = session
                .run(ort::inputs![
                    "input" => Tensor::from_array(([1usize, CONTEXT + WINDOW], input)).map_err(err)?,
                    "state" => Tensor::from_array(([2usize, 1, 128], state)).map_err(err)?,
                    "sr" => Tensor::from_array(([0usize; 0], vec![SAMPLE_RATE])).map_err(err)?,
                ])
                .map_err(err)?;
            let (_, p) = outputs["output"].try_extract_tensor::<f32>().map_err(err)?;
            let (_, s) = outputs["stateN"].try_extract_tensor::<f32>().map_err(err)?;
            let prob = *p.first().ok_or_else(|| VadError("empty output".into()))?;
            Ok((prob, s.to_vec()))
        })?;
        if next_state.len() != STATE_LEN {
            return Err(VadError(format!("state has {} values", next_state.len())));
        }
        // No range check: listen's streaming gate compares the raw value
        // (`prob > threshold`), so a NaN is silence on both sides.
        self.state = next_state;
        self.context.copy_from_slice(&window[WINDOW - CONTEXT..]);
        Ok(prob)
    }
}
