//! Dedicated floating notification window.
//!
//! Separate from the chat floating bar (`commands::floating`) so notifications
//! never interrupt or clobber an in-progress chat/PTT session. The window
//! lives at `?window=notifications` and renders
//! `src/components/notifications/NotificationBar.tsx`.
//!
//! Delivery model: Rust stashes a payload in `PENDING` and shows the window.
//! The webview polls `notifications_poll` every ~250 ms and picks up the
//! payload via `.take()`. Tauri's event bus was flaky for this case on Linux
//! (see note in `commands::floating`), so polling keeps this simple.

use std::sync::Mutex;

use tauri::{command, AppHandle, LogicalSize, Manager, PhysicalPosition};

pub const NOTIFICATIONS_LABEL: &str = "notifications";
const TOP_MARGIN: f64 = 20.0;
const RIGHT_MARGIN: f64 = 20.0;
pub const DEFAULT_WIDTH: f64 = 380.0;

#[derive(serde::Serialize, serde::Deserialize, Clone, Debug)]
pub struct NotificationPayload {
    pub title: String,
    pub body: String,
    #[serde(rename = "autoHideMs", skip_serializing_if = "Option::is_none")]
    pub auto_hide_ms: Option<u64>,
}

static PENDING: Mutex<Option<NotificationPayload>> = Mutex::new(None);

fn anchor_top_right(app: &AppHandle, width: f64) -> Option<PhysicalPosition<i32>> {
    let window = app.get_webview_window(NOTIFICATIONS_LABEL)?;
    let monitor = window
        .current_monitor()
        .ok()
        .flatten()
        .or_else(|| app.primary_monitor().ok().flatten())?;

    let scale = monitor.scale_factor();
    let size = monitor.size();
    let pos = monitor.position();

    let monitor_width_logical = size.width as f64 / scale;
    let x_logical = monitor_width_logical - width - RIGHT_MARGIN;

    let x_physical = pos.x + (x_logical * scale).round() as i32;
    let y_physical = pos.y + (TOP_MARGIN * scale).round() as i32;

    Some(PhysicalPosition::new(x_physical, y_physical))
}

#[command]
pub async fn show_notification_alert(
    app: AppHandle,
    title: String,
    body: String,
    auto_hide_ms: Option<u64>,
) -> Result<(), String> {
    let payload = NotificationPayload { title, body, auto_hide_ms };

    if let Ok(mut guard) = PENDING.lock() {
        *guard = Some(payload);
    }

    let window = app
        .get_webview_window(NOTIFICATIONS_LABEL)
        .ok_or_else(|| format!("notification window '{}' not found", NOTIFICATIONS_LABEL))?;

    if let Some(pos) = anchor_top_right(&app, DEFAULT_WIDTH) {
        let _ = window.set_position(pos);
    }

    window.show().map_err(|e| e.to_string())?;
    let _ = window.set_always_on_top(true);

    Ok(())
}

#[command]
pub async fn hide_notification_bar(app: AppHandle) -> Result<(), String> {
    if let Some(window) = app.get_webview_window(NOTIFICATIONS_LABEL) {
        window.hide().map_err(|e| e.to_string())?;
    }
    Ok(())
}

#[command]
pub async fn resize_notification_bar(app: AppHandle, height: f64) -> Result<(), String> {
    let window = app
        .get_webview_window(NOTIFICATIONS_LABEL)
        .ok_or_else(|| "notification window not found".to_string())?;

    let clamped = height.clamp(40.0, 400.0);
    window
        .set_size(LogicalSize::new(DEFAULT_WIDTH, clamped))
        .map_err(|e| e.to_string())?;

    if let Some(pos) = anchor_top_right(&app, DEFAULT_WIDTH) {
        let _ = window.set_position(pos);
    }

    Ok(())
}

/// Polled by the notification webview every ~250 ms. Returns any pending
/// payload and clears it atomically.
#[command]
pub async fn notifications_poll() -> Result<Option<NotificationPayload>, String> {
    let pending = PENDING.lock().ok().and_then(|mut g| g.take());
    Ok(pending)
}
