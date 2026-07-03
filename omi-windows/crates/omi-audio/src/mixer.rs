use std::collections::VecDeque;

use tokio::sync::broadcast;

use crate::AudioChunk;

const MIX_BUFFER_MS: usize = 100;
const MIX_SAMPLES: usize = (crate::SAMPLE_RATE as usize) * MIX_BUFFER_MS / 1000;

/// Mix two audio broadcast streams into one output stream at the sample level.
/// Accumulates samples from both sources in ring buffers, sums overlapping
/// regions, and clamps to i16 range to prevent clipping.
pub async fn mix_streams(
    mut mic_rx: broadcast::Receiver<AudioChunk>,
    mut loopback_rx: broadcast::Receiver<AudioChunk>,
    mixed_tx: broadcast::Sender<AudioChunk>,
) {
    let mut mic_buf: VecDeque<i16> = VecDeque::with_capacity(MIX_SAMPLES * 4);
    let mut loopback_buf: VecDeque<i16> = VecDeque::with_capacity(MIX_SAMPLES * 4);
    let mut flush_interval = tokio::time::interval(
        std::time::Duration::from_millis(MIX_BUFFER_MS as u64),
    );

    loop {
        tokio::select! {
            Ok(chunk) = mic_rx.recv() => {
                mic_buf.extend(chunk.samples.iter());
            }
            Ok(chunk) = loopback_rx.recv() => {
                loopback_buf.extend(chunk.samples.iter());
            }
            _ = flush_interval.tick() => {
                let out_len = mic_buf.len().max(loopback_buf.len()).min(MIX_SAMPLES * 2);
                if out_len == 0 {
                    continue;
                }

                let mut mixed = Vec::with_capacity(out_len);
                for _ in 0..out_len {
                    let m = mic_buf.pop_front().unwrap_or(0) as i32;
                    let l = loopback_buf.pop_front().unwrap_or(0) as i32;
                    mixed.push(m.saturating_add(l).clamp(i16::MIN as i32, i16::MAX as i32) as i16);
                }

                let _ = mixed_tx.send(AudioChunk {
                    samples: mixed,
                    sample_rate: crate::SAMPLE_RATE,
                });
            }
            else => break,
        }
    }
    tracing::info!("Mixer stopped");
}
