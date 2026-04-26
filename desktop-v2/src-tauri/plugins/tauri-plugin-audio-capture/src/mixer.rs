//! Interleave mic and system-audio mono streams into stereo i16 PCM.
//!
//! Channel 0 (left)  = microphone (user)
//! Channel 1 (right) = system audio (others)
//!
//! Ported from `desktop/Desktop/Sources/AudioMixer.swift`. The two sources
//! arrive asynchronously on different threads at different chunk cadences,
//! so we buffer each side and emit interleaved stereo bytes once both
//! buffers have enough data. On flush, the shorter side is padded with
//! silence so no trailing audio is dropped.

use std::collections::VecDeque;

/// Emit once both buffers hold at least 100 ms of 16 kHz audio (1600 samples).
const MIN_CHUNK_SAMPLES: usize = 1600;
/// Cap each buffer at ~1 s of audio to prevent unbounded growth if one side
/// stalls (e.g. nothing playing through the speakers).
const MAX_BUFFER_SAMPLES: usize = 16_000;
/// If the mic buffer exceeds this (300 ms) and the sys buffer hasn't caught
/// up, emit a chunk with silence on the sys side instead of holding the
/// mic audio hostage. Core Audio process taps only deliver frames while
/// audio is playing — during pure silence the tap is silent, so without
/// this fallback the mic transcript would stall whenever nothing is
/// playing through the speakers.
const MIC_ONLY_PATIENCE_SAMPLES: usize = 4800;

pub struct AudioMixer {
    mic: VecDeque<i16>,
    sys: VecDeque<i16>,
}

impl AudioMixer {
    pub fn new() -> Self {
        Self {
            mic: VecDeque::with_capacity(MAX_BUFFER_SAMPLES),
            sys: VecDeque::with_capacity(MAX_BUFFER_SAMPLES),
        }
    }

    pub fn push_mic(&mut self, samples: &[i16]) {
        self.mic.extend(samples.iter().copied());
        trim(&mut self.mic, MAX_BUFFER_SAMPLES);
    }

    pub fn push_sys(&mut self, samples: &[i16]) {
        self.sys.extend(samples.iter().copied());
        trim(&mut self.sys, MAX_BUFFER_SAMPLES);
    }

    /// Drain any output that can be emitted.
    ///
    /// Normally pairs `min(mic, sys)` samples and interleaves them. If the
    /// mic buffer builds past `MIC_ONLY_PATIENCE_SAMPLES` while sys is
    /// still short, emit a chunk padded with silence on the sys side so
    /// the mic transcript isn't stalled by silent system output.
    pub fn drain_stereo(&mut self) -> Option<Vec<u8>> {
        let mic_len = self.mic.len();
        let sys_len = self.sys.len();
        let pair_len = mic_len.min(sys_len);
        if pair_len >= MIN_CHUNK_SAMPLES {
            return Some(interleave_drain(&mut self.mic, &mut self.sys, pair_len));
        }
        if mic_len >= MIC_ONLY_PATIENCE_SAMPLES {
            let take = mic_len;
            while self.sys.len() < take {
                self.sys.push_back(0);
            }
            return Some(interleave_drain(&mut self.mic, &mut self.sys, take));
        }
        None
    }

    /// Drain everything, padding the shorter side with silence. Called on
    /// stop so trailing audio isn't lost.
    pub fn flush(&mut self) -> Option<Vec<u8>> {
        let len = self.mic.len().max(self.sys.len());
        if len == 0 {
            return None;
        }
        while self.mic.len() < len {
            self.mic.push_back(0);
        }
        while self.sys.len() < len {
            self.sys.push_back(0);
        }
        Some(interleave_drain(&mut self.mic, &mut self.sys, len))
    }
}

fn trim(buf: &mut VecDeque<i16>, cap: usize) {
    if buf.len() > cap {
        let excess = buf.len() - cap;
        buf.drain(..excess);
    }
}

fn interleave_drain(mic: &mut VecDeque<i16>, sys: &mut VecDeque<i16>, samples: usize) -> Vec<u8> {
    let mut out = Vec::with_capacity(samples * 4);
    for _ in 0..samples {
        let m = mic.pop_front().unwrap_or(0);
        let s = sys.pop_front().unwrap_or(0);
        out.extend_from_slice(&m.to_le_bytes());
        out.extend_from_slice(&s.to_le_bytes());
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn no_output_until_both_sides_have_min_chunk() {
        let mut m = AudioMixer::new();
        m.push_mic(&vec![1_i16; MIN_CHUNK_SAMPLES]);
        assert!(m.drain_stereo().is_none());
        m.push_sys(&vec![2_i16; MIN_CHUNK_SAMPLES - 1]);
        assert!(m.drain_stereo().is_none());
        m.push_sys(&[2_i16]);
        let out = m.drain_stereo().expect("should emit");
        assert_eq!(out.len(), MIN_CHUNK_SAMPLES * 4);
        // Left channel = 1 (mic), right = 2 (sys).
        assert_eq!(&out[0..2], &1_i16.to_le_bytes());
        assert_eq!(&out[2..4], &2_i16.to_le_bytes());
    }

    #[test]
    fn flush_pads_shorter_side_with_silence() {
        let mut m = AudioMixer::new();
        m.push_mic(&[5, 6, 7]);
        m.push_sys(&[9]);
        let out = m.flush().expect("flush emits remainder");
        // 3 frames of stereo i16 = 12 bytes.
        assert_eq!(out.len(), 12);
        assert_eq!(&out[0..2], &5_i16.to_le_bytes());
        assert_eq!(&out[2..4], &9_i16.to_le_bytes());
        assert_eq!(&out[4..6], &6_i16.to_le_bytes());
        assert_eq!(&out[6..8], &0_i16.to_le_bytes()); // sys padded
        assert_eq!(&out[8..10], &7_i16.to_le_bytes());
        assert_eq!(&out[10..12], &0_i16.to_le_bytes());
    }

    #[test]
    fn mic_not_held_hostage_when_sys_is_silent() {
        let mut m = AudioMixer::new();
        // Push just under the patience threshold — should still wait.
        m.push_mic(&vec![1_i16; MIC_ONLY_PATIENCE_SAMPLES - 1]);
        assert!(m.drain_stereo().is_none());
        // Once over the patience threshold with no sys data, emit with
        // silence on the sys side.
        m.push_mic(&[1_i16; 2]);
        let out = m.drain_stereo().expect("should emit mic-only padded");
        assert_eq!(out.len(), (MIC_ONLY_PATIENCE_SAMPLES + 1) * 4);
        // First frame: left = 1 (mic), right = 0 (silence).
        assert_eq!(&out[0..2], &1_i16.to_le_bytes());
        assert_eq!(&out[2..4], &0_i16.to_le_bytes());
    }

    #[test]
    fn buffer_trimmed_to_cap() {
        let mut m = AudioMixer::new();
        m.push_mic(&vec![1_i16; MAX_BUFFER_SAMPLES + 500]);
        assert_eq!(m.mic.len(), MAX_BUFFER_SAMPLES);
    }
}
