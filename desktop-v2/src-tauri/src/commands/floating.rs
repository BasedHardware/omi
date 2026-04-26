use tauri::{command, AppHandle, Emitter, LogicalSize, Manager, PhysicalPosition};

pub const FLOATING_LABEL: &str = "floating";
const TOP_MARGIN: f64 = 20.0;
pub const DEFAULT_WIDTH: f64 = 500.0;

pub fn anchor_top_center(app: &AppHandle, width: f64) -> Option<PhysicalPosition<i32>> {
    let window = app.get_webview_window(FLOATING_LABEL)?;
    let monitor = window
        .current_monitor()
        .ok()
        .flatten()
        .or_else(|| app.primary_monitor().ok().flatten())?;

    let scale = monitor.scale_factor();
    let size = monitor.size();
    let pos = monitor.position();

    let monitor_width_logical = size.width as f64 / scale;
    let x_logical = (monitor_width_logical - width) / 2.0;

    let x_physical = pos.x + (x_logical * scale).round() as i32;
    let y_physical = pos.y + (TOP_MARGIN * scale).round() as i32;

    Some(PhysicalPosition::new(x_physical, y_physical))
}

#[command]
pub async fn toggle_floating_bar(app: AppHandle) -> Result<(), String> {
    let window = app
        .get_webview_window(FLOATING_LABEL)
        .ok_or_else(|| "floating window not found".to_string())?;

    let visible = window.is_visible().map_err(|e| e.to_string())?;
    if visible {
        window.hide().map_err(|e| e.to_string())?;
        return Ok(());
    }

    if let Some(pos) = anchor_top_center(&app, DEFAULT_WIDTH) {
        let _ = window.set_position(pos);
    }

    window.show().map_err(|e| e.to_string())?;
    // User-initiated activation: grab OS focus so the textarea can receive
    // keystrokes immediately. `focus: false` in config only suppresses the
    // implicit focus-on-create; set_focus() still works on demand.
    let _ = window.set_focus();

    // On X11, WMs sometimes ignore the first set_focus() after show() because
    // the window is still transitioning to mapped. Force WM-level activation
    // via EWMH (`_NET_ACTIVE_WINDOW`) using xdotool. Match by PID + title so
    // we activate *our* floating bar and not the main window.
    #[cfg(target_os = "linux")]
    {
        let our_pid = std::process::id();
        std::thread::spawn(move || {
            std::thread::sleep(std::time::Duration::from_millis(50));
            let _ = std::process::Command::new("xdotool")
                .args([
                    "search",
                    "--onlyvisible",
                    "--pid",
                    &our_pid.to_string(),
                    "--name",
                    "Ask Nooto",
                    "windowactivate",
                    "--sync",
                ])
                .output();
        });
    }

    // Tell the frontend this was a user-initiated activation so it can expand
    // to the input state instead of sitting in the idle pill.
    let _ = app.emit("floating:activate", ());
    Ok(())
}

#[command]
pub async fn hide_floating_bar(app: AppHandle) -> Result<(), String> {
    if let Some(window) = app.get_webview_window(FLOATING_LABEL) {
        window.hide().map_err(|e| e.to_string())?;
    }
    Ok(())
}

#[command]
pub async fn resize_floating_bar(app: AppHandle, height: f64) -> Result<(), String> {
    let window = app
        .get_webview_window(FLOATING_LABEL)
        .ok_or_else(|| "floating window not found".to_string())?;

    let clamped = height.clamp(40.0, 700.0);
    window
        .set_size(LogicalSize::new(DEFAULT_WIDTH, clamped))
        .map_err(|e| e.to_string())?;

    if let Some(pos) = anchor_top_center(&app, DEFAULT_WIDTH) {
        let _ = window.set_position(pos);
    }

    Ok(())
}

#[command]
pub async fn focus_floating_bar(app: AppHandle) -> Result<(), String> {
    if let Some(window) = app.get_webview_window(FLOATING_LABEL) {
        window.set_focus().map_err(|e| e.to_string())?;
    }
    Ok(())
}

/// Show the floating bar in "alert" mode with a title + body. Used by the
/// focus assistant to surface distraction notifications inline even when
/// the main window already has focus (OS notifications are suppressed in
/// that case on most desktops).
#[command]
pub async fn show_floating_alert(
    app: AppHandle,
    title: String,
    body: String,
) -> Result<(), String> {
    let window = app
        .get_webview_window(FLOATING_LABEL)
        .ok_or_else(|| "floating window not found".to_string())?;

    if let Some(pos) = anchor_top_center(&app, DEFAULT_WIDTH) {
        let _ = window.set_position(pos);
    }

    window.show().map_err(|e| e.to_string())?;

    // Tell the floating-bar frontend to render the alert. It will auto-hide
    // after a few seconds (handled in FloatingBar.tsx).
    #[derive(serde::Serialize, Clone)]
    struct AlertPayload {
        title: String,
        body: String,
    }
    let _ = app.emit(
        "floating:alert",
        AlertPayload { title, body },
    );

    Ok(())
}

#[command]
pub async fn show_main_window(app: AppHandle) -> Result<(), String> {
    if let Some(window) = app.get_webview_window("main") {
        window.show().map_err(|e| e.to_string())?;
        window.set_focus().map_err(|e| e.to_string())?;
    }
    Ok(())
}

// ---------------------------------------------------------------------------
// Whispr live-transcription HUD
// ---------------------------------------------------------------------------

pub const WHISPR_LABEL: &str = "whispr";
pub const WHISPR_WIDTH: f64 = 120.0;
const WHISPR_TOP_MARGIN: f64 = 20.0;

fn anchor_whispr_top_center(
    app: &AppHandle,
    width: f64,
) -> Option<PhysicalPosition<i32>> {
    let window = app.get_webview_window(WHISPR_LABEL)?;
    let monitor = window
        .current_monitor()
        .ok()
        .flatten()
        .or_else(|| app.primary_monitor().ok().flatten())?;

    let scale = monitor.scale_factor();
    let size = monitor.size();
    let pos = monitor.position();

    let monitor_width_logical = size.width as f64 / scale;
    let x_logical = (monitor_width_logical - width) / 2.0;

    let x_physical = pos.x + (x_logical * scale).round() as i32;
    let y_physical = pos.y + (WHISPR_TOP_MARGIN * scale).round() as i32;

    Some(PhysicalPosition::new(x_physical, y_physical))
}

#[command]
pub async fn show_whispr_hud(app: AppHandle) -> Result<(), String> {
    eprintln!("[whispr] show_whispr_hud invoked");
    let window = app.get_webview_window(WHISPR_LABEL).ok_or_else(|| {
        eprintln!("[whispr] window not found by label {}", WHISPR_LABEL);
        "whispr window not found".to_string()
    })?;

    // Whispr now follows the cursor (same UX as the Companion buddy) instead
    // of pinning to top-center. Warm the monitor cache so the position calc
    // works on first call, then set an initial cursor-anchored position so
    // the window doesn't flash at its old position before the tracker takes
    // over, then enroll the label in the cursor tracker.
    #[cfg(target_os = "macos")]
    {
        super::companion::refresh_monitor_cache_pub(&app);
    }
    #[cfg(target_os = "macos")]
    {
        if let Some(pos) = super::companion::buddy_position_from_cache_pub() {
            eprintln!(
                "[whispr] initial cursor-anchored position: ({}, {})",
                pos.x, pos.y
            );
            let _ = window.set_position(pos);
        } else if let Some(pos) = anchor_whispr_top_center(&app, WHISPR_WIDTH) {
            eprintln!(
                "[whispr] cursor unavailable — falling back to top-center: ({}, {})",
                pos.x, pos.y
            );
            let _ = window.set_position(pos);
        } else {
            eprintln!("[whispr] no position computable — window will appear at default");
        }
    }
    #[cfg(not(target_os = "macos"))]
    if let Some(pos) = anchor_whispr_top_center(&app, WHISPR_WIDTH) {
        let _ = window.set_position(pos);
    }

    window.show().map_err(|e| {
        eprintln!("[whispr] window.show() failed: {}", e);
        e.to_string()
    })?;

    #[cfg(target_os = "macos")]
    super::companion::track_window(WHISPR_LABEL, app);

    Ok(())
}

#[command]
pub async fn hide_whispr_hud(app: AppHandle) -> Result<(), String> {
    #[cfg(target_os = "macos")]
    super::companion::untrack_window(WHISPR_LABEL);

    if let Some(window) = app.get_webview_window(WHISPR_LABEL) {
        window.hide().map_err(|e| e.to_string())?;
    }
    Ok(())
}

/// Broadcast the rolling live transcript to every window. Called from
/// the main-window PTT hook. Rust's `app.emit` reliably reaches all
/// windows; the JS `emitTo` path didn't always deliver to a freshly
/// shown whispr window (webview not yet fully mounted).
#[derive(serde::Serialize, Clone)]
pub struct WhisprLivePayload {
    pub text: String,
    pub is_final: bool,
}

#[command]
pub async fn whispr_push_live(
    app: AppHandle,
    text: String,
    is_final: bool,
) -> Result<(), String> {
    app.emit("whispr:live", WhisprLivePayload { text, is_final })
        .map_err(|e| e.to_string())
}

#[command]
pub async fn resize_whispr_hud(app: AppHandle, height: f64) -> Result<(), String> {
    let window = app
        .get_webview_window(WHISPR_LABEL)
        .ok_or_else(|| "whispr window not found".to_string())?;
    window
        .set_size(LogicalSize::new(WHISPR_WIDTH, height.max(48.0)))
        .map_err(|e| e.to_string())?;
    // Top-center anchor doesn't depend on height, but re-apply in case
    // the user moved across monitors.
    if let Some(pos) = anchor_whispr_top_center(&app, WHISPR_WIDTH) {
        let _ = window.set_position(pos);
    }
    Ok(())
}
