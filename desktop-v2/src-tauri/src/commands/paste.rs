//! Clipboard delivery for the Whispr transcript.
//!
//! We used to try simulating Cmd+V via enigo to auto-paste into the focused
//! app. On dev builds that's unreliable — every rebuild changes the binary
//! signature, and macOS revokes Accessibility (silently) for keystroke
//! synthesis. The CGEvent calls then SIGABRT-crash the entire process before
//! `catch_unwind` can catch them, which means the user not only loses the
//! auto-paste but the app itself dies right after the transcription.
//!
//! Trade-off chosen: drop auto-paste, guarantee the clipboard write. The
//! transcript is always on the clipboard within milliseconds of stop_recording
//! returning; the user presses Cmd+V manually wherever they want it. This is
//! one extra keystroke per Whispr session in exchange for never losing a
//! transcript and never crashing. The previous-clipboard restore was already
//! out of scope (we don't snapshot it), so functionally the user gets the
//! same outcome — the transcript on the clipboard, ready to paste.
//!
//! If we ever want auto-paste back, the right path is a tiny separate
//! signed helper binary that we shell out to (like the Swift speech-helper
//! sidecar pattern). That isolates the unreliable CGEvent at process level
//! so a crash there can't take the main app down.

use tauri::command;

#[command]
pub async fn paste_transcript(text: String) -> Result<(), String> {
    if text.trim().is_empty() {
        eprintln!("[paste] paste_transcript: empty text — skipping");
        return Ok(());
    }
    eprintln!(
        "[paste] paste_transcript: {} chars on clipboard, preview {:?}",
        text.chars().count(),
        text.chars().take(60).collect::<String>()
    );

    let mut cb = arboard::Clipboard::new().map_err(|e| format!("clipboard: {e}"))?;
    cb.set_text(text).map_err(|e| format!("clipboard set: {e}"))?;
    eprintln!("[paste] clipboard set OK — press Cmd+V to paste");
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
