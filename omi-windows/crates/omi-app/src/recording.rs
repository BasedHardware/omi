use dioxus::prelude::*;
use tokio::sync::broadcast;

use omi_transcription::models::TranscriptSegment;
use omi_transcription::streaming::DeepgramConfig;

/// Global recording state shared via Dioxus context.
#[derive(Debug, Clone, PartialEq)]
pub enum RecordingStatus {
    Idle,
    Recording { device: String },
    Error(String),
}

/// Holds all live transcript segments.
#[derive(Debug, Clone, Default)]
pub struct LiveTranscript {
    pub segments: Vec<TranscriptSegment>,
}

/// Start recording: mic capture → Deepgram streaming → transcript segments.
///
/// This function is NOT async-spawned with tokio::spawn (Signal is !Send).
/// Instead, it runs on the Dioxus async runtime (single-threaded) and uses
/// spawn_blocking + channels to bridge to the audio/WS threads.
pub async fn start_recording(
    api_key: String,
    status: &mut Signal<RecordingStatus>,
    transcript: &mut Signal<LiveTranscript>,
) {
    // Clear previous transcript
    transcript.set(LiveTranscript::default());

    // Audio broadcast channel
    let (audio_tx, _) = omi_audio::audio_channel(256);

    // Start mic capture (sync, runs on audio thread internally via cpal)
    let mic = match omi_audio::mic::start_mic_capture(audio_tx.clone()) {
        Ok(m) => {
            status.set(RecordingStatus::Recording {
                device: m.device_name().to_string(),
            });
            m
        }
        Err(e) => {
            status.set(RecordingStatus::Error(format!("Mic error: {e}")));
            return;
        }
    };

    tracing::info!("Recording started on {}", mic.device_name());

    // Transcript broadcast channel
    let (transcript_tx, mut transcript_rx) = broadcast::channel::<TranscriptSegment>(128);

    // Spawn Deepgram streaming on a Send-capable tokio task
    let audio_rx = audio_tx.subscribe();
    let dg_config = DeepgramConfig {
        api_key,
        sample_rate: omi_audio::SAMPLE_RATE,
        ..Default::default()
    };

    tokio::spawn(async move {
        if let Err(e) = omi_transcription::streaming::run_deepgram_stream(
            dg_config,
            audio_rx,
            transcript_tx,
        )
        .await
        {
            tracing::error!("Deepgram stream error: {e}");
        }
    });

    // Poll the transcript channel on the local (non-Send) Dioxus task
    // This keeps the mic handle alive and updates the UI signal
    let _mic_handle = mic;
    loop {
        match transcript_rx.recv().await {
            Ok(segment) => {
                let mut current = transcript.read().clone();
                if segment.is_final {
                    current.segments.retain(|s| s.is_final || s.start != segment.start);
                    current.segments.push(segment);
                } else {
                    if let Some(last) = current.segments.last_mut() {
                        if !last.is_final {
                            *last = segment;
                        } else {
                            current.segments.push(segment);
                        }
                    } else {
                        current.segments.push(segment);
                    }
                }
                transcript.set(current);
            }
            Err(broadcast::error::RecvError::Lagged(n)) => {
                tracing::warn!("Transcript UI lagged by {n}");
            }
            Err(broadcast::error::RecvError::Closed) => break,
        }
    }
}
