mod capture;
pub mod models;
pub mod transcription;
pub mod vad;

use std::sync::{Arc, Mutex};

use chrono::Utc;
use models::{AudioDevice, CaptureConfig, CaptureState};
use serde::Serialize;
use tauri::{
    plugin::{Builder, TauriPlugin},
    Emitter, Manager, Runtime,
};
use tauri_plugin_store::StoreExt;
use tokio::sync::mpsc;
use tokio::task::JoinHandle;
use tokio_util::sync::CancellationToken;
use tracing;

use capture::CaptureHandle;
use transcription::{post_conversation, TranscriptionStream};
use vad::VADGateService;

const AUTH_STORE_PATH: &str = "auth.json";
const BACKEND_URL: &str = "http://127.0.0.1:10201";

/// Plugin-managed state holding the active capture handle and consumer task.
struct AudioCaptureState {
    handle: Option<CaptureHandle>,
    consumer: Option<JoinHandle<()>>,
    cancel: Option<CancellationToken>,
}

impl Default for AudioCaptureState {
    fn default() -> Self {
        Self {
            handle: None,
            consumer: None,
            cancel: None,
        }
    }
}

/// Pack mono i16 samples into stereo by duplicating into both channels.
/// Deepgram is configured for 2-channel multichannel input (mic | sys).
/// Until system-audio capture is wired up, mic is mirrored into the sys channel.
fn mono_to_stereo_bytes(mono: &[i16]) -> Vec<u8> {
    let mut out = Vec::with_capacity(mono.len() * 4);
    for &s in mono {
        let bytes = s.to_le_bytes();
        out.extend_from_slice(&bytes);
        out.extend_from_slice(&bytes);
    }
    out
}

/// Drain audio frames, run VAD, forward gated speech to Deepgram via the
/// transcription stream. On cancellation, finish the stream and POST the
/// accumulated segments to `/v1/conversations/from-segments`.
#[derive(Clone, Serialize)]
struct TranscriptEvent {
    text: String,
    is_final: bool,
    speaker: String,
    speaker_id: i64,
    is_user: bool,
    start: f64,
    end: f64,
}

async fn run_transcription_consumer<R: Runtime>(
    app: tauri::AppHandle<R>,
    mut rx: mpsc::UnboundedReceiver<Vec<i16>>,
    cancel: CancellationToken,
    id_token: String,
    device_name: Option<String>,
    language: String,
) {
    tracing::info!("[audio-capture] consumer task started");
    let started_at = Utc::now();

    // Open the WS in a separate task so this consumer starts draining `rx`
    // immediately. Until the WS is up, audio is dropped.
    let stream_slot: std::sync::Arc<tokio::sync::RwLock<Option<TranscriptionStream>>> =
        std::sync::Arc::new(tokio::sync::RwLock::new(None));

    if id_token.is_empty() {
        tracing::warn!("[audio-capture] skipping WS connect — no auth token");
    } else {
        let backend = BACKEND_URL.to_string();
        let token = id_token.clone();
        let slot = stream_slot.clone();
        let app_for_cb = app.clone();
        let on_transcript: transcription::TranscriptCallback =
            Arc::new(move |live: transcription::LiveTranscript| {
                tracing::info!(
                    "[audio-capture] emitting transcript:partial (final={}, speaker={}, len={}): {}",
                    live.is_final,
                    live.speaker,
                    live.text.len(),
                    &live.text.chars().take(60).collect::<String>()
                );
                if let Err(e) = app_for_cb.emit(
                    "transcript:partial",
                    TranscriptEvent {
                        text: live.text,
                        is_final: live.is_final,
                        speaker: live.speaker,
                        speaker_id: live.speaker_id,
                        is_user: live.is_user,
                        start: live.start,
                        end: live.end,
                    },
                ) {
                    tracing::warn!("[audio-capture] emit failed: {}", e);
                }
            });
        let language_for_ws = language.clone();
        tokio::spawn(async move {
            tracing::info!(
                "[audio-capture] opening WS to {} (language={})",
                backend,
                language_for_ws
            );
            match TranscriptionStream::connect(
                &backend,
                &token,
                &language_for_ws,
                Some(on_transcript),
            )
            .await
            {
                Ok(s) => {
                    tracing::info!("[audio-capture] WS connected");
                    *slot.write().await = Some(s);
                }
                Err(e) => {
                    tracing::error!("[audio-capture] failed to open transcription stream: {}", e);
                }
            }
        });
    }

    let mut vad = VADGateService::new();
    let mut sent_chunks: u64 = 0;
    let mut total_chunks: u64 = 0;
    let mut last_log = std::time::Instant::now();

    loop {
        tokio::select! {
            _ = cancel.cancelled() => {
                tracing::info!("[audio-capture] consumer cancelled");
                break;
            }
            maybe_chunk = rx.recv() => {
                let Some(mono) = maybe_chunk else {
                    tracing::info!("[audio-capture] audio channel closed");
                    break;
                };
                let stereo = mono_to_stereo_bytes(&mono);
                let out = vad.process_audio(&stereo);
                total_chunks += 1;
                if !out.audio_to_send.is_empty() {
                    if let Some(s) = stream_slot.read().await.as_ref() {
                        s.send_audio(out.audio_to_send);
                        sent_chunks += 1;
                    }
                }
                if last_log.elapsed().as_secs() >= 5 {
                    let connected = stream_slot.read().await.is_some();
                    tracing::info!(
                        "[audio-capture] stats: ws={}, total={}, sent_to_dg={}",
                        connected, total_chunks, sent_chunks
                    );
                    last_log = std::time::Instant::now();
                }
            }
        }
    }

    let segments = match stream_slot.write().await.take() {
        Some(s) => s.finish().await,
        None => Vec::new(),
    };

    let finished_at = Utc::now();
    if let Err(e) = post_conversation(
        BACKEND_URL,
        &id_token,
        segments,
        started_at,
        finished_at,
        device_name,
    )
    .await
    {
        tracing::error!("[audio-capture] failed to create conversation: {}", e);
    }

    tracing::info!("[audio-capture] consumer task exiting");
}

/// Read the Firebase ID token from the Tauri store (written by the auth flow).
/// Falls back to `store()` to load on demand if it hasn't been opened yet.
fn read_id_token<R: Runtime>(app: &tauri::AppHandle<R>) -> Option<String> {
    let store = app
        .get_store(AUTH_STORE_PATH)
        .or_else(|| app.store(AUTH_STORE_PATH).ok())?;
    let val = store.get("id_token")?;
    val.as_str().map(|s| s.to_string())
}

// ---------------------------------------------------------------------------
// Tauri commands
// ---------------------------------------------------------------------------

/// Return the list of input audio devices.
#[tauri::command]
fn list_devices() -> Vec<AudioDevice> {
    capture::list_audio_devices()
}

/// Start recording with the given configuration.
#[tauri::command]
async fn start_recording<R: Runtime>(
    app: tauri::AppHandle<R>,
    config: Option<CaptureConfig>,
) -> Result<CaptureState, String> {
    let state = app.state::<Mutex<AudioCaptureState>>();
    let mut guard = state
        .lock()
        .map_err(|e| format!("Failed to lock state: {}", e))?;

    if guard.handle.is_some() {
        return Err("Capture is already running".to_string());
    }

    let config = config.unwrap_or_default();
    let language = config.language.clone();
    let (tx, rx) = mpsc::unbounded_channel::<Vec<i16>>();

    let handle = capture::start_capture(config, tx)?;

    let capture_state = CaptureState {
        is_capturing: true,
        device_name: Some(handle.device_name.clone()),
        sample_rate: handle.sample_rate,
    };

    let id_token = read_id_token(&app).unwrap_or_default();
    if id_token.is_empty() {
        tracing::warn!("[audio-capture] no id_token in store — recording without transcription");
    }

    let cancel = CancellationToken::new();
    let device_name = Some(handle.device_name.clone());
    let consumer = tokio::spawn(run_transcription_consumer(
        app.clone(),
        rx,
        cancel.clone(),
        id_token,
        device_name,
        language,
    ));

    tracing::info!(
        "Recording started: device={}, rate={}",
        capture_state.device_name.as_deref().unwrap_or("?"),
        capture_state.sample_rate
    );

    guard.handle = Some(handle);
    guard.consumer = Some(consumer);
    guard.cancel = Some(cancel);

    Ok(capture_state)
}

/// Stop the active recording.
#[tauri::command]
fn stop_recording<R: Runtime>(app: tauri::AppHandle<R>) -> Result<CaptureState, String> {
    let state = app.state::<Mutex<AudioCaptureState>>();
    let mut guard = state
        .lock()
        .map_err(|e| format!("Failed to lock state: {}", e))?;

    if guard.handle.is_none() {
        return Err("No capture is running".to_string());
    }

    // Dropping the handle stops the cpal stream and closes the channel.
    guard.handle = None;
    if let Some(c) = guard.cancel.take() {
        c.cancel();
    }
    // Don't abort — let the consumer finish the WS gracefully and POST the
    // conversation. The cpal channel is already closed so it will drain quickly.
    if let Some(_task) = guard.consumer.take() {
        // Detach; consumer will exit on its own.
    }

    tracing::info!("Recording stopped");

    Ok(CaptureState::default())
}

/// Return the current capture state.
#[tauri::command]
fn get_capture_state<R: Runtime>(app: tauri::AppHandle<R>) -> Result<CaptureState, String> {
    let state = app.state::<Mutex<AudioCaptureState>>();
    let guard = state
        .lock()
        .map_err(|e| format!("Failed to lock state: {}", e))?;

    match &guard.handle {
        Some(h) => Ok(CaptureState {
            is_capturing: true,
            device_name: Some(h.device_name.clone()),
            sample_rate: h.sample_rate,
        }),
        None => Ok(CaptureState::default()),
    }
}

// ---------------------------------------------------------------------------
// Plugin initialisation
// ---------------------------------------------------------------------------

/// Initialise the audio capture plugin.
///
/// Usage in `main.rs`:
/// ```ignore
/// tauri::Builder::default()
///     .plugin(tauri_plugin_audio_capture::init())
/// ```
pub fn init<R: Runtime>() -> TauriPlugin<R> {
    Builder::new("audio-capture")
        .invoke_handler(tauri::generate_handler![
            list_devices,
            start_recording,
            stop_recording,
            get_capture_state,
        ])
        .setup(|app, _api| {
            app.manage(Mutex::new(AudioCaptureState::default()));
            tracing::info!("Audio capture plugin initialised");
            Ok(())
        })
        .build()
}
