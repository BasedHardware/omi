pub mod mic;
pub mod loopback;
pub mod mixer;
pub mod vad;

use tokio::sync::broadcast;

/// Audio sample format used throughout the pipeline: mono 16kHz i16 PCM.
pub const SAMPLE_RATE: u32 = 16_000;
pub const CHANNELS: u16 = 1;

/// A chunk of raw PCM audio (mono 16kHz i16).
#[derive(Debug, Clone)]
pub struct AudioChunk {
    pub samples: Vec<i16>,
    pub sample_rate: u32,
}

/// Create a broadcast channel for streaming audio chunks.
pub fn audio_channel(capacity: usize) -> (broadcast::Sender<AudioChunk>, broadcast::Receiver<AudioChunk>) {
    broadcast::channel(capacity)
}
