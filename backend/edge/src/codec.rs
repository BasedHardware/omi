//! Client audio decode for the shadow path, matching listen's receive loop
//! (`backend/routers/listen/receiver.py`, `receive_data`):
//! - `opus` and `opus_fs320` share one libopus decoder at the session rate
//!   (packets are self-describing; the output capacity is 120 ms);
//! - `pcm16` passes through unchanged (little-endian, possibly odd length);
//! - `pcm8` is unsigned 8-bit lifted to 16-bit (`audioop.bias(data, 1, -128)`
//!   then `audioop.lin2lin(.., 1, 2)`).
//!
//! Not yet implemented: `lc3` / `lc3_fs1030` and `aac` (listen mirrors only
//! the codecs above).

/// Rates listen accepts for any codec (`SUPPORTED_SAMPLE_RATES`).
pub const SUPPORTED_SAMPLE_RATES: [u32; 9] = [8000, 11025, 12000, 16000, 22050, 24000, 32000, 44100, 48000];
/// Rates libopus decodes at (`OPUS_SUPPORTED_SAMPLE_RATES`).
pub const OPUS_SAMPLE_RATES: [u32; 5] = [8000, 12000, 16000, 24000, 48000];
/// listen's `OPUS_MAX_FRAME_MS`: decode output capacity.
const OPUS_MAX_FRAME_MS: usize = 120;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Codec {
    Opus,
    Pcm8,
    Pcm16,
}

impl Codec {
    pub const ALL: [Codec; 3] = [Codec::Opus, Codec::Pcm8, Codec::Pcm16];

    /// The client's `codec` query value; `opus_fs320` normalizes to opus as
    /// in `normalize_codec_frame`.
    pub fn parse(raw: &str) -> Option<Codec> {
        match raw {
            "opus" | "opus_fs320" => Some(Codec::Opus),
            "pcm8" => Some(Codec::Pcm8),
            "pcm16" => Some(Codec::Pcm16),
            _ => None,
        }
    }

    pub fn as_str(self) -> &'static str {
        match self {
            Codec::Opus => "opus",
            Codec::Pcm8 => "pcm8",
            Codec::Pcm16 => "pcm16",
        }
    }

    pub fn idx(self) -> usize {
        self as usize
    }

    pub fn supports_rate(self, rate: u32) -> bool {
        match self {
            Codec::Opus => OPUS_SAMPLE_RATES.contains(&rate),
            Codec::Pcm8 | Codec::Pcm16 => SUPPORTED_SAMPLE_RATES.contains(&rate),
        }
    }
}

pub enum Decoder {
    Opus { dec: opus::Decoder, out: Vec<i16> },
    Pcm8,
    Pcm16,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DecodeError(pub String);

impl Decoder {
    pub fn new(codec: Codec, sample_rate: u32) -> Result<Decoder, DecodeError> {
        if !codec.supports_rate(sample_rate) {
            return Err(DecodeError(format!("{} at {sample_rate} Hz", codec.as_str())));
        }
        Ok(match codec {
            Codec::Opus => Decoder::Opus {
                dec: opus::Decoder::new(sample_rate, opus::Channels::Mono).map_err(|e| DecodeError(e.to_string()))?,
                out: vec![0; sample_rate as usize / 1000 * OPUS_MAX_FRAME_MS],
            },
            Codec::Pcm8 => Decoder::Pcm8,
            Codec::Pcm16 => Decoder::Pcm16,
        })
    }

    /// Decode one client frame, appending PCM16 little-endian bytes to `pcm`.
    pub fn decode(&mut self, frame: &[u8], pcm: &mut Vec<u8>) -> Result<(), DecodeError> {
        match self {
            Decoder::Opus { dec, out } => {
                let n = dec.decode(frame, out, false).map_err(|e| DecodeError(e.to_string()))?;
                pcm.reserve(n * 2);
                for s in &out[..n] {
                    pcm.extend_from_slice(&s.to_le_bytes());
                }
            }
            Decoder::Pcm8 => {
                pcm.reserve(frame.len() * 2);
                for &b in frame {
                    // bias(-128) wraps mod 256 and reads the byte as signed;
                    // lin2lin(1, 2) shifts it into the high byte.
                    let s = ((b ^ 0x80) as i8 as i16) << 8;
                    pcm.extend_from_slice(&s.to_le_bytes());
                }
            }
            Decoder::Pcm16 => pcm.extend_from_slice(frame),
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn codec_names_match_listen() {
        assert_eq!(Codec::parse("opus_fs320"), Some(Codec::Opus));
        assert_eq!(Codec::parse("opus"), Some(Codec::Opus));
        assert_eq!(Codec::parse("pcm8"), Some(Codec::Pcm8));
        assert_eq!(Codec::parse("pcm16"), Some(Codec::Pcm16));
        for later in ["lc3", "lc3_fs1030", "aac", ""] {
            assert_eq!(Codec::parse(later), None);
        }
        assert!(!Codec::Opus.supports_rate(44100));
        assert!(Codec::Pcm16.supports_rate(44100));
        assert!(Decoder::new(Codec::Opus, 11025).is_err());
    }

    #[test]
    fn pcm8_matches_audioop_bias_then_lin2lin() {
        // audioop.lin2lin(audioop.bias(bytes([0, 1, 127, 128, 129, 255]), 1, -128), 1, 2)
        // == b'\x00\x80\x00\x81\x00\xff\x00\x00\x00\x01\x00\x7f'
        let mut out = Vec::new();
        Decoder::Pcm8.decode(&[0, 1, 127, 128, 129, 255], &mut out).unwrap();
        assert_eq!(
            out,
            vec![0x00, 0x80, 0x00, 0x81, 0x00, 0xff, 0x00, 0x00, 0x00, 0x01, 0x00, 0x7f]
        );
    }

    #[test]
    fn opus_round_trip_decodes_a_frame() {
        let mut enc = opus::Encoder::new(16000, opus::Channels::Mono, opus::Application::Voip).unwrap();
        let pcm: Vec<i16> = (0..320).map(|i| ((i as f32 * 0.2).sin() * 8000.0) as i16).collect();
        let packet = enc.encode_vec(&pcm, 4000).unwrap();
        let mut dec = Decoder::new(Codec::Opus, 16000).unwrap();
        let mut out = Vec::new();
        dec.decode(&packet, &mut out).unwrap();
        assert_eq!(out.len(), 640);
        assert!(dec.decode(&[0xff, 0xff, 0xff], &mut out).is_err() || out.len() > 640);
    }
}
