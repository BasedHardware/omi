//! Durable on-disk WAV recording of mixed stereo PCM.
//!
//! Writes a canonical 44-byte RIFF/WAVE header with placeholder size fields,
//! appends raw 16 kHz / 2ch / 16-bit PCM LE frames as they arrive from the
//! mixer, and patches the two size fields on `finalize`. Wrapped in a
//! `BufWriter` so per-chunk appends don't hit the disk every 100 ms.
//!
//! Channel layout matches `mixer.rs`: left = mic, right = system audio.

use std::fs::{create_dir_all, OpenOptions};
use std::io::{BufWriter, Seek, SeekFrom, Write};
use std::path::Path;

const SAMPLE_RATE: u32 = 16_000;
const CHANNELS: u16 = 2;
const BITS_PER_SAMPLE: u16 = 16;
const BYTE_RATE: u32 = SAMPLE_RATE * CHANNELS as u32 * BITS_PER_SAMPLE as u32 / 8;
const BLOCK_ALIGN: u16 = CHANNELS * BITS_PER_SAMPLE / 8;
const HEADER_SIZE: u32 = 44;

// Mono constants for the Companion single-shot recorder.
const MONO_CHANNELS: u16 = 1;
const MONO_BYTE_RATE: u32 = SAMPLE_RATE * MONO_CHANNELS as u32 * BITS_PER_SAMPLE as u32 / 8;
const MONO_BLOCK_ALIGN: u16 = MONO_CHANNELS * BITS_PER_SAMPLE / 8;

/// Append-only WAV file writer. Call `create`, `append_stereo_bytes` zero or
/// more times, then `finalize` to patch the header and close the file.
pub struct AudioFileWriter {
    writer: BufWriter<std::fs::File>,
    data_size: u64,
    path: String,
}

impl AudioFileWriter {
    /// Open the file, write a placeholder WAV header, and prepare for appends.
    /// Creates the parent directory if missing.
    /// Format is fixed: 16 kHz, 2 channels (mic = left, sys = right), 16-bit PCM LE.
    pub fn create(path: &Path) -> Result<Self, String> {
        let path_str = path.display().to_string();

        if let Some(parent) = path.parent() {
            if !parent.as_os_str().is_empty() {
                create_dir_all(parent)
                    .map_err(|e| format!("audio_recorder: mkdir {}: {}", parent.display(), e))?;
            }
        }

        let file = OpenOptions::new()
            .read(true)
            .write(true)
            .create(true)
            .truncate(true)
            .open(path)
            .map_err(|e| format!("audio_recorder: open {}: {}", path_str, e))?;

        let mut writer = BufWriter::new(file);
        write_placeholder_header(&mut writer)
            .map_err(|e| format!("audio_recorder: write header {}: {}", path_str, e))?;

        Ok(Self {
            writer,
            data_size: 0,
            path: path_str,
        })
    }

    /// Append stereo PCM bytes. One frame = 4 bytes (2 channels × i16 LE).
    /// `bytes.len() % 4 == 0` is a caller invariant (this is what the existing
    /// AudioMixer emits — see mixer.rs).
    pub fn append_stereo_bytes(&mut self, bytes: &[u8]) -> Result<(), String> {
        if bytes.is_empty() {
            return Ok(());
        }
        self.writer
            .write_all(bytes)
            .map_err(|e| format!("audio_recorder: append {}: {}", self.path, e))?;
        self.data_size += bytes.len() as u64;
        Ok(())
    }

    /// Flush the buffer, seek back to the header, patch in the real data
    /// size + RIFF chunk size, and close the file. Returns total PCM bytes
    /// written (so the caller can sanity-check duration).
    pub fn finalize(mut self) -> Result<u64, String> {
        self.writer
            .flush()
            .map_err(|e| format!("audio_recorder: flush {}: {}", self.path, e))?;

        // u32 LE fields — cap at u32::MAX. Canonical WAV can't represent more
        // than ~4 GiB of PCM data anyway.
        let data_size_u32: u32 = self.data_size.try_into().unwrap_or(u32::MAX);
        let riff_size_u32: u32 = (self.data_size + 36).try_into().unwrap_or(u32::MAX);

        let file = self.writer.get_mut();

        file.seek(SeekFrom::Start(4))
            .map_err(|e| format!("audio_recorder: seek riff {}: {}", self.path, e))?;
        file.write_all(&riff_size_u32.to_le_bytes())
            .map_err(|e| format!("audio_recorder: patch riff {}: {}", self.path, e))?;

        file.seek(SeekFrom::Start(40))
            .map_err(|e| format!("audio_recorder: seek data {}: {}", self.path, e))?;
        file.write_all(&data_size_u32.to_le_bytes())
            .map_err(|e| format!("audio_recorder: patch data {}: {}", self.path, e))?;

        self.writer
            .flush()
            .map_err(|e| format!("audio_recorder: final flush {}: {}", self.path, e))?;

        tracing::info!(
            path = %self.path,
            bytes = self.data_size,
            "audio_recorder: finalized WAV"
        );

        Ok(self.data_size)
    }
}

fn write_placeholder_header<W: Write>(w: &mut W) -> std::io::Result<()> {
    // RIFF chunk descriptor
    w.write_all(b"RIFF")?;
    w.write_all(&0u32.to_le_bytes())?; // placeholder: 36 + data_size
    w.write_all(b"WAVE")?;

    // "fmt " sub-chunk (PCM, 16 bytes)
    w.write_all(b"fmt ")?;
    w.write_all(&16u32.to_le_bytes())?;
    w.write_all(&1u16.to_le_bytes())?; // PCM format code
    w.write_all(&CHANNELS.to_le_bytes())?;
    w.write_all(&SAMPLE_RATE.to_le_bytes())?;
    w.write_all(&BYTE_RATE.to_le_bytes())?;
    w.write_all(&BLOCK_ALIGN.to_le_bytes())?;
    w.write_all(&BITS_PER_SAMPLE.to_le_bytes())?;

    // "data" sub-chunk
    w.write_all(b"data")?;
    w.write_all(&0u32.to_le_bytes())?; // placeholder: data_size

    debug_assert_eq!(HEADER_SIZE, 44);
    Ok(())
}

fn write_placeholder_mono_header<W: Write>(w: &mut W) -> std::io::Result<()> {
    // RIFF chunk descriptor
    w.write_all(b"RIFF")?;
    w.write_all(&0u32.to_le_bytes())?; // placeholder: 36 + data_size
    w.write_all(b"WAVE")?;

    // "fmt " sub-chunk (PCM, 16 bytes)
    w.write_all(b"fmt ")?;
    w.write_all(&16u32.to_le_bytes())?;
    w.write_all(&1u16.to_le_bytes())?; // PCM format code
    w.write_all(&MONO_CHANNELS.to_le_bytes())?;
    w.write_all(&SAMPLE_RATE.to_le_bytes())?;
    w.write_all(&MONO_BYTE_RATE.to_le_bytes())?;
    w.write_all(&MONO_BLOCK_ALIGN.to_le_bytes())?;
    w.write_all(&BITS_PER_SAMPLE.to_le_bytes())?;

    // "data" sub-chunk
    w.write_all(b"data")?;
    w.write_all(&0u32.to_le_bytes())?; // placeholder: data_size

    Ok(())
}

/// Append-only mono WAV file writer for the Companion single-shot PTT path.
///
/// Format: PCM 16-bit LE, 16 kHz, 1 channel (mono) — the format Gemini
/// `inline_data` expects and what the cpal mic capture already delivers after
/// the existing `mix_to_mono` + `resample_linear` pass in `capture.rs`.
///
/// Usage: `create`, `append_mono_samples` zero or more times, `finalize`.
/// `finalize` returns `(bytes_written, duration_ms)` so the caller can
/// populate `CompanionRecording` without a second read.
pub struct MonoAudioFileWriter {
    writer: BufWriter<std::fs::File>,
    data_size: u64,
    path: String,
}

impl MonoAudioFileWriter {
    /// Open the file, write a placeholder WAV header, and prepare for appends.
    /// Creates the parent directory if missing.
    pub fn create(path: &Path) -> Result<Self, String> {
        let path_str = path.display().to_string();

        if let Some(parent) = path.parent() {
            if !parent.as_os_str().is_empty() {
                create_dir_all(parent).map_err(|e| {
                    format!("mono_audio_recorder: mkdir {}: {}", parent.display(), e)
                })?;
            }
        }

        let file = OpenOptions::new()
            .read(true)
            .write(true)
            .create(true)
            .truncate(true)
            .open(path)
            .map_err(|e| format!("mono_audio_recorder: open {}: {}", path_str, e))?;

        let mut writer = BufWriter::new(file);
        write_placeholder_mono_header(&mut writer)
            .map_err(|e| format!("mono_audio_recorder: write header {}: {}", path_str, e))?;

        Ok(Self { writer, data_size: 0, path: path_str })
    }

    /// Append mono i16 PCM samples (already at 16 kHz from capture.rs).
    pub fn append_mono_samples(&mut self, samples: &[i16]) -> Result<(), String> {
        if samples.is_empty() {
            return Ok(());
        }
        for &s in samples {
            self.writer
                .write_all(&s.to_le_bytes())
                .map_err(|e| format!("mono_audio_recorder: append {}: {}", self.path, e))?;
        }
        self.data_size += (samples.len() * 2) as u64;
        Ok(())
    }

    /// Flush, patch the WAV header size fields, and close the file.
    /// Returns `(pcm_bytes_written, duration_ms)`.
    pub fn finalize(mut self) -> Result<(u64, u64), String> {
        self.writer
            .flush()
            .map_err(|e| format!("mono_audio_recorder: flush {}: {}", self.path, e))?;

        let data_size_u32: u32 = self.data_size.try_into().unwrap_or(u32::MAX);
        let riff_size_u32: u32 = (self.data_size + 36).try_into().unwrap_or(u32::MAX);

        let file = self.writer.get_mut();

        file.seek(SeekFrom::Start(4))
            .map_err(|e| format!("mono_audio_recorder: seek riff {}: {}", self.path, e))?;
        file.write_all(&riff_size_u32.to_le_bytes())
            .map_err(|e| format!("mono_audio_recorder: patch riff {}: {}", self.path, e))?;

        file.seek(SeekFrom::Start(40))
            .map_err(|e| format!("mono_audio_recorder: seek data {}: {}", self.path, e))?;
        file.write_all(&data_size_u32.to_le_bytes())
            .map_err(|e| format!("mono_audio_recorder: patch data {}: {}", self.path, e))?;

        self.writer
            .flush()
            .map_err(|e| format!("mono_audio_recorder: final flush {}: {}", self.path, e))?;

        // duration_ms = bytes / (sample_rate * channels * bytes_per_sample) * 1000
        // = bytes / (16000 * 1 * 2) * 1000 = bytes / 32
        let duration_ms = self.data_size * 1000 / (SAMPLE_RATE as u64 * MONO_CHANNELS as u64 * 2);

        tracing::info!(
            path = %self.path,
            bytes = self.data_size,
            duration_ms,
            "mono_audio_recorder: finalized WAV"
        );

        Ok((self.data_size, duration_ms))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use std::io::Read;

    fn tmp_path(name: &str) -> std::path::PathBuf {
        let mut p = std::env::temp_dir();
        let nanos = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_nanos())
            .unwrap_or(0);
        p.push(format!("audio_recorder_test_{}_{}", nanos, name));
        p
    }

    fn read_u32_le(buf: &[u8], offset: usize) -> u32 {
        u32::from_le_bytes([
            buf[offset],
            buf[offset + 1],
            buf[offset + 2],
            buf[offset + 3],
        ])
    }

    fn read_u16_le(buf: &[u8], offset: usize) -> u16 {
        u16::from_le_bytes([buf[offset], buf[offset + 1]])
    }

    #[test]
    fn writes_and_patches_header_for_real_payload() {
        let mut path = tmp_path("payload");
        path.set_extension("wav");

        // 400 frames of stereo i16 = 400 * 4 bytes = 1600 bytes.
        // Two appends to exercise that path.
        let mut chunk_a = Vec::with_capacity(800);
        let mut chunk_b = Vec::with_capacity(800);
        for i in 0..200i16 {
            chunk_a.extend_from_slice(&i.to_le_bytes());
            chunk_a.extend_from_slice(&(-i).to_le_bytes());
        }
        for i in 200..400i16 {
            chunk_b.extend_from_slice(&i.to_le_bytes());
            chunk_b.extend_from_slice(&(-i).to_le_bytes());
        }
        let expected_data_size = (chunk_a.len() + chunk_b.len()) as u32;

        let mut w = AudioFileWriter::create(&path).expect("create");
        w.append_stereo_bytes(&chunk_a).expect("append a");
        w.append_stereo_bytes(&chunk_b).expect("append b");
        let total = w.finalize().expect("finalize");
        assert_eq!(total, expected_data_size as u64);

        let mut file = fs::File::open(&path).expect("open for read");
        let mut buf = Vec::new();
        file.read_to_end(&mut buf).expect("read");

        assert_eq!(buf.len(), 44 + expected_data_size as usize);

        // ASCII markers
        assert_eq!(&buf[0..4], b"RIFF");
        assert_eq!(&buf[8..12], b"WAVE");
        assert_eq!(&buf[12..16], b"fmt ");
        assert_eq!(&buf[36..40], b"data");

        // Patched size fields
        assert_eq!(read_u32_le(&buf, 4), 36 + expected_data_size);
        assert_eq!(read_u32_le(&buf, 40), expected_data_size);

        // fmt chunk sanity
        assert_eq!(read_u32_le(&buf, 16), 16);
        assert_eq!(read_u16_le(&buf, 20), 1);
        assert_eq!(read_u16_le(&buf, 22), 2);
        assert_eq!(read_u32_le(&buf, 24), 16_000);
        assert_eq!(read_u32_le(&buf, 28), 16_000 * 2 * 2);
        assert_eq!(read_u16_le(&buf, 32), 4);
        assert_eq!(read_u16_le(&buf, 34), 16);

        // Payload round-trips byte-for-byte.
        assert_eq!(&buf[44..44 + chunk_a.len()], chunk_a.as_slice());
        assert_eq!(&buf[44 + chunk_a.len()..], chunk_b.as_slice());

        let _ = fs::remove_file(&path);
    }

    #[test]
    fn finalize_without_appends_produces_empty_wav() {
        let mut path = tmp_path("empty");
        // Nest under a missing subdir to also exercise create_dir_all.
        path.push("nested");
        path.push("recording.wav");

        let w = AudioFileWriter::create(&path).expect("create");
        let total = w.finalize().expect("finalize");
        assert_eq!(total, 0);

        let mut file = fs::File::open(&path).expect("open for read");
        let mut buf = Vec::new();
        file.read_to_end(&mut buf).expect("read");

        assert_eq!(buf.len(), 44);
        assert_eq!(&buf[0..4], b"RIFF");
        assert_eq!(&buf[8..12], b"WAVE");
        assert_eq!(&buf[12..16], b"fmt ");
        assert_eq!(&buf[36..40], b"data");
        assert_eq!(read_u32_le(&buf, 4), 36);
        assert_eq!(read_u32_le(&buf, 40), 0);

        let _ = fs::remove_file(&path);
        if let Some(parent) = path.parent() {
            let _ = fs::remove_dir(parent);
            if let Some(grandparent) = parent.parent() {
                let _ = fs::remove_dir(grandparent);
            }
        }
    }
}
