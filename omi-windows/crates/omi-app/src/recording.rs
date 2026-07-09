use std::sync::Arc;

use dioxus::prelude::*;
use tokio::sync::{broadcast, oneshot};

use crate::app::Db;
use crate::config::AppConfig;
use crate::proactive::ProactiveEngine;
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

/// Token to stop an active recording session.
pub struct StopRecording(oneshot::Sender<()>);

impl StopRecording {
    pub fn new(tx: oneshot::Sender<()>) -> Self {
        Self(tx)
    }

    pub fn stop(self) {
        let _ = self.0.send(());
    }
}

/// Start recording: mic capture → Deepgram streaming → transcript segments → DB.
///
/// Call `StopRecording::new()` to get a stop handle, pass its receiver here.
pub async fn start_recording(
    api_key: String,
    diarize: bool,
    db: Option<Db>,
    cfg: AppConfig,
    stop_rx: tokio::sync::oneshot::Receiver<()>,
    status: &mut Signal<RecordingStatus>,
    transcript: &mut Signal<LiveTranscript>,
) {
    start_recording_with_proactive(api_key, diarize, db, cfg, stop_rx, status, transcript, None).await;
}

/// Internal: start recording + optionally fire proactive engine on completion.
pub async fn start_recording_with_proactive(
    api_key: String,
    diarize: bool,
    db: Option<Db>,
    cfg: AppConfig,
    stop_rx: tokio::sync::oneshot::Receiver<()>,
    status: &mut Signal<RecordingStatus>,
    transcript: &mut Signal<LiveTranscript>,
    proactive: Option<Arc<ProactiveEngine>>,
) {
    // Clear previous transcript
    transcript.set(LiveTranscript::default());
    tracing::info!("[RECORDING] start_recording called, API key len={}", api_key.len());

    // Audio broadcast channel — keep initial rx alive until subscribed
    let (audio_tx, audio_rx0) = omi_audio::audio_channel(256);
    tracing::info!("[RECORDING] Audio broadcast channel created (capacity=256)");

    // Start mic capture
    tracing::info!("[RECORDING] Attempting to start mic capture...");
    let preferred = if cfg.mic_device_name.is_empty() {
        None
    } else {
        Some(cfg.mic_device_name.as_str())
    };
    let gain = cfg.mic_gain;
    tracing::info!("[RECORDING] Mic software gain: {gain}x");
    let mic = match omi_audio::mic::start_mic_capture_with_gain(audio_tx.clone(), preferred, gain) {
        Ok(m) => {
            tracing::info!("[RECORDING] Mic capture started on device: {}", m.device_name());
            status.set(RecordingStatus::Recording {
                device: m.device_name().to_string(),
            });
            m
        }
        Err(e) => {
            tracing::error!("[RECORDING] Mic capture failed: {e}");
            status.set(RecordingStatus::Error(format!("Mic error: {e}")));
            return;
        }
    };

    let mut loopback = None;
    if cfg.system_audio_enabled {
        tracing::info!("[RECORDING] Attempting to start WASAPI loopback capture...");
        match omi_audio::loopback::start_loopback_capture(audio_tx.clone()) {
            Ok(stream) => {
                tracing::info!("[RECORDING] WASAPI loopback capture started: {}", stream.device_name());
                loopback = Some(stream);
            }
            Err(e) => {
                tracing::error!("[RECORDING] WASAPI loopback capture failed: {e}");
            }
        }
    }

    tracing::info!("[RECORDING] Recording started on '{}', preparing Deepgram config...", mic.device_name());

    // Create a conversation record in the DB
    let conversation_id: Option<String> = db.as_ref().and_then(|Db(d)| {
        match d.create_conversation(None) {
            Ok(id) => {
                tracing::info!("[RECORDING] Created conversation {id} in DB");
                Some(id)
            }
            Err(e) => {
                tracing::error!("[RECORDING] Failed to create conversation: {e}");
                None
            }
        }
    });

    // Transcript channel
    let (transcript_tx, mut transcript_rx) = broadcast::channel::<TranscriptSegment>(128);

    let mut stop_rx = stop_rx;

    // Deepgram WS on a tokio Send task, using the initial audio_rx0
    let dg_config = DeepgramConfig {
        api_key: api_key.clone(),
        sample_rate: omi_audio::SAMPLE_RATE,
        diarize,
        ..Default::default()
    };
    tracing::info!("[RECORDING] DeepgramConfig: model={} lang={} rate={} enc={} ch={} diarize={}",
        dg_config.model, dg_config.language, dg_config.sample_rate,
        dg_config.encoding, dg_config.channels, dg_config.diarize);

    // Error feedback channel back to Dioxus task
    let (err_tx, mut err_rx) = oneshot::channel::<String>();

    tracing::info!("[RECORDING] Spawning Deepgram stream task...");
    tokio::spawn(async move {
        tracing::info!("[RECORDING] Deepgram task spawned, calling run_deepgram_stream");
        if let Err(e) = omi_transcription::streaming::run_deepgram_stream(
            dg_config,
            audio_rx0,
            transcript_tx,
        )
        .await
        {
            tracing::error!("[RECORDING] Deepgram stream error: {e:#}");
            let _ = err_tx.send(e.to_string());
        } else {
            tracing::info!("[RECORDING] Deepgram stream ended cleanly");
        }
    });
    tracing::info!("[RECORDING] Deepgram task spawned, entering poll loop...");

    // Poll transcript + stop signal on Dioxus task (keeps stream handles alive)
    let _mic_handle = mic;
    let _loopback_handle = loopback;
    let mut segment_count: u32 = 0;
    tracing::info!("[RECORDING] Entering poll loop (stop_rx + transcript_rx + err_rx)");
    loop {
        tokio::select! {
            // Stop requested from UI
            _ = &mut stop_rx => {
                tracing::info!("[RECORDING] Stop signal received from UI after {segment_count} segments");
                break;
            }
            // Deepgram errored
            Ok(err_msg) = &mut err_rx => {
                tracing::error!("[RECORDING] Deepgram error received: {err_msg}");
                status.set(RecordingStatus::Error(err_msg));
                break;
            }
            // New transcript segment
            result = transcript_rx.recv() => {
                match result {
                    Ok(segment) => {
                        segment_count += 1;
                        tracing::info!("[RECORDING] UI got segment #{segment_count}: final={} speaker={} \"{}\"",
                            segment.is_final, segment.speaker, segment.text);

                        // Persist final segments to DB
                        if segment.is_final {
                            if let (Some(ref conv_id), Some(Db(ref d))) = (&conversation_id, &db) {
                                if let Err(e) = d.insert_segment(
                                    conv_id,
                                    segment.speaker,
                                    &segment.text,
                                    segment.start,
                                    segment.end,
                                    true,
                                ) {
                                    tracing::error!("[RECORDING] Failed to insert segment: {e}");
                                }
                            }
                        }

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
                        tracing::warn!("[RECORDING] Transcript UI lagged by {n} messages");
                    }
                    Err(broadcast::error::RecvError::Closed) => {
                        tracing::warn!("[RECORDING] Transcript channel closed after {segment_count} segments");
                        break;
                    }
                }
            }
        }
    }

    tracing::info!("[RECORDING] Session ended. Total segments received: {segment_count}");

    // Complete the conversation in DB and trigger LLM summarization
    if let (Some(ref conv_id), Some(Db(ref d))) = (&conversation_id, &db) {
        if let Err(e) = d.complete_conversation(conv_id) {
            tracing::error!("[RECORDING] Failed to complete conversation {conv_id}: {e}");
        } else {
            tracing::info!("[RECORDING] Marked conversation {conv_id} as completed, launching summarization...");
            let db_clone = d.clone();
            let conv_id_clone = conv_id.clone();
            let cfg_clone = cfg.clone();
            let proactive_clone = proactive.clone();
            tokio::spawn(async move {
                crate::llm::process_conversation(&db_clone, &conv_id_clone, &cfg_clone).await;
                // Fire proactive suggestions now that the conversation is processed
                if let Some(engine) = proactive_clone {
                    if let Ok(rt_dummy) = tokio::task::spawn_blocking(|| {
                        crate::agent_runtime::AgentRuntime::new()
                    }).await {
                        engine.on_conversation_ended(&db_clone, &conv_id_clone, &cfg_clone, &rt_dummy).await;
                    }
                }
            });
        }
    }

    status.set(RecordingStatus::Idle);
}
