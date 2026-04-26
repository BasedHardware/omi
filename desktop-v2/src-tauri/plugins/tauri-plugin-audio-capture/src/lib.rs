mod audio_recorder;
mod capture;
mod mixer;
pub mod models;
mod retry;
mod storage;
#[cfg(target_os = "macos")]
mod system_audio_macos;
pub mod transcription;
pub mod vad;

use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
use std::time::Duration;

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

use audio_recorder::{AudioFileWriter, MonoAudioFileWriter};
use capture::CaptureHandle;
use mixer::AudioMixer;
use models::CompanionRecording;
use retry::TranscriptionRetryService;
use storage::{LocalSegment, LocalSession, TranscriptionStorage};
use transcription::{post_conversation, TranscriptionStream};
use vad::VADGateService;

const AUTH_STORE_PATH: &str = "auth.json";
const BACKEND_URL: &str = "http://127.0.0.1:10201";

/// Bounded capacity for the system-audio mpsc. Matches the consumer cadence;
/// the real-time HAL callback drops on full rather than blocking. Sized
/// generously (~2.5 s of 10 ms chunks) so a brief consumer stall (VAD
/// inference, Deepgram send) can't silently lose tap frames.
#[cfg(target_os = "macos")]
const SYS_AUDIO_CHANNEL_CAPACITY: usize = 256;

#[cfg(target_os = "macos")]
type SysHandle = system_audio_macos::SystemAudioCapture;
#[cfg(not(target_os = "macos"))]
type SysHandle = ();

/// Live per-channel sample counters, shared between the consumer task and
/// `get_capture_state`. Lets the Settings panel show real-time evidence
/// that system audio is flowing during an actual recording.
#[derive(Default)]
struct CaptureCounters {
    mic_samples: AtomicU64,
    sys_samples: AtomicU64,
}

/// Plugin-managed state holding the active capture handle and consumer task.
struct AudioCaptureState {
    handle: Option<CaptureHandle>,
    sys_handle: Option<SysHandle>,
    consumer: Option<JoinHandle<Result<(), String>>>,
    cancel: Option<CancellationToken>,
    counters: Arc<CaptureCounters>,
    /// SQLite-backed persist-then-POST store. `None` only if init failed —
    /// recording still works but segments aren't checkpointed for retry.
    storage: Option<Arc<TranscriptionStorage>>,
    /// Row id of the session currently being recorded. Used by
    /// `run_transcription_consumer` to append segments and by the
    /// retry service to reconcile on failure.
    session_id: Option<i64>,
    /// When `start_recording` is called with `mic_only: true`, the companion
    /// consumer task writes raw mono PCM here and returns the finalized WAV
    /// path + duration via `stop_recording`.
    companion_wav_path: Option<String>,
    /// Consumer task for the `mic_only` Companion PTT mode. Populated instead
    /// of `consumer` when `start_recording` is called with `mic_only: true`.
    /// Returns the final `CompanionRecording` on success.
    companion_consumer: Option<JoinHandle<Result<CompanionRecording, String>>>,
}

impl Default for AudioCaptureState {
    fn default() -> Self {
        Self {
            handle: None,
            sys_handle: None,
            consumer: None,
            cancel: None,
            counters: Arc::new(CaptureCounters::default()),
            storage: None,
            session_id: None,
            companion_wav_path: None,
            companion_consumer: None,
        }
    }
}

/// Pack mono i16 samples into stereo by duplicating into both channels.
/// Used only as a fallback when system-audio capture is disabled or
/// unavailable — Deepgram is configured for 2-channel multichannel input
/// (channel 0 = mic/user, channel 1 = sys/others), so we still need to
/// deliver two channels even when we only have the mic.
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
    mut mic_rx: mpsc::UnboundedReceiver<Vec<i16>>,
    mut sys_rx: Option<mpsc::Receiver<Vec<i16>>>,
    counters: Arc<CaptureCounters>,
    cancel: CancellationToken,
    id_token: String,
    device_name: Option<String>,
    language: String,
    storage: Option<Arc<TranscriptionStorage>>,
    session_id: Option<i64>,
    mut audio_writer: Option<AudioFileWriter>,
    skip_live: bool,
) -> Result<(), String> {
    tracing::info!(
        "[audio-capture] consumer task started (system_audio={})",
        sys_rx.is_some()
    );
    let started_at = Utc::now();

    // Open the WS in a separate task so this consumer starts draining `rx`
    // immediately. Until the WS is up, audio is dropped.
    let stream_slot: std::sync::Arc<tokio::sync::RwLock<Option<TranscriptionStream>>> =
        std::sync::Arc::new(tokio::sync::RwLock::new(None));

    if skip_live {
        tracing::info!("[audio-capture] live transcription disabled — recording audio only");
    } else if id_token.is_empty() {
        tracing::warn!("[audio-capture] skipping WS connect — no auth token");
    } else {
        let backend = BACKEND_URL.to_string();
        let token = id_token.clone();
        let slot = stream_slot.clone();
        let app_for_cb = app.clone();
        let storage_for_cb = storage.clone();
        let on_transcript: transcription::TranscriptCallback =
            Arc::new(move |live: transcription::LiveTranscript| {
                tracing::info!(
                    "[audio-capture] emitting transcript:partial (final={}, speaker={}, len={}): {}",
                    live.is_final,
                    live.speaker,
                    live.text.len(),
                    &live.text.chars().take(60).collect::<String>()
                );
                // Persist finalized segments immediately — mirrors the
                // Swift "persist-then-POST" parity so a crash between now
                // and the end of the session can't lose text that already
                // came back from Deepgram.
                if live.is_final {
                    if let (Some(s), Some(sid)) = (storage_for_cb.as_ref(), session_id) {
                        if let Err(e) = s.append_segment(
                            sid,
                            &live.text,
                            &live.speaker,
                            live.speaker_id,
                            live.is_user,
                            live.start,
                            live.end,
                        ) {
                            tracing::warn!(
                                "[audio-capture] append_segment failed (session={}): {}",
                                sid,
                                e
                            );
                        }
                    }
                }
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
        let watchdog_cancel = cancel.clone();
        // Persistent Deepgram supervisor — connect on start, reconnect
        // whenever the current stream dies (peer close, socket error) or
        // goes stale (no traffic for STALE_SECS while we're still sending
        // audio). Without this, a WS drop mid-recording silently stops
        // transcription for the rest of the session (lost the tail of a
        // long meeting — Swift `TranscriptionService` has the same
        // reconnect+stale logic).
        tokio::spawn(async move {
            const STALE_SECS: i64 = 90;
            const MAX_BACKOFF_SECS: u64 = 30;
            let mut backoff_secs: u64 = 1;

            loop {
                if watchdog_cancel.is_cancelled() {
                    break;
                }

                tracing::info!(
                    "[audio-capture] opening WS to {} (language={})",
                    backend,
                    language_for_ws
                );
                match TranscriptionStream::connect(
                    &backend,
                    &token,
                    &language_for_ws,
                    Some(on_transcript.clone()),
                )
                .await
                {
                    Ok(s) => {
                        tracing::info!("[audio-capture] WS connected");
                        backoff_secs = 1;
                        *slot.write().await = Some(s);
                    }
                    Err(e) => {
                        tracing::error!(
                            "[audio-capture] WS connect failed (backoff={}s): {}",
                            backoff_secs,
                            e
                        );
                        tokio::select! {
                            _ = watchdog_cancel.cancelled() => break,
                            _ = tokio::time::sleep(Duration::from_secs(backoff_secs)) => {}
                        }
                        backoff_secs = (backoff_secs * 2).min(MAX_BACKOFF_SECS);
                        continue;
                    }
                }

                // Monitor the current stream. If it stops being alive or
                // stops receiving data, tear it down and reconnect.
                loop {
                    tokio::select! {
                        _ = watchdog_cancel.cancelled() => return,
                        _ = tokio::time::sleep(Duration::from_secs(5)) => {}
                    }
                    let (dead, stale) = {
                        let guard = slot.read().await;
                        match guard.as_ref() {
                            Some(s) => (!s.is_alive(), s.seconds_since_activity() > STALE_SECS),
                            None => (true, false),
                        }
                    };
                    if dead || stale {
                        tracing::warn!(
                            "[audio-capture] WS unhealthy (dead={}, stale={}) — reconnecting",
                            dead,
                            stale
                        );
                        // Take the old stream out and tell it to shut down
                        // cleanly on a background task so we don't block
                        // the watchdog waiting for it to drain.
                        if let Some(old) = slot.write().await.take() {
                            tokio::spawn(async move {
                                let _ = old.finish().await;
                            });
                        }
                        break;
                    }
                }
            }
            tracing::info!("[audio-capture] WS watchdog exiting");
        });
    }

    let mut vad = VADGateService::new();
    let mut mixer = AudioMixer::new();
    let mut sent_chunks: u64 = 0;
    let mut total_chunks: u64 = 0;
    let mut last_log = std::time::Instant::now();

    // Drain all stereo chunks the mixer can emit, caching the WS read-lock
    // across the loop so we don't reacquire it per chunk on the hot path.
    //
    // `vad.process_audio` runs synchronous ONNX inference on the Silero
    // model. Left in an async context it monopolises the current Tokio
    // worker for the duration of the inference (~1–3 ms per chunk, hundreds
    // of times a second) which starves other tasks on the same runtime —
    // most visibly the embedded Axum backend. `block_in_place` keeps us on
    // the same thread but hands off any other tasks scheduled here so the
    // worker pool stays responsive.
    async fn drain_mixer_and_forward(
        mixer: &mut AudioMixer,
        vad: &mut VADGateService,
        stream_slot: &Arc<tokio::sync::RwLock<Option<TranscriptionStream>>>,
        sent_chunks: &mut u64,
        audio_writer: &mut Option<AudioFileWriter>,
    ) {
        let Some(first) = mixer.drain_stereo() else {
            return;
        };
        let stream = stream_slot.read().await;
        let stream_ref = stream.as_ref();
        let mut next = Some(first);
        while let Some(stereo) = next.take() {
            // Persist the *unsluiced* mixed audio before VAD gates it. The
            // WAV on disk is the durable record for post-stop re-processing
            // even if the live WS path drops frames or loses its socket.
            if let Some(w) = audio_writer.as_mut() {
                if let Err(e) = w.append_stereo_bytes(&stereo) {
                    tracing::warn!("[audio-capture] audio file append failed: {}", e);
                }
            }
            let out = tokio::task::block_in_place(|| vad.process_audio(&stereo));
            if !out.audio_to_send.is_empty() {
                if let Some(s) = stream_ref {
                    s.send_audio(out.audio_to_send);
                    *sent_chunks += 1;
                }
            }
            next = mixer.drain_stereo();
        }
    }

    // Mic-only fallback: duplicate mono into both channels and forward.
    async fn forward_mic_only(
        mono: &[i16],
        vad: &mut VADGateService,
        stream_slot: &Arc<tokio::sync::RwLock<Option<TranscriptionStream>>>,
        sent_chunks: &mut u64,
        audio_writer: &mut Option<AudioFileWriter>,
    ) {
        let stereo = mono_to_stereo_bytes(mono);
        if let Some(w) = audio_writer.as_mut() {
            if let Err(e) = w.append_stereo_bytes(&stereo) {
                tracing::warn!("[audio-capture] audio file append failed: {}", e);
            }
        }
        let out = tokio::task::block_in_place(|| vad.process_audio(&stereo));
        if out.audio_to_send.is_empty() {
            return;
        }
        if let Some(s) = stream_slot.read().await.as_ref() {
            s.send_audio(out.audio_to_send);
            *sent_chunks += 1;
        }
    }

    loop {
        tokio::select! {
            _ = cancel.cancelled() => {
                tracing::info!("[audio-capture] consumer cancelled");
                break;
            }
            maybe_chunk = mic_rx.recv() => {
                let Some(mono) = maybe_chunk else {
                    tracing::info!("[audio-capture] mic channel closed");
                    break;
                };
                total_chunks += 1;
                counters.mic_samples.fetch_add(mono.len() as u64, Ordering::Relaxed);
                if sys_rx.is_some() {
                    mixer.push_mic(&mono);
                    drain_mixer_and_forward(&mut mixer, &mut vad, &stream_slot, &mut sent_chunks, &mut audio_writer).await;
                } else {
                    forward_mic_only(&mono, &mut vad, &stream_slot, &mut sent_chunks, &mut audio_writer).await;
                }
            }
            maybe_chunk = async {
                match sys_rx.as_mut() {
                    Some(rx) => rx.recv().await,
                    None => std::future::pending().await,
                }
            } => {
                let Some(mono) = maybe_chunk else {
                    tracing::warn!("[audio-capture] system-audio channel closed — switching to mic-only");
                    sys_rx = None;
                    continue;
                };
                counters.sys_samples.fetch_add(mono.len() as u64, Ordering::Relaxed);
                mixer.push_sys(&mono);
                drain_mixer_and_forward(&mut mixer, &mut vad, &stream_slot, &mut sent_chunks, &mut audio_writer).await;
            }
        }

        if last_log.elapsed().as_secs() >= 5 {
            let connected = stream_slot.read().await.is_some();
            tracing::info!(
                "[audio-capture] stats: ws={}, total_mic={}, sent_to_dg={}, sys={}",
                connected,
                total_chunks,
                sent_chunks,
                sys_rx.is_some()
            );
            last_log = std::time::Instant::now();
        }
    }

    // Flush any trailing mixer audio (pads the shorter side with silence).
    if let Some(stereo) = mixer.flush() {
        if let Some(w) = audio_writer.as_mut() {
            if let Err(e) = w.append_stereo_bytes(&stereo) {
                tracing::warn!("[audio-capture] audio file append failed: {}", e);
            }
        }
        let out = tokio::task::block_in_place(|| vad.process_audio(&stereo));
        if !out.audio_to_send.is_empty() {
            if let Some(s) = stream_slot.read().await.as_ref() {
                s.send_audio(out.audio_to_send);
            }
        }
    }

    // Close the WAV — patches the header with the real data size. Happens
    // before the WS finish + POST so the durable recording is on disk even
    // if the subsequent network work errors out.
    if let Some(writer) = audio_writer.take() {
        if let Err(e) = tokio::task::block_in_place(|| writer.finalize()) {
            tracing::warn!("[audio-capture] audio file finalize failed: {}", e);
        }
    }

    let segments = match stream_slot.write().await.take() {
        Some(s) => s.finish().await,
        None => Vec::new(),
    };

    // Persist-then-POST path — delegates the mark_uploading / POST /
    // mark_completed / mark_failed / meeting:synced emit / retry-backoff
    // flow to the retry service so there's one authoritative implementation.
    if let (Some(s), Some(sid)) = (storage.as_ref(), session_id) {
        if let Err(e) = s.finish_session(sid) {
            tracing::warn!("[audio-capture] finish_session failed (session={}): {}", sid, e);
        }
        let result = retry::retry_one(s, &app, sid).await;
        tracing::info!("[audio-capture] consumer task exiting");
        return result;
    }

    // Fallback — storage init failed at plugin setup, so we can't
    // checkpoint. POST directly; silent failure is the best we can do
    // here since there's nowhere to park the segments.
    if segments.is_empty() {
        tracing::info!("[audio-capture] consumer task exiting (no segments, no storage)");
        return Err("no transcription captured".into());
    }
    let finished_at = Utc::now();
    let result = post_conversation(
        BACKEND_URL,
        &id_token,
        segments,
        started_at,
        finished_at,
        device_name,
        &language,
    )
    .await;
    if let Ok(backend_id) = &result {
        if let Err(e) = app.emit(
            "meeting:synced",
            serde_json::json!({
                "session_id": session_id,
                "backend_id": backend_id,
            }),
        ) {
            tracing::warn!("[audio-capture] emit meeting:synced failed: {}", e);
        }
    }
    tracing::info!("[audio-capture] consumer task exiting");
    result.map(|_| ())
}

/// Mic-only consumer for the Companion PTT path.
///
/// Drains raw mono i16 chunks from `mic_rx`, writes them straight to
/// `wav_writer` (no VAD, no Deepgram, no mixer), and finalizes the WAV on
/// cancellation.  Returns `Ok(CompanionRecording)` with the final WAV path and
/// duration so `stop_recording` can surface these to the caller.
async fn run_companion_consumer(
    mut mic_rx: mpsc::UnboundedReceiver<Vec<i16>>,
    cancel: CancellationToken,
    mut wav_writer: MonoAudioFileWriter,
    wav_path: String,
) -> Result<CompanionRecording, String> {
    tracing::info!("[companion] mic-only consumer started (path={})", wav_path);

    loop {
        tokio::select! {
            _ = cancel.cancelled() => {
                tracing::info!("[companion] mic-only consumer cancelled");
                break;
            }
            maybe_chunk = mic_rx.recv() => {
                let Some(mono) = maybe_chunk else {
                    tracing::info!("[companion] mic channel closed");
                    break;
                };
                if let Err(e) = wav_writer.append_mono_samples(&mono) {
                    tracing::warn!("[companion] WAV append failed: {}", e);
                }
            }
        }
    }

    let (_, duration_ms) = tokio::task::block_in_place(|| wav_writer.finalize())?;

    Ok(CompanionRecording {
        wav_path,
        duration_ms,
        sample_rate: 16_000,
        channels: 1,
    })
}

/// The richer return value of `stop_recording`.
///
/// Existing callers (Whispr meeting capture) read `CaptureState` fields via
/// TypeScript destructuring and simply ignore the new `companion_recording`
/// field — it is always `null` for non-mic-only sessions.  The Companion
/// caller reads `companion_recording` to obtain the WAV path and duration.
#[derive(Clone, Serialize)]
struct StopRecordingResult {
    // CaptureState fields (flattened so existing TS callers keep working).
    is_capturing: bool,
    device_name: Option<String>,
    sample_rate: u32,
    system_audio_active: bool,
    mic_samples_total: u64,
    sys_samples_total: u64,
    /// Populated only when the session was started with `mic_only: true`.
    companion_recording: Option<CompanionRecording>,
}

impl StopRecordingResult {
    fn from_capture_state(state: CaptureState) -> Self {
        Self {
            is_capturing: state.is_capturing,
            device_name: state.device_name,
            sample_rate: state.sample_rate,
            system_audio_active: state.system_audio_active,
            mic_samples_total: state.mic_samples_total,
            sys_samples_total: state.sys_samples_total,
            companion_recording: None,
        }
    }
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
    eprintln!(
        "[audio-capture] start_recording invoked; config={:?}",
        config
    );
    let state = app.state::<Mutex<AudioCaptureState>>();
    {
        let guard = state
            .lock()
            .map_err(|e| format!("Failed to lock state: {}", e))?;
        if guard.handle.is_some() {
            eprintln!("[audio-capture] start_recording ABORT: capture already running");
            return Err("Capture is already running".to_string());
        }
    }

    let config = config.unwrap_or_default();
    let mic_only = config.mic_only;
    eprintln!(
        "[audio-capture] mic_only={} sample_rate={} channels={}",
        mic_only, config.sample_rate, config.channels
    );

    // -----------------------------------------------------------------------
    // Companion PTT fast path — mic-only, no ScreenCaptureKit, no Deepgram.
    // -----------------------------------------------------------------------
    if mic_only {
        let (mic_tx, mic_rx) = mpsc::unbounded_channel::<Vec<i16>>();

        // Force mono 16 kHz (Gemini's preferred inline_data format).
        let mic_config = CaptureConfig {
            sample_rate: 16_000,
            channels: 1,
            device_id: config.device_id.clone(),
            mic_only: true,
            ..CaptureConfig::default()
        };
        let handle = capture::start_capture(mic_config, mic_tx)?;

        // Write to <app_data_dir>/companion/recordings/<uuid>.wav.
        // The frontend owns cleanup after consuming the WAV.
        let wav_path = match app.path().app_data_dir() {
            Ok(dir) => {
                let uuid = uuid::Uuid::new_v4().to_string();
                dir.join("companion")
                    .join("recordings")
                    .join(format!("{}.wav", uuid))
                    .display()
                    .to_string()
            }
            Err(e) => {
                tracing::warn!("[companion] app_data_dir unavailable: {}", e);
                let uuid = uuid::Uuid::new_v4().to_string();
                std::env::temp_dir()
                    .join(format!("companion_{}.wav", uuid))
                    .display()
                    .to_string()
            }
        };

        let wav_writer = MonoAudioFileWriter::create(std::path::Path::new(&wav_path))
            .map_err(|e| format!("companion WAV writer failed: {}", e))?;

        let capture_state = CaptureState {
            is_capturing: true,
            device_name: Some(handle.device_name.clone()),
            sample_rate: handle.sample_rate,
            system_audio_active: false,
            mic_samples_total: 0,
            sys_samples_total: 0,
        };

        let cancel = CancellationToken::new();
        let companion_consumer = tokio::spawn(run_companion_consumer(
            mic_rx,
            cancel.clone(),
            wav_writer,
            wav_path.clone(),
        ));

        tracing::info!(
            "[companion] mic-only recording started: device={}, path={}",
            handle.device_name,
            wav_path
        );

        {
            let mut guard = state
                .lock()
                .map_err(|e| format!("Failed to lock state: {}", e))?;
            guard.handle = Some(handle);
            guard.cancel = Some(cancel);
            guard.companion_consumer = Some(companion_consumer);
            guard.companion_wav_path = Some(wav_path);
        }

        return Ok(capture_state);
    }

    // -----------------------------------------------------------------------
    // Meeting-capture path (unchanged).
    // -----------------------------------------------------------------------
    let language = config.language.clone();
    let want_system_audio = config.capture_system_audio;
    let skip_live = config.skip_live_transcription;
    let (mic_tx, mic_rx) = mpsc::unbounded_channel::<Vec<i16>>();

    let handle = capture::start_capture(config, mic_tx)?;

    // Try to start system-audio capture. Failure is not fatal — we fall
    // back to mic-only and log a warning. macOS Core Audio Taps require
    // 14.4+, so this will cleanly fail on older systems. Run the setup
    // on a blocking thread with a generous timeout so a first-time TCC
    // prompt has time to be answered, and a hung Core Audio / TCC IPC
    // can never freeze the mic-start path indefinitely.
    let (sys_rx, sys_handle) = if want_system_audio {
        let fut = tokio::task::spawn_blocking(start_system_audio_capture);
        match tokio::time::timeout(std::time::Duration::from_secs(15), fut).await {
            Ok(Ok(Ok((rx, h)))) => {
                tracing::info!("[audio-capture] system-audio capture started");
                (Some(rx), Some(h))
            }
            Ok(Ok(Err(e))) => {
                tracing::warn!(
                    "[audio-capture] system-audio capture unavailable (falling back to mic-only). \
                     Grant 'Audio Capture' permission in System Settings → Privacy & Security if \
                     you expect this to work. Error: {}",
                    e
                );
                (None, None)
            }
            Ok(Err(join_err)) => {
                tracing::warn!(
                    "[audio-capture] system-audio setup task panicked, falling back to mic-only: {}",
                    join_err
                );
                (None, None)
            }
            Err(_) => {
                tracing::warn!(
                    "[audio-capture] system-audio setup timed out after 15s (TCC prompt \
                     unanswered?), falling back to mic-only"
                );
                (None, None)
            }
        }
    } else {
        (None, None)
    };

    let capture_state = CaptureState {
        is_capturing: true,
        device_name: Some(handle.device_name.clone()),
        sample_rate: handle.sample_rate,
        system_audio_active: sys_handle.is_some(),
        mic_samples_total: 0,
        sys_samples_total: 0,
    };

    let id_token = read_id_token(&app).unwrap_or_default();
    if id_token.is_empty() {
        tracing::warn!("[audio-capture] no id_token in store — recording without transcription");
    }

    // Clone the storage handle out of managed state (cheap — Arc) and open a
    // DB row for this session so segments can be appended as they arrive.
    let storage = {
        let guard = state
            .lock()
            .map_err(|e| format!("Failed to lock state: {}", e))?;
        guard.storage.clone()
    };
    let timezone = iana_time_zone::get_timezone().unwrap_or_else(|_| "UTC".to_string());
    let session_id = storage.as_ref().and_then(|s| {
        match s.start_session(
            "desktop",
            if language.trim().is_empty() { "en" } else { &language },
            &timezone,
            Some(handle.device_name.as_str()),
        ) {
            Ok(id) => {
                tracing::info!("[audio-capture] opened session row id={}", id);
                Some(id)
            }
            Err(e) => {
                tracing::warn!("[audio-capture] start_session failed: {}", e);
                None
            }
        }
    });

    // Open a WAV writer under `<app_data_dir>/transcription/raw/<session_id>.wav`
    // so the mixed-stereo audio is durable even if the live transcription
    // path drops frames. Best-effort: if we don't have a session id or the
    // path isn't resolvable we skip — recording still works, we just lose
    // the post-stop re-process safety net.
    let audio_writer: Option<AudioFileWriter> = match (storage.as_ref(), session_id) {
        (Some(s), Some(sid)) => match app.path().app_data_dir() {
            Ok(dir) => {
                let path = dir
                    .join("transcription")
                    .join("raw")
                    .join(format!("{}.wav", sid));
                match AudioFileWriter::create(&path) {
                    Ok(w) => {
                        let path_str = path.display().to_string();
                        if let Err(e) = s.set_audio_file_path(sid, &path_str) {
                            tracing::warn!(
                                "[audio-capture] set_audio_file_path failed: {}",
                                e
                            );
                        }
                        tracing::info!("[audio-capture] recording audio to {}", path_str);
                        Some(w)
                    }
                    Err(e) => {
                        tracing::warn!("[audio-capture] audio writer create failed: {}", e);
                        None
                    }
                }
            }
            Err(e) => {
                tracing::warn!(
                    "[audio-capture] app_data_dir unavailable — not saving audio file: {}",
                    e
                );
                None
            }
        },
        _ => None,
    };

    let counters = Arc::new(CaptureCounters::default());

    let cancel = CancellationToken::new();
    let device_name = Some(handle.device_name.clone());
    let consumer = tokio::spawn(run_transcription_consumer(
        app.clone(),
        mic_rx,
        sys_rx,
        counters.clone(),
        cancel.clone(),
        id_token,
        device_name,
        language,
        storage,
        session_id,
        audio_writer,
        skip_live,
    ));

    tracing::info!(
        "Recording started: device={}, rate={}, system_audio={}",
        capture_state.device_name.as_deref().unwrap_or("?"),
        capture_state.sample_rate,
        sys_handle.is_some()
    );

    {
        let mut guard = state
            .lock()
            .map_err(|e| format!("Failed to lock state: {}", e))?;
        guard.handle = Some(handle);
        guard.sys_handle = sys_handle;
        guard.consumer = Some(consumer);
        guard.cancel = Some(cancel);
        guard.counters = counters;
        guard.session_id = session_id;
    }

    Ok(capture_state)
}

/// Start system-audio capture on macOS (Core Audio Taps, 14.4+). On other
/// platforms this always errors — callers treat it as a graceful fallback
/// to mic-only, so the error message is user-facing-friendly.
#[cfg(target_os = "macos")]
fn start_system_audio_capture() -> Result<(mpsc::Receiver<Vec<i16>>, SysHandle), String> {
    let (tx, rx) = mpsc::channel::<Vec<i16>>(SYS_AUDIO_CHANNEL_CAPACITY);
    let handle = system_audio_macos::SystemAudioCapture::start(tx)?;
    Ok((rx, handle))
}

#[cfg(not(target_os = "macos"))]
fn start_system_audio_capture() -> Result<(mpsc::Receiver<Vec<i16>>, SysHandle), String> {
    Err("system audio capture is only supported on macOS".into())
}

/// Result of a one-shot diagnostic probe — used by the Settings debug panel.
#[derive(Clone, Serialize)]
pub struct SystemAudioProbe {
    /// Tap creation succeeded (implies TCC + macOS version are OK).
    pub ok: bool,
    /// Platform-tagged description (e.g. "macos-14.4+").
    pub platform: String,
    /// Human-readable outcome — error text on failure, status on success.
    pub message: String,
    /// Samples observed on the tap in the probe window (≈500 ms). `0`
    /// means the tap started but nothing was playing through the speakers.
    pub samples_received: u64,
}

/// Source-format string of the aggregate device at the last probe.
/// Useful for diagnosing "tap delivers zeros" scenarios — tells us what
/// Core Audio thinks the tap is producing (rate, channels, bit depth).
#[cfg(target_os = "macos")]
fn last_tap_format_string() -> Option<String> {
    system_audio_macos::last_tap_format()
        .map(|(rate, ch, bits)| format!("{} Hz / {} ch / {} bits", rate as u32, ch, bits))
}
#[cfg(not(target_os = "macos"))]
fn last_tap_format_string() -> Option<String> {
    None
}

/// Result of the combined mic + system-audio live probe.
#[derive(Clone, Serialize)]
pub struct LiveCaptureProbe {
    pub ok: bool,
    pub duration_ms: u64,
    pub mic_samples: u64,
    pub sys_samples: u64,
    /// RMS amplitude of mic samples (0.0 – 1.0, normalised).
    pub mic_level: f32,
    /// RMS amplitude of sys samples (0.0 – 1.0, normalised).
    pub sys_level: f32,
    /// Peak absolute i16 value observed on the mic channel.
    #[serde(default)]
    pub mic_peak_i16: i32,
    /// Peak absolute i16 value observed on the sys channel.
    #[serde(default)]
    pub sys_peak_i16: i32,
    /// Count of non-zero mic samples — distinguishes "silent" (all 0) from
    /// "very quiet" (all tiny but non-zero values).
    #[serde(default)]
    pub mic_nonzero: u64,
    #[serde(default)]
    pub sys_nonzero: u64,
    /// Whether the Deepgram WS was connected during the probe.
    #[serde(default)]
    pub transcription_connected: bool,
    /// Number of transcript messages received from Deepgram.
    #[serde(default)]
    pub transcript_count: u64,
    /// Source format the aggregate device reports for the tap (macOS).
    #[serde(default)]
    pub sys_source_format: Option<String>,
    /// Raw pre-resample peak (f32 abs) seen in the HAL callback. Non-zero
    /// means Core Audio *is* delivering real audio bytes into our
    /// callback — a later zero in `sys_peak_i16` would then be a bug in
    /// our resampler / conversion. Zero means Core Audio is the culprit.
    #[serde(default)]
    pub sys_raw_peak: f32,
    /// Human-readable summary / error message.
    pub message: String,
}

/// A single transcript line emitted via the `probe:transcript` event so
/// the UI can render mic-vs-sys bubbles during the live capture test.
#[derive(Clone, Serialize)]
struct ProbeTranscriptEvent {
    text: String,
    is_final: bool,
    is_user: bool,
    speaker: String,
    start: f64,
    end: f64,
}

/// Request system-audio capture permission. On macOS, attempting to
/// create a Core Audio Process Tap triggers the TCC prompt (if the
/// binary is properly signed + has `NSScreenCaptureUsageDescription` in
/// its Info.plist). Also opens System Settings → Privacy & Security →
/// Screen & System Audio Recording so the user can toggle the entry
/// manually if the prompt doesn't appear.
#[tauri::command]
async fn request_system_audio_permission() -> Result<SystemAudioProbe, String> {
    // Open System Settings to the Screen & System Audio Recording pane.
    // `-g` launches without activating so it doesn't steal focus.
    let _ = std::process::Command::new("open")
        .arg("x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture")
        .spawn();

    // Run a fresh tap attempt — on first call after a TCC reset this is
    // what surfaces the "wants to record from other apps" prompt.
    probe_system_audio().await
}

/// Start a short-lived system-audio tap, collect samples for ~500 ms, then
/// tear it down. Lets the Settings debug panel confirm whether TCC is
/// granted and whether the tap is actually delivering frames.
#[tauri::command]
async fn probe_system_audio() -> Result<SystemAudioProbe, String> {
    let platform = if cfg!(target_os = "macos") {
        "macos-14.4+".to_string()
    } else {
        std::env::consts::OS.to_string()
    };

    let probe_result = tokio::task::spawn_blocking(move || -> Result<u64, String> {
        let (mut rx, _handle) = start_system_audio_capture()?;
        // Draining for a short window. If the tap is working and audio is
        // playing, we'll see frames; if it's silent, we'll see none but
        // the start itself succeeded (proving TCC is granted).
        let deadline = std::time::Instant::now() + std::time::Duration::from_millis(600);
        let mut samples: u64 = 0;
        while std::time::Instant::now() < deadline {
            match rx.try_recv() {
                Ok(chunk) => samples += chunk.len() as u64,
                Err(tokio::sync::mpsc::error::TryRecvError::Empty) => {
                    std::thread::sleep(std::time::Duration::from_millis(20));
                }
                Err(tokio::sync::mpsc::error::TryRecvError::Disconnected) => break,
            }
        }
        Ok(samples)
        // _handle dropped here → tap is torn down.
    })
    .await
    .map_err(|e| format!("probe task panicked: {}", e))?;

    match probe_result {
        Ok(samples_received) => {
            let message = if samples_received > 0 {
                format!(
                    "OK — received {} samples (~{} ms) during probe",
                    samples_received,
                    samples_received * 1000 / 16_000
                )
            } else {
                "Tap started but no audio was playing — try again while something is \
                 playing through the speakers (YouTube, Music, a call)"
                    .to_string()
            };
            Ok(SystemAudioProbe {
                ok: true,
                platform,
                message,
                samples_received,
            })
        }
        Err(e) => Ok(SystemAudioProbe {
            ok: false,
            platform,
            message: e,
            samples_received: 0,
        }),
    }
}

/// Run a combined mic + system-audio capture for a short window and report
/// per-channel sample counts + average amplitude. Lets the user verify
/// that both sources are delivering audio simultaneously (e.g. play a
/// YouTube video and watch sys_samples tick up alongside mic_samples).
///
/// Refuses to run while the main recording is active — the two would
/// contend for the mic cpal stream.
#[tauri::command]
async fn probe_live_capture<R: Runtime>(
    app: tauri::AppHandle<R>,
    duration_ms: Option<u64>,
) -> Result<LiveCaptureProbe, String> {
    let duration_ms = duration_ms.unwrap_or(5000).clamp(500, 15_000);

    {
        let state = app.state::<Mutex<AudioCaptureState>>();
        let guard = state
            .lock()
            .map_err(|e| format!("Failed to lock state: {}", e))?;
        if guard.handle.is_some() {
            return Err(
                "A recording is already running — stop it first before probing".to_string(),
            );
        }
    }

    // Start mic via the same cpal path used by real recording.
    let (mic_tx, mut mic_rx) = mpsc::unbounded_channel::<Vec<i16>>();
    let mic_handle = capture::start_capture(models::CaptureConfig::default(), mic_tx)
        .map_err(|e| format!("mic start failed: {}", e))?;

    // Start sys capture on a blocking thread with a 3s timeout.
    let sys_result = tokio::time::timeout(
        std::time::Duration::from_secs(3),
        tokio::task::spawn_blocking(start_system_audio_capture),
    )
    .await;
    let (mut sys_rx, _sys_handle) = match sys_result {
        Ok(Ok(Ok((rx, h)))) => (Some(rx), Some(h)),
        Ok(Ok(Err(e))) => {
            drop(mic_handle);
            return Ok(empty_probe_error(format!("system-audio start failed: {}", e)));
        }
        Ok(Err(e)) => {
            drop(mic_handle);
            return Ok(empty_probe_error(format!(
                "system-audio task panicked: {}",
                e
            )));
        }
        Err(_) => {
            drop(mic_handle);
            return Ok(empty_probe_error(
                "system-audio start timed out after 3s".to_string(),
            ));
        }
    };

    // Open a Deepgram WS for the probe. Best-effort — if auth is missing
    // or the backend is unreachable we still run the sample-count probe.
    let id_token = read_id_token(&app).unwrap_or_default();
    let transcript_count = Arc::new(AtomicU64::new(0));
    let stream = if id_token.is_empty() {
        None
    } else {
        let app_for_cb = app.clone();
        let counter = transcript_count.clone();
        let callback: transcription::TranscriptCallback =
            Arc::new(move |live: transcription::LiveTranscript| {
                counter.fetch_add(1, Ordering::Relaxed);
                let _ = app_for_cb.emit(
                    "probe:transcript",
                    ProbeTranscriptEvent {
                        text: live.text,
                        is_final: live.is_final,
                        is_user: live.is_user,
                        speaker: live.speaker,
                        start: live.start,
                        end: live.end,
                    },
                );
            });
        match TranscriptionStream::connect(BACKEND_URL, &id_token, "en", Some(callback)).await {
            Ok(s) => Some(s),
            Err(e) => {
                tracing::warn!("[probe] Deepgram connect failed (probe continues without transcription): {}", e);
                None
            }
        }
    };
    let transcription_connected = stream.is_some();

    let mut vad = VADGateService::new();
    let mut mixer = AudioMixer::new();
    let deadline = tokio::time::Instant::now() + std::time::Duration::from_millis(duration_ms);
    let mut mic_samples: u64 = 0;
    let mut sys_samples: u64 = 0;
    let mut mic_sum_sq: f64 = 0.0;
    let mut sys_sum_sq: f64 = 0.0;
    let mut mic_peak: i32 = 0;
    let mut sys_peak: i32 = 0;
    let mut mic_nonzero: u64 = 0;
    let mut sys_nonzero: u64 = 0;
    let max_val = i16::MAX as f64;

    loop {
        tokio::select! {
            _ = tokio::time::sleep_until(deadline) => break,
            chunk = mic_rx.recv() => {
                let Some(samples) = chunk else { break };
                mic_samples += samples.len() as u64;
                for &s in &samples {
                    let abs = (s as i32).abs();
                    if abs > mic_peak { mic_peak = abs; }
                    if s != 0 { mic_nonzero += 1; }
                    let n = s as f64 / max_val;
                    mic_sum_sq += n * n;
                }
                mixer.push_mic(&samples);
                forward_mixed_to_probe_stream(&mut mixer, &mut vad, stream.as_ref());
            }
            chunk = async {
                match sys_rx.as_mut() {
                    Some(rx) => rx.recv().await,
                    None => std::future::pending().await,
                }
            } => {
                let Some(samples) = chunk else { sys_rx = None; continue };
                sys_samples += samples.len() as u64;
                for &s in &samples {
                    let abs = (s as i32).abs();
                    if abs > sys_peak { sys_peak = abs; }
                    if s != 0 { sys_nonzero += 1; }
                    let n = s as f64 / max_val;
                    sys_sum_sq += n * n;
                }
                mixer.push_sys(&samples);
                forward_mixed_to_probe_stream(&mut mixer, &mut vad, stream.as_ref());
            }
        }
    }

    // Flush any tail, then finalize the WS so Deepgram emits closing
    // partials. Wait briefly for the final `is_final` messages to arrive.
    if let Some(stereo) = mixer.flush() {
        let out = tokio::task::block_in_place(|| vad.process_audio(&stereo));
        if !out.audio_to_send.is_empty() {
            if let Some(s) = stream.as_ref() {
                s.send_audio(out.audio_to_send);
            }
        }
    }
    if let Some(s) = stream {
        let _segments = s.finish().await;
    }
    // Read the raw HAL-callback peak BEFORE tearing down — tells us
    // whether Core Audio actually delivered non-zero bytes.
    #[cfg(target_os = "macos")]
    let sys_raw_peak = _sys_handle
        .as_ref()
        .map(|h| h.raw_peak())
        .unwrap_or(0.0);
    #[cfg(not(target_os = "macos"))]
    let sys_raw_peak = 0.0_f32;
    // Tear down captures.
    drop(mic_handle);
    drop(_sys_handle);

    let mic_level = if mic_samples > 0 {
        (mic_sum_sq / mic_samples as f64).sqrt() as f32
    } else {
        0.0
    };
    let sys_level = if sys_samples > 0 {
        (sys_sum_sq / sys_samples as f64).sqrt() as f32
    } else {
        0.0
    };
    let count = transcript_count.load(Ordering::Relaxed);

    let fmt_str = last_tap_format_string().unwrap_or_else(|| "n/a".into());
    let message = match (mic_samples > 0, sys_samples > 0) {
        (true, true) => format!(
            "mic {} samples peak={} nz={} RMS={:.5}; sys {} samples peak_i16={} raw_peak_f32={:.5} nz={} RMS={:.5}; tap_format=[{}]; {} transcripts",
            mic_samples,
            mic_peak,
            mic_nonzero,
            mic_level,
            sys_samples,
            sys_peak,
            sys_raw_peak,
            sys_nonzero,
            sys_level,
            fmt_str,
            count
        ),
        (true, false) => "Mic delivered audio but system tap produced no frames — is anything \
             actually playing through the speakers?"
            .to_string(),
        (false, true) => "System tap delivered audio but mic produced no frames — check the mic \
             device selection."
            .to_string(),
        (false, false) => "Neither mic nor system tap produced audio during the probe window."
            .to_string(),
    };

    Ok(LiveCaptureProbe {
        ok: mic_samples > 0 && sys_samples > 0 && mic_peak > 0 && sys_peak > 0,
        duration_ms,
        mic_samples,
        sys_samples,
        mic_level,
        sys_level,
        mic_peak_i16: mic_peak,
        sys_peak_i16: sys_peak,
        mic_nonzero,
        sys_nonzero,
        transcription_connected,
        transcript_count: count,
        sys_source_format: last_tap_format_string(),
        sys_raw_peak,
        message,
    })
}

fn empty_probe_error(message: String) -> LiveCaptureProbe {
    LiveCaptureProbe {
        ok: false,
        duration_ms: 0,
        mic_samples: 0,
        sys_samples: 0,
        mic_level: 0.0,
        sys_level: 0.0,
        mic_peak_i16: 0,
        sys_peak_i16: 0,
        mic_nonzero: 0,
        sys_nonzero: 0,
        transcription_connected: false,
        transcript_count: 0,
        sys_source_format: None,
        sys_raw_peak: 0.0,
        message,
    }
}

fn forward_mixed_to_probe_stream(
    mixer: &mut AudioMixer,
    vad: &mut VADGateService,
    stream: Option<&TranscriptionStream>,
) {
    while let Some(stereo) = mixer.drain_stereo() {
        let out = vad.process_audio(&stereo);
        if out.audio_to_send.is_empty() {
            continue;
        }
        if let Some(s) = stream {
            s.send_audio(out.audio_to_send);
        }
    }
}

/// Stop the active recording.
///
/// For meeting-capture sessions (the existing path): waits for the consumer
/// task to finish the Deepgram WS, persist the final segments, and POST the
/// conversation to the backend before returning — so the caller's follow-up
/// `loadConversations()` sees the new meeting instead of racing the upload.
///
/// For Companion mic-only sessions (`mic_only: true`): finalizes the WAV file
/// and returns a `StopRecordingResult` where `companion_recording` is
/// populated with the WAV path, duration, sample rate, and channel count so
/// the caller can send the file to Gemini immediately.
///
/// Existing callers that only read `CaptureState` fields are unaffected —
/// `companion_recording` will be `null` for meeting-capture sessions.
#[tauri::command]
async fn stop_recording<R: Runtime>(
    app: tauri::AppHandle<R>,
) -> Result<StopRecordingResult, String> {
    eprintln!("[audio-capture] stop_recording invoked");
    let state = app.state::<Mutex<AudioCaptureState>>();
    let (consumer, companion_consumer) = {
        let mut guard = state
            .lock()
            .map_err(|e| format!("Failed to lock state: {}", e))?;

        if guard.handle.is_none() {
            eprintln!("[audio-capture] stop_recording ABORT: no capture running");
            return Err("No capture is running".to_string());
        }
        eprintln!(
            "[audio-capture] stop_recording: handle=Some companion_consumer={}",
            guard.companion_consumer.is_some()
        );

        // Dropping the handle stops the cpal stream and closes the channel.
        guard.handle = None;
        // Drop the system-audio handle too — its Drop impl detaches teardown
        // to a background thread so this returns fast even if Core Audio IPC
        // blocks briefly.
        guard.sys_handle = None;
        if let Some(c) = guard.cancel.take() {
            c.cancel();
        }
        guard.session_id = None;
        guard.companion_wav_path = None;
        (guard.consumer.take(), guard.companion_consumer.take())
    };

    // -----------------------------------------------------------------------
    // Companion fast path — return WAV metadata synchronously.
    // -----------------------------------------------------------------------
    if let Some(task) = companion_consumer {
        eprintln!("[audio-capture] awaiting companion_consumer task...");
        let companion_recording = match task.await {
            Ok(Ok(rec)) => {
                eprintln!(
                    "[audio-capture] consumer OK: wav={} duration={}ms samples=?",
                    rec.wav_path, rec.duration_ms
                );
                rec
            }
            Ok(Err(e)) => {
                eprintln!("[audio-capture] consumer ERR: WAV finalize failed: {}", e);
                return Err(e);
            }
            Err(join_err) => {
                eprintln!("[audio-capture] consumer PANIC: {}", join_err);
                return Err(format!("companion consumer panicked: {}", join_err));
            }
        };
        eprintln!(
            "[audio-capture] returning StopRecordingResult with companion_recording"
        );
        return Ok(StopRecordingResult {
            is_capturing: false,
            device_name: None,
            sample_rate: companion_recording.sample_rate as u32,
            system_audio_active: false,
            mic_samples_total: 0,
            sys_samples_total: 0,
            companion_recording: Some(companion_recording),
        });
    }

    // -----------------------------------------------------------------------
    // Meeting-capture path — await WS + POST as before.
    // -----------------------------------------------------------------------
    // Await the consumer OUTSIDE the mutex — it awaits the WS finish + POST,
    // which can take a couple of seconds, and we must not hold the state
    // lock across that await (would deadlock concurrent `get_capture_state`).
    if let Some(task) = consumer {
        match task.await {
            Ok(Ok(())) => {
                tracing::info!("Recording stopped — conversation saved");
            }
            Ok(Err(e)) => {
                // Consumer ran to completion but the POST (or empty-segment
                // check) reported an error. The retry service will pick it
                // up; surface the error so the UI can show a toast.
                tracing::warn!("Recording stopped — save failed: {}", e);
                return Err(e);
            }
            Err(join_err) => {
                tracing::error!("Recording stopped — consumer panicked: {}", join_err);
                return Err(format!("consumer task panicked: {}", join_err));
            }
        }
    } else {
        tracing::info!("Recording stopped (no consumer task)");
    }

    Ok(StopRecordingResult::from_capture_state(CaptureState::default()))
}

/// List all local sessions (recording, pending_upload, uploading, completed,
/// failed) so the UI can render local-only meetings alongside backend rows.
#[tauri::command]
fn list_local_sessions<R: Runtime>(
    app: tauri::AppHandle<R>,
) -> Result<Vec<LocalSession>, String> {
    let state = app.state::<Mutex<AudioCaptureState>>();
    let storage = {
        let guard = state
            .lock()
            .map_err(|e| format!("Failed to lock state: {}", e))?;
        guard.storage.clone()
    };
    let Some(storage) = storage else {
        return Ok(Vec::new());
    };
    storage
        .list_sessions()
        .map_err(|e| format!("list_sessions: {e}"))
}

/// Return the finalized segments attached to a local session.
#[tauri::command]
fn get_local_segments<R: Runtime>(
    app: tauri::AppHandle<R>,
    session_id: i64,
) -> Result<Vec<LocalSegment>, String> {
    let state = app.state::<Mutex<AudioCaptureState>>();
    let storage = {
        let guard = state
            .lock()
            .map_err(|e| format!("Failed to lock state: {}", e))?;
        guard.storage.clone()
    };
    let Some(storage) = storage else {
        return Ok(Vec::new());
    };
    storage
        .get_segments(session_id)
        .map_err(|e| format!("get_segments: {e}"))
}

/// User-triggered retry for a failed / pending session — bypasses backoff.
#[tauri::command]
async fn retry_sync_now<R: Runtime>(
    app: tauri::AppHandle<R>,
    session_id: i64,
) -> Result<(), String> {
    let storage = {
        let state = app.state::<Mutex<AudioCaptureState>>();
        let guard = state
            .lock()
            .map_err(|e| format!("Failed to lock state: {}", e))?;
        guard
            .storage
            .clone()
            .ok_or_else(|| "storage not initialised".to_string())?
    };
    retry::retry_one(&storage, &app, session_id).await
}

/// Delete a local session (and cascade its segments).
#[tauri::command]
fn delete_local_session<R: Runtime>(
    app: tauri::AppHandle<R>,
    session_id: i64,
) -> Result<(), String> {
    let state = app.state::<Mutex<AudioCaptureState>>();
    let storage = {
        let guard = state
            .lock()
            .map_err(|e| format!("Failed to lock state: {}", e))?;
        guard
            .storage
            .clone()
            .ok_or_else(|| "storage not initialised".to_string())?
    };
    storage
        .delete_session(session_id)
        .map_err(|e| format!("delete_session: {e}"))
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
            system_audio_active: guard.sys_handle.is_some(),
            mic_samples_total: guard.counters.mic_samples.load(Ordering::Relaxed),
            sys_samples_total: guard.counters.sys_samples.load(Ordering::Relaxed),
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
            probe_system_audio,
            probe_live_capture,
            request_system_audio_permission,
            list_local_sessions,
            get_local_segments,
            retry_sync_now,
            delete_local_session,
        ])
        .setup(|app, _api| {
            // Try to open the local SQLite store. If this fails the plugin
            // still works — we just lose the persist-then-POST safety net
            // (recording + live transcription keep working).
            let storage = match app.path().app_data_dir() {
                Ok(dir) => match TranscriptionStorage::init(&dir) {
                    Ok(s) => {
                        let arc = Arc::new(s);
                        // Start the retry service so pending / failed
                        // sessions get reconciled in the background.
                        let svc = TranscriptionRetryService::start(arc.clone(), app.clone());
                        // Hold the service for the lifetime of the app so
                        // its cancel token isn't dropped (which would stop
                        // the loop).
                        app.manage(svc);
                        Some(arc)
                    }
                    Err(e) => {
                        tracing::error!(
                            "[audio-capture] TranscriptionStorage init failed \
                             (running without local persistence): {}",
                            e
                        );
                        None
                    }
                },
                Err(e) => {
                    tracing::error!(
                        "[audio-capture] app_data_dir unavailable \
                         (running without local persistence): {}",
                        e
                    );
                    None
                }
            };

            let mut state = AudioCaptureState::default();
            state.storage = storage;
            app.manage(Mutex::new(state));
            tracing::info!("Audio capture plugin initialised");
            Ok(())
        })
        .build()
}
