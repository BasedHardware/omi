//! Onboarding shortcut capture.
//!
//! The PTT module owns the only `rdev` listener in the process (rdev only
//! supports one `listen` call per platform). This module piggy-backs on that
//! listener: when the frontend arms capture via `start_shortcut_capture`,
//! the PTT callback forwards each key press/release here, and we emit
//! `onboarding:shortcut_key` Tauri events the React side translates into a
//! key-cap visualization and a stored chord.
//!
//! `stop_shortcut_capture` disarms; the listener falls back to no-op for the
//! onboarding side (PTT continues normally).

use std::sync::OnceLock;
use std::sync::atomic::{AtomicBool, Ordering};

use rdev::Key;
use serde::Serialize;
use tauri::{AppHandle, Emitter};

static ARMED: AtomicBool = AtomicBool::new(false);
static APP: OnceLock<AppHandle> = OnceLock::new();

#[derive(Serialize, Clone)]
pub struct ShortcutKeyEvent {
    /// "press" or "release"
    pub kind: &'static str,
    /// Normalized key label, e.g. "Cmd", "Shift", "Space", "A".
    pub label: String,
    /// rdev's debug name for the key, useful for diagnostics.
    pub raw: String,
}

pub fn set_app(app: AppHandle) {
    let _ = APP.set(app);
}

/// Called by the PTT listener for every key event. No-op when capture is
/// disarmed so the hot path stays cheap.
pub fn record_key(kind: &'static str, key: Key) {
    if !ARMED.load(Ordering::SeqCst) {
        return;
    }
    let app = match APP.get() {
        Some(a) => a,
        None => return,
    };
    let label = normalize(key);
    let payload = ShortcutKeyEvent {
        kind,
        label,
        raw: format!("{:?}", key),
    };
    let _ = app.emit("onboarding:shortcut_key", payload);
}

/// Normalize rdev keys to the user-facing labels Swift uses (Cmd/Ctrl/Shift/
/// Option/Space/letters/digits/F-keys). Unknown keys fall back to their
/// debug name so the user still sees something.
fn normalize(key: Key) -> String {
    let s = match key {
        Key::MetaLeft | Key::MetaRight => {
            if cfg!(target_os = "macos") {
                "Cmd"
            } else {
                "Win"
            }
        }
        Key::ControlLeft | Key::ControlRight => "Ctrl",
        Key::ShiftLeft | Key::ShiftRight => "Shift",
        Key::Alt => {
            if cfg!(target_os = "macos") {
                "Option"
            } else {
                "Alt"
            }
        }
        Key::AltGr => "Right Option",
        Key::Function => "Fn",
        Key::Space => "Space",
        Key::Return => "Return",
        Key::Tab => "Tab",
        Key::Escape => "Esc",
        Key::Backspace => "Backspace",
        Key::CapsLock => "CapsLock",
        Key::UpArrow => "↑",
        Key::DownArrow => "↓",
        Key::LeftArrow => "←",
        Key::RightArrow => "→",
        Key::F1 => "F1",
        Key::F2 => "F2",
        Key::F3 => "F3",
        Key::F4 => "F4",
        Key::F5 => "F5",
        Key::F6 => "F6",
        Key::F7 => "F7",
        Key::F8 => "F8",
        Key::F9 => "F9",
        Key::F10 => "F10",
        Key::F11 => "F11",
        Key::F12 => "F12",
        Key::KeyA => "A",
        Key::KeyB => "B",
        Key::KeyC => "C",
        Key::KeyD => "D",
        Key::KeyE => "E",
        Key::KeyF => "F",
        Key::KeyG => "G",
        Key::KeyH => "H",
        Key::KeyI => "I",
        Key::KeyJ => "J",
        Key::KeyK => "K",
        Key::KeyL => "L",
        Key::KeyM => "M",
        Key::KeyN => "N",
        Key::KeyO => "O",
        Key::KeyP => "P",
        Key::KeyQ => "Q",
        Key::KeyR => "R",
        Key::KeyS => "S",
        Key::KeyT => "T",
        Key::KeyU => "U",
        Key::KeyV => "V",
        Key::KeyW => "W",
        Key::KeyX => "X",
        Key::KeyY => "Y",
        Key::KeyZ => "Z",
        Key::Num0 => "0",
        Key::Num1 => "1",
        Key::Num2 => "2",
        Key::Num3 => "3",
        Key::Num4 => "4",
        Key::Num5 => "5",
        Key::Num6 => "6",
        Key::Num7 => "7",
        Key::Num8 => "8",
        Key::Num9 => "9",
        _ => {
            return format!("{:?}", key);
        }
    };
    s.to_string()
}

#[tauri::command]
pub fn start_shortcut_capture(app: AppHandle) -> Result<(), String> {
    set_app(app);
    ARMED.store(true, Ordering::SeqCst);
    Ok(())
}

#[tauri::command]
pub fn stop_shortcut_capture() -> Result<(), String> {
    ARMED.store(false, Ordering::SeqCst);
    Ok(())
}
