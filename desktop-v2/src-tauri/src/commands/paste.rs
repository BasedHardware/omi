//! Clipboard write + simulated Ctrl+V paste.
//!
//! Called by the frontend at the end of a PTT session to deliver the
//! transcribed text to whichever app was focused before the floating bar
//! took over.
//!
//! Flow:
//!   1. Write the transcript to the system clipboard.
//!   2. Simulate Ctrl+V (Cmd+V on macOS) to paste into the focused app.
//!   3. Leave the transcript on the clipboard.
//!
//! We intentionally do NOT restore the previous clipboard. If the
//! focused window doesn't accept the paste (no text input, wrong
//! field type, permission issue), the user still has the transcript
//! on the clipboard and can paste it manually. This trades preserving
//! the user's previous clipboard for guaranteeing the transcript is
//! never lost — the latter is the promise of a dictation tool.

use enigo::{Enigo, Key, Keyboard, Settings};
use tauri::command;

#[command]
pub async fn paste_transcript(text: String) -> Result<(), String> {
    if text.trim().is_empty() {
        return Ok(());
    }

    let mut cb = arboard::Clipboard::new().map_err(|e| format!("clipboard: {e}"))?;

    // 1. Write the transcript.
    cb.set_text(text)
        .map_err(|e| format!("clipboard set: {e}"))?;

    // 2. Give the OS a beat to settle focus after the Whispr HUD hides.
    tokio::time::sleep(std::time::Duration::from_millis(90)).await;

    // 3. Simulate the paste keystroke. Best-effort: if this fails the
    //    transcript is still on the clipboard.
    let mut enigo = Enigo::new(&Settings::default()).map_err(|e| format!("enigo: {e}"))?;
    let mod_key = if cfg!(target_os = "macos") {
        Key::Meta
    } else {
        Key::Control
    };

    enigo
        .key(mod_key, enigo::Direction::Press)
        .map_err(|e| format!("enigo press mod: {e}"))?;
    enigo
        .key(Key::Unicode('v'), enigo::Direction::Click)
        .map_err(|e| format!("enigo click v: {e}"))?;
    enigo
        .key(mod_key, enigo::Direction::Release)
        .map_err(|e| format!("enigo release mod: {e}"))?;

    Ok(())
}

/// Copy text to clipboard without pasting. Used by the Whispr history
/// page and as a fallback if `paste_transcript`'s keystroke injection
/// fails.
#[command]
pub async fn copy_to_clipboard(text: String) -> Result<(), String> {
    if text.is_empty() {
        return Ok(());
    }
    let mut cb = arboard::Clipboard::new().map_err(|e| format!("clipboard: {e}"))?;
    cb.set_text(text).map_err(|e| format!("clipboard set: {e}"))?;
    Ok(())
}
