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

/// True once the rdev listener thread has actually been spawned. Tracks
/// "succeeded" rather than "attempted" so `start_listener` can be retried
/// after the user grants Accessibility during onboarding without restarting.
static LISTENER_SPAWNED: AtomicBool = AtomicBool::new(false);
static PTT_DOWN: AtomicBool = AtomicBool::new(false);
static IS_ACTIVE: AtomicBool = AtomicBool::new(false);

// ---------------------------------------------------------------------------
// Companion key state (independent of Whispr PTT, shares the same rdev listener)
// ---------------------------------------------------------------------------
/// True while the companion key is physically held. Unlike PTT there is no
/// chord-cancellation path for Companion, so a single atomic suffices.
static COMPANION_DOWN: AtomicBool = AtomicBool::new(false);

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

/// User-chosen PTT key set from the frontend via `set_ptt_key` once
/// onboarding completes (or any time via Settings). Defaults to AltGr —
/// rdev exposes right Alt / AltGr as `Key::AltGr`, distinct from left Alt
/// (`Key::Alt`).
static PTT_KEY: std::sync::Mutex<PttKeyLabel> =
    std::sync::Mutex::new(PttKeyLabel::AltGr);

#[derive(Clone, Copy, PartialEq, Eq)]
enum PttKeyLabel {
    // Single-key bindings — fire on the matching keypress / keyrelease.
    Cmd,
    Ctrl,
    Shift,
    RightShift,
    Option,
    AltGr,
    Fn,
    Space,
    Return,
    Tab,
    // Chord bindings — fire when ALL constituent keys are held simultaneously
    // and stop when any one is released. Chord state is tracked via the
    // CMD_DOWN / SHIFT_*_DOWN atomics below.
    CmdShift,
    CmdRightShift,
}

impl PttKeyLabel {
    fn from_label(label: &str) -> Option<Self> {
        match label {
            "Cmd" | "Win" => Some(Self::Cmd),
            "Ctrl" => Some(Self::Ctrl),
            "Shift" => Some(Self::Shift),
            "Right Shift" | "RightShift" => Some(Self::RightShift),
            "Option" | "Alt" => Some(Self::Option),
            "Right Option" | "AltGr" => Some(Self::AltGr),
            "Fn" => Some(Self::Fn),
            "Space" => Some(Self::Space),
            "Return" => Some(Self::Return),
            "Tab" => Some(Self::Tab),
            "Cmd+Shift" | "CmdShift" => Some(Self::CmdShift),
            "Cmd+Right Shift" | "CmdRightShift" => Some(Self::CmdRightShift),
            _ => None,
        }
    }

    fn matches(self, key: Key) -> bool {
        match self {
            Self::Cmd => matches!(key, Key::MetaLeft | Key::MetaRight),
            Self::Ctrl => matches!(key, Key::ControlLeft | Key::ControlRight),
            Self::Shift => matches!(key, Key::ShiftLeft | Key::ShiftRight),
            Self::RightShift => matches!(key, Key::ShiftRight),
            // "Option" = either Option key. macOS labels both as ⌥; rdev
            // splits them into Key::Alt (left) and Key::AltGr (right). Most
            // users mean "either" when they pick Option. The dedicated AltGr
            // variant below is still available for right-only.
            Self::Option => matches!(key, Key::Alt | Key::AltGr),
            Self::AltGr => matches!(key, Key::AltGr),
            Self::Fn => matches!(key, Key::Function),
            Self::Space => matches!(key, Key::Space),
            Self::Return => matches!(key, Key::Return),
            Self::Tab => matches!(key, Key::Tab),
            // Chord variants are NEVER a single-key match — they're handled
            // by the chord-state path that reads the modifier atomics.
            Self::CmdShift | Self::CmdRightShift => false,
        }
    }

    /// True if this variant requires chord-state tracking (multiple keys
    /// must be held simultaneously) rather than a single-key match.
    fn is_chord(self) -> bool {
        matches!(self, Self::CmdShift | Self::CmdRightShift)
    }

    /// For chord variants: are all constituent keys currently held?
    /// For single-key variants: false (they don't use this path).
    fn chord_active(self) -> bool {
        match self {
            Self::CmdShift => {
                CMD_DOWN.load(Ordering::SeqCst)
                    && (SHIFT_LEFT_DOWN.load(Ordering::SeqCst)
                        || SHIFT_RIGHT_DOWN.load(Ordering::SeqCst))
            }
            Self::CmdRightShift => {
                CMD_DOWN.load(Ordering::SeqCst) && SHIFT_RIGHT_DOWN.load(Ordering::SeqCst)
            }
            _ => false,
        }
    }
}

// Modifier-key state atomics — updated on every keypress / keyrelease so
// chord variants can decide whether all required keys are currently held.
static CMD_DOWN: AtomicBool = AtomicBool::new(false);
static SHIFT_LEFT_DOWN: AtomicBool = AtomicBool::new(false);
static SHIFT_RIGHT_DOWN: AtomicBool = AtomicBool::new(false);

fn update_modifier_state(key: Key, down: bool) {
    match key {
        Key::MetaLeft | Key::MetaRight => CMD_DOWN.store(down, Ordering::SeqCst),
        Key::ShiftLeft => SHIFT_LEFT_DOWN.store(down, Ordering::SeqCst),
        Key::ShiftRight => SHIFT_RIGHT_DOWN.store(down, Ordering::SeqCst),
        _ => {}
    }
}

/// Re-evaluate the Companion chord after a modifier key event. Fires
/// `companion:start` / `companion:stop` on chord-state transitions. No-op
/// when the configured Companion key is a single-key variant — those still
/// flow through the per-event `is_companion_key` path.
fn evaluate_companion_chord(app: &AppHandle) {
    let configured = COMPANION_KEY
        .lock()
        .map(|g| *g)
        .unwrap_or(PttKeyLabel::Fn);
    if !configured.is_chord() {
        return;
    }
    let active_now = configured.chord_active();
    let was_down = COMPANION_DOWN.load(Ordering::SeqCst);
    if active_now && !was_down {
        COMPANION_DOWN.store(true, Ordering::SeqCst);
        eprintln!("[ptt] companion chord active — firing companion:start");
        let _ = app.emit("companion:start", ());
    } else if !active_now && was_down {
        COMPANION_DOWN.store(false, Ordering::SeqCst);
        eprintln!("[ptt] companion chord released — firing companion:stop");
        let _ = app.emit("companion:stop", ());
    }
}

// ---------------------------------------------------------------------------
// Shared key-mutation and key-check helpers
// ---------------------------------------------------------------------------

fn write_key_mutex(
    lock: &std::sync::Mutex<PttKeyLabel>,
    label: &str,
    context: &str,
) -> Result<(), String> {
    let parsed = PttKeyLabel::from_label(label)
        .ok_or_else(|| format!("unsupported {} key: {}", context, label))?;
    *lock.lock().map_err(|e| e.to_string())? = parsed;
    Ok(())
}

fn matches_key_mutex(
    lock: &std::sync::Mutex<PttKeyLabel>,
    fallback: PttKeyLabel,
    key: Key,
) -> bool {
    lock.lock().map(|g| *g).unwrap_or(fallback).matches(key)
}

/// Return the human-readable label for the current PTT key (used by the
/// frontend to show which key Whispr is already using).
#[tauri::command]
pub fn get_ptt_key() -> String {
    PTT_KEY
        .lock()
        .map(|g| ptt_key_to_label(*g).to_string())
        .unwrap_or_else(|_| "AltGr".to_string())
}

/// Return the human-readable label for the current Companion PTT key.
#[tauri::command]
pub fn get_companion_key() -> String {
    COMPANION_KEY
        .lock()
        .map(|g| ptt_key_to_label(*g).to_string())
        .unwrap_or_else(|_| "Fn".to_string())
}

fn ptt_key_to_label(key: PttKeyLabel) -> &'static str {
    match key {
        PttKeyLabel::Cmd => "Cmd",
        PttKeyLabel::Ctrl => "Ctrl",
        PttKeyLabel::Shift => "Shift",
        PttKeyLabel::RightShift => "Right Shift",
        PttKeyLabel::Option => "Option",
        PttKeyLabel::AltGr => "AltGr",
        PttKeyLabel::Fn => "Fn",
        PttKeyLabel::Space => "Space",
        PttKeyLabel::Return => "Return",
        PttKeyLabel::Tab => "Tab",
        PttKeyLabel::CmdShift => "Cmd+Shift",
        PttKeyLabel::CmdRightShift => "Cmd+Right Shift",
    }
}

/// Frontend hook: set the key the PTT listener should react to. Accepts a
/// single-key label like "Ctrl", "Option", "Space". Multi-key chords aren't
/// supported yet for PTT — hold gestures must be a single key by design.
///
/// Returns an error if the requested key is already used by the Companion PTT
/// binding — both features would fire on the same key and step on each other.
#[tauri::command]
pub fn set_ptt_key(label: String) -> Result<(), String> {
    let trimmed = label.trim();
    eprintln!("[ptt] set_ptt_key requested: {:?}", trimmed);
    let parsed = PttKeyLabel::from_label(trimmed).ok_or_else(|| {
        let msg = format!("unsupported PTT key: {}", trimmed);
        eprintln!("[ptt] {}", msg);
        msg
    })?;
    // Conflict guard: reject if the companion key already uses this key.
    let companion = COMPANION_KEY.lock().map(|g| *g).unwrap_or(PttKeyLabel::Fn);
    if parsed == companion {
        let msg = format!(
            "Whispr PTT key conflicts with Companion key (both {}). Change one of them first.",
            trimmed
        );
        eprintln!("[ptt] {}", msg);
        return Err(msg);
    }
    let res = write_key_mutex(&PTT_KEY, trimmed, "PTT");
    eprintln!("[ptt] set_ptt_key OK: PTT key = {:?}", trimmed);
    res
}

/// Companion PTT key — default Fn. Independent of the Whispr key.
/// On macOS, rdev delivers `Key::Function` for the Fn key on Apple keyboards.
/// If your layout doesn't produce it, switch to "AltGr" or another key via this command.
static COMPANION_KEY: std::sync::Mutex<PttKeyLabel> =
    std::sync::Mutex::new(PttKeyLabel::Fn);

/// Frontend hook: set the key that triggers Companion (default: "Fn").
///
/// Returns an error if the requested key is already used by the Whispr PTT
/// binding — both features would fire on the same key and step on each other.
#[tauri::command]
pub fn set_companion_key(label: String) -> Result<(), String> {
    let trimmed = label.trim();
    eprintln!("[ptt] set_companion_key requested: {:?}", trimmed);
    let parsed = PttKeyLabel::from_label(trimmed).ok_or_else(|| {
        let msg = format!("unsupported companion key: {}", trimmed);
        eprintln!("[ptt] {} (Rust binary out of date? — restart pnpm tauri:dev:signed)", msg);
        msg
    })?;
    // Conflict guard: reject if the Whispr PTT key already uses this key.
    let whispr = PTT_KEY.lock().map(|g| *g).unwrap_or(PttKeyLabel::AltGr);
    if parsed == whispr {
        let msg = format!(
            "Companion key conflicts with Whispr PTT key (both {}). Change one of them first.",
            trimmed
        );
        eprintln!("[ptt] {}", msg);
        return Err(msg);
    }
    let result = write_key_mutex(&COMPANION_KEY, trimmed, "companion");
    eprintln!("[ptt] set_companion_key OK: companion key = {:?}", trimmed);
    result
}

fn is_ptt_key(key: Key) -> bool {
    matches_key_mutex(&PTT_KEY, PttKeyLabel::AltGr, key)
}

fn is_companion_key(key: Key) -> bool {
    matches_key_mutex(&COMPANION_KEY, PttKeyLabel::Fn, key)
}

#[cfg(target_os = "macos")]
fn accessibility_trusted() -> bool {
    #[link(name = "ApplicationServices", kind = "framework")]
    extern "C" {
        fn AXIsProcessTrusted() -> bool;
    }
    unsafe { AXIsProcessTrusted() }
}

/// Input Monitoring is a distinct TCC scope from Accessibility, and rdev
/// needs it. macOS SIGKILLs the process if an event tap receives keystrokes
/// without it, which cannot be caught from Rust. `IOHIDCheckAccess` is a
/// semi-private IOKit API used for years by Karabiner-Elements and similar
/// tools to probe this exact permission — returns 0 granted, 1 denied,
/// 2 unknown. Anything other than 0 means don't spawn rdev.
#[cfg(target_os = "macos")]
fn input_monitoring_granted() -> bool {
    // kIOHIDRequestTypeListenEvent = 1
    const K_IOHID_REQUEST_TYPE_LISTEN_EVENT: u32 = 1;
    const K_IOHID_ACCESS_TYPE_GRANTED: u32 = 0;
    #[link(name = "IOKit", kind = "framework")]
    extern "C" {
        fn IOHIDCheckAccess(requestType: u32) -> u32;
    }
    let status = unsafe { IOHIDCheckAccess(K_IOHID_REQUEST_TYPE_LISTEN_EVENT) };
    status == K_IOHID_ACCESS_TYPE_GRANTED
}

/// Trigger the Input Monitoring prompt (same mechanism Karabiner uses). If
/// not previously decided, macOS shows the native prompt. Subsequent calls
/// are a no-op — user must toggle the app in System Settings by hand.
#[cfg(target_os = "macos")]
fn request_input_monitoring() {
    const K_IOHID_REQUEST_TYPE_LISTEN_EVENT: u32 = 1;
    #[link(name = "IOKit", kind = "framework")]
    extern "C" {
        fn IOHIDRequestAccess(requestType: u32) -> bool;
    }
    unsafe { IOHIDRequestAccess(K_IOHID_REQUEST_TYPE_LISTEN_EVENT) };
}

pub fn start_listener(app: AppHandle) {
    eprintln!("[ptt] start_listener called");
    if LISTENER_SPAWNED.load(Ordering::SeqCst) {
        eprintln!("[ptt] listener already running, bailing");
        return;
    }

    #[cfg(target_os = "macos")]
    {
        if !accessibility_trusted() {
            eprintln!("[ptt] Accessibility not granted — skipping rdev listener");
            tracing::warn!(
                "[ptt] skipping rdev listener: Accessibility not granted."
            );
            LISTENER_FAILED.store(true, Ordering::SeqCst);
            set_listener_error("Accessibility permission not granted".to_string());
            let _ = app;
            return;
        }
        // Trigger the native prompt if not previously decided, then re-check.
        // Without Input Monitoring the kernel SIGKILLs us on first event —
        // so we bail rather than start a ticking time bomb.
        if !input_monitoring_granted() {
            request_input_monitoring();
            if !input_monitoring_granted() {
                eprintln!("[ptt] Input Monitoring not granted — skipping rdev listener");
                tracing::warn!(
                    "[ptt] skipping rdev listener: Input Monitoring not granted."
                );
                LISTENER_FAILED.store(true, Ordering::SeqCst);
                set_listener_error("Input Monitoring permission not granted".to_string());
                let _ = app;
                return;
            }
        }
    }

    // Clear any prior skip state — we're about to spawn for real.
    LISTENER_FAILED.store(false, Ordering::SeqCst);
    LISTENER_SPAWNED.store(true, Ordering::SeqCst);

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
                KEY_COUNT.fetch_add(1, Ordering::Relaxed);
                set_last_key(format!("press {:?}", key));
                // Track modifier state for chord-mode Companion keys (Cmd+Shift,
                // Cmd+Right Shift). Updated BEFORE the per-key matchers run so
                // the chord evaluator below sees the post-event state.
                update_modifier_state(key, true);
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
                } else if is_companion_key(key) {
                    // Companion key is independent — doesn't cancel Whispr PTT.
                    if !COMPANION_DOWN.swap(true, Ordering::SeqCst) {
                        eprintln!("[ptt] companion key down — firing companion:start");
                        if let Err(e) = app_for_cb.emit("companion:start", ()) {
                            eprintln!("[ptt] emit companion:start FAILED: {}", e);
                        }
                    }
                } else if matches!(key, Key::Escape) {
                    // Esc cancels an in-flight Companion guidance chain. We
                    // don't consume the keystroke (rdev is observation-only),
                    // so existing Esc behavior elsewhere (closing modals,
                    // exiting fullscreen) is unaffected.
                    let _ = app_for_cb.emit("companion:chain-cancel", ());
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
                // Re-check chord state on every keypress. No-op when the
                // configured Companion key is a single-key variant.
                evaluate_companion_chord(&app_for_cb);
            }
            EventType::KeyRelease(key) => {
                set_last_key(format!("release {:?}", key));
                shortcut_capture::record_key("release", key);
                update_modifier_state(key, false);
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
                } else if is_companion_key(key) {
                    if COMPANION_DOWN.swap(false, Ordering::SeqCst) {
                        eprintln!("[ptt] companion key released — firing companion:stop");
                        if let Err(e) = app_for_cb.emit("companion:stop", ()) {
                            tracing::warn!("[ptt] emit companion:stop failed: {}", e);
                        }
                    }
                }
                // Re-check chord state on every keyrelease. Fires
                // companion:stop when the chord becomes incomplete.
                evaluate_companion_chord(&app_for_cb);
            }
            EventType::ButtonPress(_) => {
                // Any global mouse click dismisses the persistent companion
                // pointer (when the "keep pointer until clicked" setting is
                // on). The TS side ignores this event when no pointer is
                // active, so emitting unconditionally is fine.
                let _ = app_for_cb.emit("companion:click-dismiss", ());

                // Also emit the click position so the chain controller can
                // hit-test against the current step's bounds. macOS-only —
                // cg_mouse_location uses Core Graphics. The TS chain
                // controller no-ops when no chain is active.
                #[cfg(target_os = "macos")]
                if let Some((x, y)) = super::companion::cg_mouse_location() {
                    let _ = app_for_cb.emit("companion:click-at", (x, y));
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

/// Called by the frontend after the user grants Accessibility during
/// onboarding — gives the listener another chance to spawn without requiring
/// an app restart. Returns true if the listener is now running.
#[tauri::command]
pub fn ensure_ptt_listener(app: AppHandle) -> bool {
    if LISTENER_SPAWNED.load(Ordering::SeqCst) {
        return true;
    }
    start_listener(app);
    LISTENER_SPAWNED.load(Ordering::SeqCst)
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
