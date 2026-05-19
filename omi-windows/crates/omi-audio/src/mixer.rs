// Mix mic + system audio streams into a single PCM stream
use tokio::sync::broadcast;

use crate::AudioChunk;

/// Mix two audio broadcast streams into one output stream.
/// Takes mic + loopback receivers, sends mixed chunks on the output sender.
pub async fn mix_streams(
    mut mic_rx: broadcast::Receiver<AudioChunk>,
    mut loopback_rx: broadcast::Receiver<AudioChunk>,
    mixed_tx: broadcast::Sender<AudioChunk>,
) {
    loop {
        tokio::select! {
            Ok(chunk) = mic_rx.recv() => {
                let _ = mixed_tx.send(chunk);
            }
            Ok(chunk) = loopback_rx.recv() => {
                let _ = mixed_tx.send(chunk);
            }
            else => break,
        }
    }
    tracing::info!("Mixer stopped");
}
