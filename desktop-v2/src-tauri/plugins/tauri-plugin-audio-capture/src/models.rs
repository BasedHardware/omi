use serde::{Deserialize, Serialize};

/// Represents an audio device discovered on the system.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AudioDevice {
    /// Opaque identifier for the device (cpal device name).
    pub id: String,
    /// Human-readable name.
    pub name: String,
    /// Whether this is the system default input device.
    pub is_default: bool,
    /// Always `true` for the devices we enumerate (input only).
    pub is_input: bool,
}

/// VAD sensitivity preset. Serialized lowercase (`off`, `sensitive`, …) to
/// match the TS `VadMode` type.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum VadMode {
    Off,
    Sensitive,
    Balanced,
    Aggressive,
}

impl Default for VadMode {
    fn default() -> Self {
        VadMode::Off
    }
}

/// High-level capture mode. Kept as a plain string on the wire to mirror
/// `CaptureMode` in TS without committing to an exhaustive enum yet.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum CaptureMode {
    Conversation,
    Ptt,
}

impl Default for CaptureMode {
    fn default() -> Self {
        CaptureMode::Conversation
    }
}

fn default_sample_rate() -> u32 {
    16000
}

fn default_channels() -> u16 {
    1
}

fn default_language() -> String {
    "en".to_string()
}

/// Configuration for starting a capture session.
///
/// Every field is `#[serde(default)]` so a minimal JSON payload (or an
/// extended one with future fields) deserializes cleanly — protects the
/// plugin from TS-side schema drift.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct CaptureConfig {
    /// Target sample rate in Hz (default: 16000).
    #[serde(default = "default_sample_rate")]
    pub sample_rate: u32,
    /// Number of output channels (default: 1 — mono).
    #[serde(default = "default_channels")]
    pub channels: u16,
    /// If `None`, the system default input device is used.
    #[serde(default)]
    pub device_id: Option<String>,
    /// Transcription language hint (BCP-47 or Deepgram language code).
    #[serde(default = "default_language")]
    pub language: String,
    /// High-level capture mode. Kept for parity with TS; currently advisory.
    #[serde(default)]
    pub mode: CaptureMode,
    /// Whether to also capture system audio alongside the mic.
    #[serde(default)]
    pub capture_system_audio: bool,
    /// VAD sensitivity preset.
    #[serde(default)]
    pub vad_mode: VadMode,
    /// When true, skip the live Deepgram WebSocket entirely — only record
    /// audio to disk and upload to /v1/conversations/from-audio on stop.
    /// Default false preserves the existing live-streaming behavior.
    #[serde(default)]
    pub skip_live_transcription: bool,
    /// When true, record mic-only to a WAV file and skip all
    /// ScreenCaptureKit / system-audio / Deepgram / transcription plumbing.
    /// Intended for the Companion PTT flow where `stop_recording` must return
    /// the WAV path synchronously so the caller can send it to Gemini as
    /// `inline_data`.  Default false preserves the existing meeting-capture
    /// behaviour and is backward-compatible with all existing callers.
    ///
    /// WAV format: PCM 16-bit LE, 16 kHz, 1 channel (mono).
    /// Written to: `<app_data_dir>/companion/recordings/<uuid>.wav`.
    /// The frontend is responsible for deleting the file after use.
    #[serde(default)]
    pub mic_only: bool,
}

impl Default for CaptureConfig {
    fn default() -> Self {
        Self {
            sample_rate: default_sample_rate(),
            channels: default_channels(),
            device_id: None,
            language: default_language(),
            mode: CaptureMode::default(),
            capture_system_audio: false,
            vad_mode: VadMode::default(),
            skip_live_transcription: false,
            mic_only: false,
        }
    }
}

/// Metadata returned by `stop_recording` when the session was started with
/// `mic_only: true`.  All the fields needed by the Companion Gemini call are
/// present so the caller never needs a second IPC round-trip.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CompanionRecording {
    /// Absolute path to the finalized WAV file.
    /// Format: PCM 16-bit LE, 16 kHz, 1 channel (mono).
    pub wav_path: String,
    /// Recording duration in milliseconds (derived from PCM byte count).
    pub duration_ms: u64,
    /// Sample rate of the WAV (always 16 000 for Gemini compatibility).
    pub sample_rate: u32,
    /// Number of channels (always 1 — mono).
    pub channels: u16,
}

/// Instantaneous audio level computed from a sample buffer.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AudioLevel {
    /// Root-mean-square amplitude (0.0 – 1.0 range, normalised to i16::MAX).
    pub rms: f32,
    /// Peak absolute amplitude (0.0 – 1.0 range).
    pub peak: f32,
}

/// Snapshot of the current capture state.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CaptureState {
    pub is_capturing: bool,
    pub device_name: Option<String>,
    pub sample_rate: u32,
    /// Whether system-audio capture is also active alongside the mic.
    #[serde(default)]
    pub system_audio_active: bool,
    /// Total mic samples delivered to the mixer since start.
    #[serde(default)]
    pub mic_samples_total: u64,
    /// Total system-audio samples delivered to the mixer since start.
    /// Stays at 0 if the tap is active but nothing is playing.
    #[serde(default)]
    pub sys_samples_total: u64,
}

impl Default for CaptureState {
    fn default() -> Self {
        Self {
            is_capturing: false,
            device_name: None,
            sample_rate: 16000,
            system_audio_active: false,
            mic_samples_total: 0,
            sys_samples_total: 0,
        }
    }
}
