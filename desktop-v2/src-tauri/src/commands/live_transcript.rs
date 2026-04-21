//! Dedicated floating live-transcript window.
//!
//! Shows while the user is in a meeting so they can see the transcript land
//! even when the main window is minimized. Separate from the chat floating
//! bar (`commands::floating`) and the notification toast
//! (`commands::notifications`) so it can live persistently during the
//! recording without colliding with transient UI.
//!
//! Data flow: the main window listens to the existing
//! `transcript:partial` Tauri event and forwards each payload to
//! `push_live_transcript_segment` below. The floating window polls
//! `poll_live_transcript_segments` every ~250 ms to drain the buffer.
//!
//! Why polling instead of listening directly: on Linux (WebKitGTK),
//! Tauri's `app.emit()` doesn't reliably deliver to freshly-shown
//! auxiliary windows — same issue we hit with the notifications bar and
//! the Whispr HUD (see comment in `commands::floating`). Polling keeps
//! cross-window sync deterministic regardless of webview state.

use std::sync::Mutex;

use tauri::{command, AppHandle, LogicalSize, Manager, PhysicalPosition};

pub const LIVE_TRANSCRIPT_LABEL: &str = "live-transcript";
const BOTTOM_MARGIN: f64 = 20.0;
const RIGHT_MARGIN: f64 = 20.0;
pub const DEFAULT_WIDTH: f64 = 420.0;
pub const DEFAULT_HEIGHT: f64 = 240.0;
const MAX_BUFFERED: usize = 200;

#[derive(serde::Serialize, serde::Deserialize, Clone, Debug)]
pub struct LiveTranscriptSegment {
    pub text: String,
    #[serde(rename = "isFinal")]
    pub is_final: bool,
    pub speaker: String,
    #[serde(rename = "speakerId")]
    pub speaker_id: i64,
    #[serde(rename = "isUser")]
    pub is_user: bool,
    pub start: f64,
    pub end: f64,
}

/// Ring buffer of pending segments the floating window hasn't polled yet.
/// Bounded so a long meeting without the floating window open doesn't
/// leak memory — we'd rather drop ancient partials than pile up forever.
static PENDING: Mutex<Vec<LiveTranscriptSegment>> = Mutex::new(Vec::new());

fn anchor_bottom_right(
    app: &AppHandle,
    width: f64,
    height: f64,
) -> Option<PhysicalPosition<i32>> {
    let window = app.get_webview_window(LIVE_TRANSCRIPT_LABEL)?;
    let monitor = window
        .current_monitor()
        .ok()
        .flatten()
        .or_else(|| app.primary_monitor().ok().flatten())?;

    let scale = monitor.scale_factor();
    let size = monitor.size();
    let pos = monitor.position();

    let monitor_width_logical = size.width as f64 / scale;
    let monitor_height_logical = size.height as f64 / scale;

    let x_logical = monitor_width_logical - width - RIGHT_MARGIN;
    let y_logical = monitor_height_logical - height - BOTTOM_MARGIN;

    let x_physical = pos.x + (x_logical * scale).round() as i32;
    let y_physical = pos.y + (y_logical * scale).round() as i32;

    Some(PhysicalPosition::new(x_physical, y_physical))
}

#[command]
pub async fn show_live_transcript(app: AppHandle) -> Result<(), String> {
    let window = app
        .get_webview_window(LIVE_TRANSCRIPT_LABEL)
        .ok_or_else(|| "live-transcript window not found".to_string())?;

    if let Some(pos) = anchor_bottom_right(&app, DEFAULT_WIDTH, DEFAULT_HEIGHT) {
        let _ = window.set_position(pos);
    }

    window.show().map_err(|e| e.to_string())?;
    let _ = window.set_always_on_top(true);
    Ok(())
}

#[command]
pub async fn hide_live_transcript(app: AppHandle) -> Result<(), String> {
    if let Some(window) = app.get_webview_window(LIVE_TRANSCRIPT_LABEL) {
        window.hide().map_err(|e| e.to_string())?;
    }
    Ok(())
}

#[command]
pub async fn resize_live_transcript(app: AppHandle, height: f64) -> Result<(), String> {
    let window = app
        .get_webview_window(LIVE_TRANSCRIPT_LABEL)
        .ok_or_else(|| "live-transcript window not found".to_string())?;

    let clamped = height.clamp(120.0, 600.0);
    window
        .set_size(LogicalSize::new(DEFAULT_WIDTH, clamped))
        .map_err(|e| e.to_string())?;

    if let Some(pos) = anchor_bottom_right(&app, DEFAULT_WIDTH, clamped) {
        let _ = window.set_position(pos);
    }

    Ok(())
}

/// Called from the main window's `transcript:partial` listener to forward
/// each segment into the shared buffer. The floating window drains it via
/// `poll_live_transcript_segments`.
#[command]
pub async fn push_live_transcript_segment(
    segment: LiveTranscriptSegment,
) -> Result<(), String> {
    if let Ok(mut guard) = PENDING.lock() {
        guard.push(segment);
        // Bound the buffer — if the floating window isn't open, drop the
        // oldest entries so we don't grow unbounded over a long meeting.
        if guard.len() > MAX_BUFFERED {
            let drop_count = guard.len() - MAX_BUFFERED;
            guard.drain(0..drop_count);
        }
    }
    Ok(())
}

/// Polled by the floating window every ~250 ms. Drains and returns all
/// buffered segments atomically.
#[command]
pub async fn poll_live_transcript_segments() -> Result<Vec<LiveTranscriptSegment>, String> {
    let drained = PENDING.lock().ok().map(|mut g| std::mem::take(&mut *g)).unwrap_or_default();
    Ok(drained)
}

/// Called when a new meeting starts so the floating window shows an empty
/// transcript instead of leftover segments from the previous session.
#[command]
pub async fn clear_live_transcript_buffer() -> Result<(), String> {
    if let Ok(mut guard) = PENDING.lock() {
        guard.clear();
    }
    Ok(())
}
