//! Port of listen's VAD gate decision path (`VADStreamingGate` in
//! `backend/utils/stt/vad_gate.py`), without the audio it forwards:
//! - input is the PCM16 chunk listen hands the gate (its STT buffer flush,
//!   see [`SttBuffer`]); bytes of a sample split across chunks carry over;
//! - each chunk is resampled to 16 kHz on its own by linear interpolation
//!   (`np.linspace` + `np.interp`, truncated to int16), then scaled to f32;
//! - 512-sample windows run Silero; leftovers carry to the next chunk;
//! - a chunk is speech if any window's probability exceeds the threshold for
//!   the gate state at the start of the chunk (start in SILENCE, continue in
//!   SPEECH/HANGOVER);
//! - active mode runs SILENCE -> SPEECH -> HANGOVER -> SILENCE with a 300 ms
//!   pre-roll and the session's hangover; shadow mode only scores.
//!
//! The window lane scores a gained copy (`SessionPcmGain`, causal peak AGC
//! toward 0.8 of full scale, at most 4x); [`Variant::Agc`] reproduces it.
use std::collections::VecDeque;

use crate::silero::{self, VadError};

/// `VAD_GATE_SPEECH_THRESHOLD`.
pub const SPEECH_THRESHOLD: f64 = 0.65;
/// `VAD_GATE_HANGOVER_MS` (standard lanes).
pub const STANDARD_HANGOVER_MS: f64 = 4000.0;
/// `WINDOW_VAD_HANGOVER_MS` (parakeet window lane).
pub const WINDOW_HANGOVER_MS: f64 = 300.0;
/// `VAD_GATE_PRE_ROLL_MS`.
pub const PRE_ROLL_MS: f64 = 300.0;
/// `WINDOW_AGC_TARGET_PEAK`, `WINDOW_AGC_MAX_GAIN`, `_INT16_ABS_MAX`.
const AGC_TARGET_PEAK: f64 = 0.8;
const AGC_MAX_GAIN: f64 = 4.0;
const INT16_ABS_MAX: f64 = 32767.0;

/// listen's `stt_buffer_flush_size`: 30 ms of PCM16.
pub fn stt_flush_bytes(sample_rate: u32) -> usize {
    (sample_rate as f64 * 2.0 * 0.03) as usize
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Variant {
    /// Silero scores the chunk as received (standard lanes).
    Plain,
    /// Silero scores a `SessionPcmGain` copy (parakeet window lane).
    Agc,
}

impl Variant {
    pub const ALL: [Variant; 2] = [Variant::Plain, Variant::Agc];
    pub fn as_str(self) -> &'static str {
        match self {
            Variant::Plain => "plain",
            Variant::Agc => "agc",
        }
    }
    pub fn idx(self) -> usize {
        self as usize
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Mode {
    Active,
    Shadow,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct GateParams {
    pub variant: Variant,
    pub mode: Mode,
    pub speech_threshold: f64,
    pub continue_threshold: f64,
    pub hangover_ms: f64,
}

impl GateParams {
    /// The standard gate listen builds when `VAD_GATE_MODE=active`.
    pub fn standard() -> Self {
        GateParams {
            variant: Variant::Plain,
            mode: Mode::Active,
            speech_threshold: SPEECH_THRESHOLD,
            continue_threshold: SPEECH_THRESHOLD,
            hangover_ms: STANDARD_HANGOVER_MS,
        }
    }

    /// The parakeet window lane's gate (`build_gate(is_window=True)`).
    pub fn window() -> Self {
        GateParams {
            variant: Variant::Agc,
            hangover_ms: WINDOW_HANGOVER_MS,
            ..Self::standard()
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum GateState {
    Silence,
    Speech,
    Hangover,
}

/// A SILENCE -> SPEECH transition: the chunk that opened the gate and the
/// first capture sample of the pre-roll emitted with it.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Open {
    pub chunk_start: u64,
    pub preroll_start: u64,
}

/// What one chunk produced.
#[derive(Debug, Default)]
pub struct ChunkOut {
    /// Ordinal (since gate start) of the first window scored in this chunk.
    pub first_ordinal: u64,
    pub probs: Vec<f32>,
    /// Threshold the chunk's windows were judged against.
    pub threshold: f64,
    pub is_speech: bool,
    pub opened: Option<Open>,
}

/// Causal peak AGC (`SessionPcmGain` + `bounded_agc_pcm16`).
#[derive(Default)]
struct SessionGain {
    peak: f64,
}

fn pcm16_peak(pcm: &[u8]) -> f64 {
    pcm.as_chunks::<2>()
        .0
        .iter()
        .map(|b| (i16::from_le_bytes(*b) as i32).abs())
        .max()
        .unwrap_or(0) as f64
}

impl SessionGain {
    /// `None` when the copy equals the input (gain <= 1 or digital silence).
    fn apply(&mut self, pcm: &[u8]) -> Option<Vec<u8>> {
        let chunk_peak = if pcm.len() < 2 { 0.0 } else { pcm16_peak(pcm) };
        if chunk_peak > self.peak {
            self.peak = chunk_peak;
        }
        let peak = if self.peak > 0.0 { self.peak } else { chunk_peak };
        if peak <= 0.0 {
            return None;
        }
        let gain = AGC_MAX_GAIN.min((INT16_ABS_MAX * AGC_TARGET_PEAK) / peak);
        if gain <= 1.0 {
            return None;
        }
        // numpy: float32 samples * python float stays float32, clip, then a
        // truncating cast to int16.
        let g = gain as f32;
        let (samples, odd) = pcm.as_chunks::<2>();
        let mut out = Vec::with_capacity(pcm.len());
        for b in samples {
            let s = i16::from_le_bytes(*b) as f32;
            let v = (s * g).clamp(-32768.0, 32767.0) as i16;
            out.extend_from_slice(&v.to_le_bytes());
        }
        // `Gate` passes whole samples; a stray byte is passed through as is.
        out.extend_from_slice(odd);
        Some(out)
    }
}

/// `np.linspace(0, n - 1, n_out)` then `np.interp` over int16 samples,
/// truncated back to int16 (`VADStreamingGate._convert_for_vad`).
pub fn resample_linear(samples: &[i16], from_rate: u32, to_rate: u32) -> Vec<i16> {
    let n = samples.len();
    let ratio = to_rate as f64 / from_rate as f64;
    let n_out = (n as f64 * ratio) as usize;
    let mut out = Vec::with_capacity(n_out);
    if n_out == 0 || n == 0 {
        return out;
    }
    let stop = (n - 1) as f64;
    let step = if n_out > 1 { stop / (n_out - 1) as f64 } else { 0.0 };
    for i in 0..n_out {
        let x = if n_out > 1 && i == n_out - 1 {
            stop
        } else {
            i as f64 * step
        };
        out.push(interp(x, samples) as i16);
    }
    out
}

/// numpy's `interp` with `xp = arange(n)`, for `0 <= x <= n - 1`.
fn interp(x: f64, fp: &[i16]) -> f64 {
    let last = fp.len() - 1;
    if x >= last as f64 {
        return fp[last] as f64;
    }
    let j = x as usize;
    let (y0, y1) = (fp[j] as f64, fp[j + 1] as f64);
    // slope = (y1 - y0) / (xp[j + 1] - xp[j]), and that divisor is exactly 1.
    (y1 - y0) * (x - j as f64) + y0
}

pub struct Gate {
    sample_rate: u32,
    params: GateParams,
    pcm_remainder: Vec<u8>,
    vad_buffer: Vec<f32>,
    stream: silero::Stream,
    gain: Option<SessionGain>,
    /// Byte of a sample split across chunks, held ahead of the AGC copy.
    agc_carry: Vec<u8>,
    next_ordinal: u64,
    state: GateState,
    audio_cursor_ms: f64,
    last_speech_ms: f64,
    /// (capture start sample, chunk ms) of buffered pre-roll chunks.
    pre_roll: VecDeque<(u64, f64)>,
    pre_roll_total_ms: f64,
}

impl Gate {
    pub fn new(sample_rate: u32, params: GateParams) -> Gate {
        Gate {
            sample_rate,
            params,
            pcm_remainder: Vec::new(),
            vad_buffer: Vec::new(),
            stream: silero::Stream::new(),
            gain: (params.variant == Variant::Agc).then(SessionGain::default),
            agc_carry: Vec::new(),
            next_ordinal: 0,
            state: GateState::Silence,
            audio_cursor_ms: 0.0,
            last_speech_ms: 0.0,
            pre_roll: VecDeque::new(),
            pre_roll_total_ms: 0.0,
        }
    }

    pub fn params(&self) -> GateParams {
        self.params
    }

    pub fn state(&self) -> GateState {
        self.state
    }

    pub fn windows_scored(&self) -> u64 {
        self.next_ordinal
    }

    fn threshold(&self) -> f64 {
        let cont = self.params.continue_threshold.min(self.params.speech_threshold);
        match self.state {
            GateState::Speech | GateState::Hangover => cont,
            GateState::Silence => self.params.speech_threshold,
        }
    }

    /// Feed one chunk (`process_audio`); `start_sample` is the capture
    /// position of its first sample.
    pub fn process_chunk(&mut self, pcm: &[u8], start_sample: u64) -> Result<ChunkOut, VadError> {
        let n_samples = pcm.len() / 2;
        let chunk_ms = (n_samples as f64 * 1000.0) / self.sample_rate as f64;
        self.audio_cursor_ms += chunk_ms;

        let mut out = if self.gain.is_none() {
            self.run_vad(pcm)?
        } else {
            // listen's window leg ends on an odd-length chunk (numpy cannot
            // view it as int16). Here a split sample is carried ahead of
            // gaining, so Silero always scores whole samples.
            let mut whole = std::mem::take(&mut self.agc_carry);
            whole.extend_from_slice(pcm);
            if whole.len() % 2 == 1 {
                self.agc_carry.push(whole.pop().expect("odd length is non-empty"));
            }
            let gained = self.gain.as_mut().and_then(|g| g.apply(&whole));
            self.run_vad(&gained.unwrap_or(whole))?
        };
        if out.is_speech {
            self.last_speech_ms = self.audio_cursor_ms;
        }
        if self.params.mode == Mode::Active {
            out.opened = self.update_state(pcm.len(), out.is_speech, start_sample);
        }
        Ok(out)
    }

    fn run_vad(&mut self, pcm: &[u8]) -> Result<ChunkOut, VadError> {
        let mut data = std::mem::take(&mut self.pcm_remainder);
        data.extend_from_slice(pcm);
        let leftover = data.len() % 2;
        if leftover != 0 {
            self.pcm_remainder = data.split_off(data.len() - leftover);
        }
        let mut samples: Vec<i16> = data.as_chunks::<2>().0.iter().map(|b| i16::from_le_bytes(*b)).collect();
        if self.sample_rate != silero::SAMPLE_RATE as u32 && !samples.is_empty() {
            samples = resample_linear(&samples, self.sample_rate, silero::SAMPLE_RATE as u32);
        }
        self.vad_buffer.extend(samples.iter().map(|&s| s as f32 / 32768.0));

        let threshold = self.threshold();
        let mut out = ChunkOut {
            first_ordinal: self.next_ordinal,
            threshold,
            ..Default::default()
        };
        let mut consumed = 0;
        while self.vad_buffer.len() - consumed >= silero::WINDOW {
            let window = &self.vad_buffer[consumed..consumed + silero::WINDOW];
            let prob = self.stream.run(window)?;
            consumed += silero::WINDOW;
            self.next_ordinal += 1;
            // Python compares the float32 probability as a double.
            if prob as f64 > threshold {
                out.is_speech = true;
            }
            out.probs.push(prob);
        }
        self.vad_buffer.drain(..consumed);
        Ok(out)
    }

    /// `_update_state`, decisions only. Returns the open, if any.
    fn update_state(&mut self, chunk_bytes: usize, is_speech: bool, start_sample: u64) -> Option<Open> {
        let chunk_ms = (chunk_bytes as f64 / (2.0 * self.sample_rate as f64)) * 1000.0;
        match self.state {
            GateState::Silence => {
                self.pre_roll.push_back((start_sample, chunk_ms));
                self.pre_roll_total_ms += chunk_ms;
                while self.pre_roll_total_ms > PRE_ROLL_MS && self.pre_roll.len() > 1 {
                    let (_, evicted_ms) = self.pre_roll.pop_front().expect("len > 1");
                    self.pre_roll_total_ms -= evicted_ms;
                }
                if !is_speech {
                    return None;
                }
                self.state = GateState::Speech;
                let preroll_start = self.pre_roll.front().map(|(s, _)| *s).unwrap_or(start_sample);
                self.pre_roll.clear();
                self.pre_roll_total_ms = 0.0;
                Some(Open {
                    chunk_start: start_sample,
                    preroll_start,
                })
            }
            GateState::Speech => {
                if !is_speech {
                    self.state = GateState::Hangover;
                }
                None
            }
            GateState::Hangover => {
                if is_speech {
                    self.state = GateState::Speech;
                } else if self.audio_cursor_ms - self.last_speech_ms > self.params.hangover_ms {
                    self.state = GateState::Silence;
                    self.pre_roll.clear();
                    self.pre_roll.push_back((start_sample, chunk_ms));
                    self.pre_roll_total_ms = chunk_ms;
                }
                None
            }
        }
    }
}

/// listen's STT buffer in front of the gate: decoded frames accumulate and
/// the whole buffer is handed over once it holds at least 30 ms
/// (`decide_stt_buffer_flush`).
pub struct SttBuffer {
    flush_bytes: usize,
    buf: Vec<u8>,
    start: Option<u64>,
}

impl SttBuffer {
    pub fn new(sample_rate: u32) -> SttBuffer {
        SttBuffer {
            flush_bytes: stt_flush_bytes(sample_rate),
            buf: Vec::new(),
            start: None,
        }
    }

    /// Append a decoded frame; returns a chunk and its start when it flushes.
    pub fn push(&mut self, pcm: &[u8], start_sample: u64) -> Option<(Vec<u8>, u64)> {
        if pcm.is_empty() {
            return None;
        }
        if self.buf.is_empty() {
            self.start = Some(start_sample);
        }
        self.buf.extend_from_slice(pcm);
        if self.buf.len() < self.flush_bytes {
            return None;
        }
        let start = self.start.take().unwrap_or(start_sample);
        Some((std::mem::take(&mut self.buf), start))
    }

    /// The partial tail listen force-flushes at session end.
    pub fn take_rest(&mut self) -> Option<(Vec<u8>, u64)> {
        let start = self.start.take()?;
        (!self.buf.is_empty()).then(|| (std::mem::take(&mut self.buf), start))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn flush_size_matches_listen() {
        assert_eq!(stt_flush_bytes(16000), 960);
        assert_eq!(stt_flush_bytes(8000), 480);
        assert_eq!(stt_flush_bytes(48000), 2880);
        assert_eq!(stt_flush_bytes(11025), 661);
    }

    #[test]
    fn stt_buffer_flushes_whole_buffer_at_30ms() {
        let mut b = SttBuffer::new(16000);
        assert!(b.push(&[0; 640], 0).is_none());
        let (chunk, start) = b.push(&[0; 640], 320).unwrap();
        assert_eq!((chunk.len(), start), (1280, 0));
        assert!(b.push(&[], 640).is_none());
        assert!(b.push(&[0; 640], 640).is_none());
    }

    #[test]
    fn resample_matches_numpy_linspace_interp() {
        // np.interp(np.linspace(0, 3, 8), np.arange(4), [0, 100, -100, 7]).astype(np.int16)
        // == [0, 42, 85, 42, -42, -84, -38, 7]
        assert_eq!(
            resample_linear(&[0, 100, -100, 7], 8000, 16000),
            vec![0, 42, 85, 42, -42, -84, -38, 7]
        );
        // n_out == 1 -> linspace gives [0.0].
        assert_eq!(resample_linear(&[5, 9, 11], 48000, 16000), vec![5]);
        assert!(resample_linear(&[5], 48000, 16000).is_empty());
    }

    #[test]
    fn agc_gate_carries_a_split_sample_before_gaining() {
        // Three samples of 1000 split 3 + 3 bytes: the gained copy must stay
        // sample-aligned (4000 each), not byte-rotated. No window runs yet.
        let mut gate = Gate::new(16000, GateParams::window());
        let pcm: Vec<u8> = [1000i16; 3].iter().flat_map(|s| s.to_le_bytes()).collect();
        gate.process_chunk(&pcm[..3], 0).unwrap();
        gate.process_chunk(&pcm[3..], 1).unwrap();
        assert!(gate.agc_carry.is_empty() && gate.pcm_remainder.is_empty());
        assert_eq!(gate.vad_buffer, vec![4000.0 / 32768.0; 3]);
    }

    #[test]
    fn agc_matches_bounded_agc_pcm16() {
        // Session peak 1000 -> gain min(4, 32767*0.8/1000) = 4.
        let mut g = SessionGain::default();
        let pcm: Vec<u8> = [1000i16, -500, 3].iter().flat_map(|s| s.to_le_bytes()).collect();
        let out = g.apply(&pcm).unwrap();
        let got: Vec<i16> = out.as_chunks::<2>().0.iter().map(|b| i16::from_le_bytes(*b)).collect();
        assert_eq!(got, vec![4000, -2000, 12]);
        // Loud chunk raises the running peak; gain then falls to <= 1: unchanged.
        let loud: Vec<u8> = [30000i16].iter().flat_map(|s| s.to_le_bytes()).collect();
        assert!(g.apply(&loud).is_none());
        // Digital silence is unchanged.
        assert!(SessionGain::default().apply(&[0, 0, 0, 0]).is_none());
        // An odd trailing byte is carried through ungained.
        let odd = SessionGain::default().apply(&[0xe8, 0x03, 0x7f]).unwrap();
        assert_eq!(odd, vec![0xa0, 0x0f, 0x7f]); // 1000 * 4 = 0x0fa0
    }
}
