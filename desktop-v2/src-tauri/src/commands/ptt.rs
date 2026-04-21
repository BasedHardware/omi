//! Push-to-talk: hold AltGr (or right Alt) to dictate.
//!
//! Runs an `rdev` listener on a dedicated OS thread. When the user presses
//! and holds the PTT key, we emit `ptt:start`; on release we emit `ptt:stop`.
//! The frontend handles the rest — showing the floating bar, driving the
//! audio plugin, writing the transcript to the clipboard, and pasting.
//!
//! macOS needs Accessibility permission for `rdev` to receive global key
//! events. If permission is missing, `rdev::listen` returns an error; we
//! log it and the listener exits gracefully — the rest of the app keeps
//! working.

use std::sync::OnceLock;
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::Instant;

use rdev::{listen, Event, EventType, Key};
use tauri::{AppHandle, Emitter};

use super::shortcut_capture;

static LISTENER_STARTED: OnceLock<()> = OnceLock::new();
static PTT_DOWN: AtomicBool = AtomicBool::new(false);
static IS_ACTIVE: AtomicBool = AtomicBool::new(false);

// Diagnostics state — updated by the listener thread, read by the
// `ptt_diagnostics` command so the settings page can surface it.
static LISTENER_THREAD_STARTED: AtomicBool = AtomicBool::new(false);
static LISTENER_FAILED: AtomicBool = AtomicBool::new(false);
static LISTENER_ERROR: OnceLock<std::sync::Mutex<Option<String>>> = OnceLock::new();
static LAST_KEY: OnceLock<std::sync::Mutex<Option<String>>> = OnceLock::new();
static KEY_COUNT: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
static PTT_START_COUNT: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
static PTT_STOP_COUNT: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);

fn set_last_key(label: String) {
    let slot = LAST_KEY.get_or_init(|| std::sync::Mutex::new(None));
    if let Ok(mut guard) = slot.lock() {
        *guard = Some(label);
    }
}

fn set_listener_error(msg: String) {
    let slot = LISTENER_ERROR.get_or_init(|| std::sync::Mutex::new(None));
    if let Ok(mut guard) = slot.lock() {
        *guard = Some(msg);
    }
}

/// Is this the PTT key? AltGr only. rdev exposes left Alt as `Key::Alt`
/// and right Alt / AltGr as `Key::AltGr` — matching only the latter
/// prevents the normal Alt+Tab / menu shortcut from triggering dictation.
fn is_ptt_key(key: Key) -> bool {
    matches!(key, Key::AltGr)
}

pub fn start_listener(app: AppHandle) {
    eprintln!("[ptt] start_listener called");
    if LISTENER_STARTED.set(()).is_err() {
        eprintln!("[ptt] listener already started, bailing");
        return;
    }

    std::thread::spawn(move || {
        eprintln!("[ptt] rdev listener thread spawned");
        tracing::info!("[ptt] starting rdev listener (AltGr hold → dictate)");
        LISTENER_THREAD_STARTED.store(true, Ordering::SeqCst);

        let mut alt_down_at: Option<Instant> = None;
        // Any non-Alt key while Alt is held cancels the gesture (so
        // Alt+Tab, AltGr+e, etc. don't trigger PTT).
        let mut chord_detected = false;

        let app_for_cb = app.clone();
        let cb = move |event: Event| match event.event_type {
            EventType::KeyPress(key) => {
                // Onboarding shortcut capture piggy-backs on this listener so
                // we don't need a second `rdev::listen` (which conflicts on
                // every platform). No-op when capture isn't armed.
                shortcut_capture::record_key("press", key);
                eprintln!(
                    "[ptt] keypress {:?} is_ptt_key={} ptt_down={} is_active={}",
                    key,
                    is_ptt_key(key),
                    PTT_DOWN.load(Ordering::SeqCst),
                    IS_ACTIVE.load(Ordering::SeqCst),
                );
                KEY_COUNT.fetch_add(1, Ordering::Relaxed);
                set_last_key(format!("press {:?}", key));
                if is_ptt_key(key) {
                    eprintln!("[ptt] is PTT key — swap PTT_DOWN");
                    if !PTT_DOWN.swap(true, Ordering::SeqCst) {
                        eprintln!("[ptt] firing ptt:start");
                        alt_down_at = Some(Instant::now());
                        chord_detected = false;
                        IS_ACTIVE.store(true, Ordering::SeqCst);
                        PTT_START_COUNT.fetch_add(1, Ordering::Relaxed);
                        match app_for_cb.emit("ptt:start", ()) {
                            Ok(()) => eprintln!("[ptt] emit ptt:start OK"),
                            Err(e) => eprintln!("[ptt] emit ptt:start FAILED: {}", e),
                        }
                    } else {
                        eprintln!("[ptt] PTT already down, skipping");
                    }
                } else if PTT_DOWN.load(Ordering::SeqCst) && !chord_detected {
                    // Another key pressed while PTT is held — this is a
                    // shortcut chord (e.g. AltGr+e for é). Cancel the
                    // dictation session so we don't eat the user's accent.
                    chord_detected = true;
                    if IS_ACTIVE.swap(false, Ordering::SeqCst) {
                        tracing::info!("[ptt] chord detected, cancelling dictation");
                        let _ = app_for_cb.emit("ptt:stop", ());
                    }
                }
            }
            EventType::KeyRelease(key) => {
                eprintln!("[ptt] keyrelease {:?}", key);
                set_last_key(format!("release {:?}", key));
                shortcut_capture::record_key("release", key);
                if is_ptt_key(key) {
                    eprintln!("[ptt] PTT key released, firing ptt:stop");
                    PTT_DOWN.store(false, Ordering::SeqCst);
                    let _ = alt_down_at.take();
                    if IS_ACTIVE.swap(false, Ordering::SeqCst) {
                        PTT_STOP_COUNT.fetch_add(1, Ordering::Relaxed);
                        if let Err(e) = app_for_cb.emit("ptt:stop", ()) {
                            tracing::warn!("[ptt] emit ptt:stop failed: {}", e);
                        }
                    }
                    chord_detected = false;
                }
            }
            _ => {}
        };

        eprintln!("[ptt] calling rdev::listen...");
        if let Err(e) = listen(cb) {
            let msg = format!("{:?}", e);
            eprintln!("[ptt] rdev listener FAILED: {}", msg);
            tracing::error!(
                "[ptt] rdev listener failed (accessibility permission missing?): {}",
                msg
            );
            LISTENER_FAILED.store(true, Ordering::SeqCst);
            set_listener_error(msg);
        } else {
            eprintln!("[ptt] rdev listener exited normally");
            tracing::info!("[ptt] rdev listener exited normally");
        }
    });
}

// ---------------------------------------------------------------------------
// Diagnostics command — surfaced in Settings > Developer
// ---------------------------------------------------------------------------

#[derive(serde::Serialize)]
pub struct PttDiagnostics {
    pub listener_thread_started: bool,
    pub listener_failed: bool,
    pub listener_error: Option<String>,
    pub ptt_down: bool,
    pub is_active: bool,
    pub total_key_events: u64,
    pub ptt_start_count: u64,
    pub ptt_stop_count: u64,
    pub last_key: Option<String>,
}

#[tauri::command]
pub fn ptt_diagnostics() -> PttDiagnostics {
    let listener_error = LISTENER_ERROR
        .get()
        .and_then(|m| m.lock().ok().map(|g| g.clone()))
        .flatten();
    let last_key = LAST_KEY
        .get()
        .and_then(|m| m.lock().ok().map(|g| g.clone()))
        .flatten();
    PttDiagnostics {
        listener_thread_started: LISTENER_THREAD_STARTED.load(Ordering::SeqCst),
        listener_failed: LISTENER_FAILED.load(Ordering::SeqCst),
        listener_error,
        ptt_down: PTT_DOWN.load(Ordering::SeqCst),
        is_active: IS_ACTIVE.load(Ordering::SeqCst),
        total_key_events: KEY_COUNT.load(Ordering::Relaxed),
        ptt_start_count: PTT_START_COUNT.load(Ordering::Relaxed),
        ptt_stop_count: PTT_STOP_COUNT.load(Ordering::Relaxed),
        last_key,
    }
}

/// Fire a synthetic PTT start/stop to exercise the frontend without
/// needing to actually hold AltGr. Useful when rdev is blocked by the OS.
#[tauri::command]
pub async fn ptt_fire_test(app: AppHandle) -> Result<(), String> {
    app.emit("ptt:start", ())
        .map_err(|e| format!("emit start: {e}"))?;
    tokio::time::sleep(std::time::Duration::from_millis(1500)).await;
    app.emit("ptt:stop", ())
        .map_err(|e| format!("emit stop: {e}"))?;
    Ok(())
}
