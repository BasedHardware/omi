mod capture;
pub mod models;
pub mod vad;

use std::sync::Mutex;

use models::{AudioDevice, CaptureConfig, CaptureState};
use tauri::{
    plugin::{Builder, TauriPlugin},
    Manager, Runtime,
};
use tokio::sync::mpsc;
use tracing;

use capture::CaptureHandle;

/// Plugin-managed state holding the active capture handle and audio receiver.
struct AudioCaptureState {
    handle: Option<CaptureHandle>,
    /// Receiver for audio chunks (available while capturing).
    rx: Option<mpsc::UnboundedReceiver<Vec<i16>>>,
}

impl Default for AudioCaptureState {
    fn default() -> Self {
        Self {
            handle: None,
            rx: None,
        }
    }
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
fn start_recording<R: Runtime>(
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
    let (tx, rx) = mpsc::unbounded_channel::<Vec<i16>>();

    let handle = capture::start_capture(config, tx)?;

    let capture_state = CaptureState {
        is_capturing: true,
        device_name: Some(handle.device_name.clone()),
        sample_rate: handle.sample_rate,
    };

    tracing::info!(
        "Recording started: device={}, rate={}",
        capture_state.device_name.as_deref().unwrap_or("?"),
        capture_state.sample_rate
    );

    guard.handle = Some(handle);
    guard.rx = Some(rx);

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

    // Dropping the handle stops the cpal stream.
    guard.handle = None;
    guard.rx = None;

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
