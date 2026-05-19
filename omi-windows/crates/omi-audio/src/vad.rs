use crate::AudioChunk;

/// Simple energy-based voice activity detection.
/// Returns true if the RMS energy of the chunk exceeds the threshold.
pub fn is_speech(chunk: &AudioChunk, threshold: f64) -> bool {
    if chunk.samples.is_empty() {
        return false;
    }
    let sum_sq: f64 = chunk
        .samples
        .iter()
        .map(|&s| (s as f64) * (s as f64))
        .sum();
    let rms = (sum_sq / chunk.samples.len() as f64).sqrt();
    rms > threshold
}

/// Default RMS threshold for speech detection (tuned for 16-bit PCM).
pub const DEFAULT_SPEECH_THRESHOLD: f64 = 300.0;
