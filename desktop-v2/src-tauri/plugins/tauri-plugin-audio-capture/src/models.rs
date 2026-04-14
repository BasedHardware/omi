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

/// Configuration for starting a capture session.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CaptureConfig {
    /// Target sample rate in Hz (default: 16000).
    pub sample_rate: u32,
    /// Number of output channels (default: 1 — mono).
    pub channels: u16,
    /// If `None`, the system default input device is used.
    pub device_id: Option<String>,
}

impl Default for CaptureConfig {
    fn default() -> Self {
        Self {
            sample_rate: 16000,
            channels: 1,
            device_id: None,
        }
    }
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
}

impl Default for CaptureState {
    fn default() -> Self {
        Self {
            is_capturing: false,
            device_name: None,
            sample_rate: 16000,
        }
    }
}
