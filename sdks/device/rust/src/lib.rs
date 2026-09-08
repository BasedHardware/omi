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
/// Decode buffer bound for `opus_decode`, not the wire frame size (160 or 320 samples).
pub const OPUS_FRAME_SAMPLES: usize = 960;
pub const PCM_CHANNELS: u8 = 1;

/// First byte of the audio codec characteristic. See `sdks/device/PROTOCOL.md`.
pub const CODEC_PCM16: u8 = 0;
pub const CODEC_PCM8: u8 = 1;
/// 160-sample frames @ 100 fps (DevKit firmware).
pub const CODEC_OPUS: u8 = 20;
/// 320-sample frames @ 50 fps (Omi CV1 firmware).
pub const CODEC_OPUS_FS320: u8 = 21;

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

        /// Buffer PCM16 LE mono audio at 16 kHz, transcribing the entire buffer
        /// once it contains at least five seconds of audio. Call [`Self::flush`]
        /// at the end of the stream to transcribe any shorter final batch.
        pub fn append_pcm(&mut self, pcm: &[u8]) -> Result<Option<String>, String> {
            self.buf.extend_from_slice(pcm);
            if self.buf.len() < self.batch {
                return Ok(None);
            }
            self.flush()
        }

        /// Transcribe all buffered audio, regardless of the batch threshold.
        ///
        /// An empty buffer returns `Ok(None)` without calling the runner.
        /// Success clears the buffer, even when the transcript is empty. An
        /// error retains all audio for an explicit retry with `flush()`; do not
        /// append the same audio again. More audio may be appended after flushing.
        pub fn flush(&mut self) -> Result<Option<String>, String> {
            if self.buf.is_empty() {
                return Ok(None);
            }
            let text = (self.runner)(&self.buf)?;
            self.buf.clear();
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

    // Codec IDs are firmware-coupled: 20 is DevKit, 21 is Omi CV1 (opusFS320).
    #[test]
    fn codec_ids() {
        assert_eq!(CODEC_PCM16, 0);
        assert_eq!(CODEC_PCM8, 1);
        assert_eq!(CODEC_OPUS, 20);
        assert_eq!(CODEC_OPUS_FS320, 21);
    }

    #[test]
    fn parakeet_url() {
        assert_eq!(
            parakeet_ws_url("https://parakeet.example/", 16000),
            "wss://parakeet.example/v3/stream?sample_rate=16000"
        );
    }

    #[cfg(feature = "stt-whisper")]
    mod whisper_tests {
        use super::super::whisper::WhisperTranscriber;
        use std::cell::{Cell, RefCell};

        #[test]
        fn failed_batch_is_retained_for_explicit_append_retry() {
            let pcm: Vec<u8> = (0..160_000).map(|i| (i % 256) as u8).collect();
            let calls = Cell::new(0);
            let mut transcriber = WhisperTranscriber::new(|chunk: &[u8]| {
                assert_eq!(chunk, pcm.as_slice());
                calls.set(calls.get() + 1);
                if calls.get() == 1 {
                    Err("runner failed".to_string())
                } else {
                    Ok("retried batch".to_string())
                }
            });

            assert_eq!(
                transcriber.append_pcm(&pcm),
                Err("runner failed".to_string())
            );
            assert_eq!(calls.get(), 1);
            assert_eq!(
                transcriber.append_pcm(&[]),
                Ok(Some("retried batch".to_string()))
            );
            assert_eq!(calls.get(), 2);
        }

        #[test]
        fn empty_flush_does_not_call_runner() {
            let mut transcriber = WhisperTranscriber::new(|_: &[u8]| {
                panic!("empty buffers must not reach the runner")
            });

            assert_eq!(transcriber.flush(), Ok(None));
            assert_eq!(transcriber.flush(), Ok(None));
        }

        #[test]
        fn final_tail_is_flushed_once_and_more_audio_can_be_appended() {
            let chunks = RefCell::new(Vec::new());
            let mut transcriber = WhisperTranscriber::new(|chunk: &[u8]| {
                chunks.borrow_mut().push(chunk.to_vec());
                Ok("tail".to_string())
            });

            assert_eq!(transcriber.append_pcm(&[1, 2, 3, 4]), Ok(None));
            assert!(chunks.borrow().is_empty());
            assert_eq!(transcriber.flush(), Ok(Some("tail".to_string())));
            assert_eq!(transcriber.flush(), Ok(None));
            assert_eq!(*chunks.borrow(), vec![vec![1, 2, 3, 4]]);

            assert_eq!(transcriber.append_pcm(&[5, 6]), Ok(None));
            assert_eq!(chunks.borrow().len(), 1);
            assert_eq!(transcriber.flush(), Ok(Some("tail".to_string())));
            assert_eq!(*chunks.borrow(), vec![vec![1, 2, 3, 4], vec![5, 6]]);
        }

        #[test]
        fn successful_empty_transcript_clears_buffer() {
            let calls = Cell::new(0);
            let mut transcriber = WhisperTranscriber::new(|chunk: &[u8]| {
                assert_eq!(chunk, &[1, 2]);
                calls.set(calls.get() + 1);
                Ok(String::new())
            });

            assert_eq!(transcriber.append_pcm(&[1, 2]), Ok(None));
            assert_eq!(transcriber.flush(), Ok(None));
            assert_eq!(calls.get(), 1);
            assert_eq!(transcriber.flush(), Ok(None));
            assert_eq!(calls.get(), 1);
        }

        #[test]
        fn full_batch_and_final_tail_are_transcribed_separately() {
            let pcm = vec![7; 160_000];
            let chunks = RefCell::new(Vec::new());
            let mut transcriber = WhisperTranscriber::new(|chunk: &[u8]| {
                chunks.borrow_mut().push(chunk.to_vec());
                Ok("transcript".to_string())
            });

            assert_eq!(transcriber.append_pcm(&pcm[..159_998]), Ok(None));
            assert!(chunks.borrow().is_empty());
            assert_eq!(
                transcriber.append_pcm(&pcm[159_998..]),
                Ok(Some("transcript".to_string()))
            );
            assert_eq!(transcriber.append_pcm(&[8, 9]), Ok(None));
            assert_eq!(chunks.borrow().len(), 1);
            assert_eq!(transcriber.flush(), Ok(Some("transcript".to_string())));
            assert_eq!(*chunks.borrow(), vec![pcm, vec![8, 9]]);
        }

        #[test]
        fn failed_partial_or_full_buffer_is_retained_for_explicit_flush_retry() {
            for length in [4, 160_000] {
                let pcm: Vec<u8> = (0..length).map(|i| (i % 256) as u8).collect();
                let calls = Cell::new(0);
                let mut transcriber = WhisperTranscriber::new(|chunk: &[u8]| {
                    assert_eq!(chunk, pcm.as_slice());
                    calls.set(calls.get() + 1);
                    if calls.get() == 1 {
                        Err("runner failed".to_string())
                    } else {
                        Ok("retried buffer".to_string())
                    }
                });

                if length < 160_000 {
                    assert_eq!(transcriber.append_pcm(&pcm), Ok(None));
                    assert_eq!(calls.get(), 0);
                    assert_eq!(transcriber.flush(), Err("runner failed".to_string()));
                } else {
                    assert_eq!(
                        transcriber.append_pcm(&pcm),
                        Err("runner failed".to_string())
                    );
                }
                assert_eq!(calls.get(), 1);
                assert_eq!(transcriber.flush(), Ok(Some("retried buffer".to_string())));
                assert_eq!(calls.get(), 2);
                assert_eq!(transcriber.flush(), Ok(None));
                assert_eq!(calls.get(), 2);
            }
        }

        #[test]
        fn oversized_append_transcribes_entire_buffer_in_one_call() {
            let pcm: Vec<u8> = (0..160_004).map(|i| (i % 256) as u8).collect();
            let calls = Cell::new(0);
            let mut transcriber = WhisperTranscriber::new(|chunk: &[u8]| {
                assert_eq!(chunk, pcm.as_slice());
                calls.set(calls.get() + 1);
                Ok("oversized batch".to_string())
            });

            assert_eq!(
                transcriber.append_pcm(&pcm),
                Ok(Some("oversized batch".to_string()))
            );
            assert_eq!(calls.get(), 1);
            assert_eq!(transcriber.flush(), Ok(None));
            assert_eq!(calls.get(), 1);
        }
    }
}
