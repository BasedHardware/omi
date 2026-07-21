//! Omi device BLE protocol helpers + optional STT.
//! See `sdks/device/PROTOCOL.md` and `sdks/device/STT.md`.
//!
//! Enable feature `ble` for `btleplug`-backed [`ble`] scan/listen.

#[cfg(feature = "ble")]
pub mod ble;

pub const SERVICE_UUID: &str = "19b10000-e8f2-537e-4f6c-d104768a1214";
pub const AUDIO_DATA_UUID: &str = "19b10001-e8f2-537e-4f6c-d104768a1214";
pub const AUDIO_CODEC_UUID: &str = "19b10002-e8f2-537e-4f6c-d104768a1214";
pub const BATTERY_SERVICE_UUID: &str = "0000180f-0000-1000-8000-00805f9b34fb";
pub const BATTERY_LEVEL_UUID: &str = "00002a19-0000-1000-8000-00805f9b34fb";

pub const PACKET_HEADER_BYTES: usize = 3;
pub const PCM_SAMPLE_RATE_HZ: u32 = 16_000;
pub const OPUS_FRAME_SAMPLES: usize = 960;
pub const PCM_CHANNELS: u8 = 1;

/// Strip the 3-byte Omi audio packet header.
pub fn strip_packet_header(packet: &[u8]) -> &[u8] {
    if packet.len() <= PACKET_HEADER_BYTES {
        &[]
    } else {
        &packet[PACKET_HEADER_BYTES..]
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SttEngine {
    Deepgram,
    Whisper,
    Parakeet,
}

impl SttEngine {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Deepgram => "deepgram",
            Self::Whisper => "whisper",
            Self::Parakeet => "parakeet",
        }
    }
}

pub fn parakeet_ws_url(api_url: &str, sample_rate: u32) -> String {
    let mut base = api_url.trim().trim_end_matches('/').to_string();
    if let Some(rest) = base.strip_prefix("https://") {
        base = format!("wss://{rest}");
    } else if let Some(rest) = base.strip_prefix("http://") {
        base = format!("ws://{rest}");
    }
    format!("{base}/v3/stream?sample_rate={sample_rate}")
}

#[cfg(feature = "stt-whisper")]
pub mod whisper {
    /// Feature-gated Whisper: inject a runner (candle/whisper-rs/etc).
    pub struct WhisperTranscriber<F>
    where
        F: Fn(&[u8]) -> Result<String, String>,
    {
        pub runner: F,
        buf: Vec<u8>,
        batch: usize,
    }

    impl<F> WhisperTranscriber<F>
    where
        F: Fn(&[u8]) -> Result<String, String>,
    {
        pub fn new(runner: F) -> Self {
            Self {
                runner,
                buf: Vec::new(),
                batch: 16000 * 2 * 5,
            }
        }

        pub fn append_pcm(&mut self, pcm: &[u8]) -> Result<Option<String>, String> {
            self.buf.extend_from_slice(pcm);
            if self.buf.len() < self.batch {
                return Ok(None);
            }
            let chunk = std::mem::take(&mut self.buf);
            let text = (self.runner)(&chunk)?;
            Ok(if text.is_empty() { None } else { Some(text) })
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn strips_header() {
        assert!(strip_packet_header(&[1, 2]).is_empty());
        assert_eq!(strip_packet_header(&[0, 0, 0, 9, 8]), &[9, 8]);
    }

    #[test]
    fn parakeet_url() {
        assert_eq!(
            parakeet_ws_url("https://parakeet.example/", 16000),
            "wss://parakeet.example/v3/stream?sample_rate=16000"
        );
    }
}
