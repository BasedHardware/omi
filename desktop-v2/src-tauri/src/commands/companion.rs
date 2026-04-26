//! Companion — cursor-anchored buddy sprite + per-display click-through overlays.
//!
//! Phase 1 scope: show/hide the buddy window and follow the cursor at ~60 Hz.
//! No AI, no audio. See the Companion plan for Phase 2+ scope.
//!
//! Key design choices:
//! - Cursor tracking polls `NSEvent.mouseLocation` at 60 Hz in a tokio task.
//! - Monitor list is cached on show and reused every tick to avoid 60 IPC calls/s.
//! - Overlay windows are created programmatically at runtime (one per display).
//! - collectionBehavior is set via objc2-app-kit so the buddy follows across Spaces.
//! - The buddy never steals focus (focus: false in conf + we never call set_focus).

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::OnceLock;
use std::time::Duration;

use tauri::{AppHandle, Manager, Monitor, PhysicalPosition, PhysicalSize, WebviewUrl};

const BUDDY_LABEL: &str = "companion-buddy";

/// Labels of windows that should follow the cursor at 60 Hz. Mutated by
/// `companion_show_buddy` / `companion_hide_buddy` and the Whispr show/hide
/// commands. The tracker iterates this set each tick.
static TRACKED_LABELS: std::sync::Mutex<Vec<&'static str>> = std::sync::Mutex::new(Vec::new());
const BUDDY_OFFSET_PT: f64 = 24.0;

/// True while the cursor-tracker task should keep running.
static TRACKER_RUNNING: AtomicBool = AtomicBool::new(false);

/// Guards against spawning the tracker more than once concurrently.
static TRACKER_SPAWNED: AtomicBool = AtomicBool::new(false);

/// Set of overlay window labels already created (protected by Mutex).
static OVERLAY_LABELS: OnceLock<std::sync::Mutex<Vec<String>>> = OnceLock::new();

fn overlay_labels() -> &'static std::sync::Mutex<Vec<String>> {
    OVERLAY_LABELS.get_or_init(|| std::sync::Mutex::new(Vec::new()))
}

/// Cached monitor list, refreshed on each `companion_show_buddy` call.
/// Avoids querying the OS 60 times/second inside the cursor tracker.
static CACHED_MONITORS: OnceLock<std::sync::Mutex<Vec<Monitor>>> = OnceLock::new();

fn cached_monitors() -> &'static std::sync::Mutex<Vec<Monitor>> {
    CACHED_MONITORS.get_or_init(|| std::sync::Mutex::new(Vec::new()))
}

fn refresh_monitor_cache(app: &AppHandle) {
    if let Ok(monitors) = app.available_monitors() {
        if let Ok(mut cache) = cached_monitors().lock() {
            *cache = monitors;
        }
    }
}

/// Public-crate wrapper so other modules (Whispr show command) can warm the
/// monitor cache before they enroll a window in the cursor tracker.
pub(crate) fn refresh_monitor_cache_pub(app: &AppHandle) {
    refresh_monitor_cache(app);
}

// ---------------------------------------------------------------------------
// Show / hide the companion buddy window
// ---------------------------------------------------------------------------

#[tauri::command]
pub async fn companion_show_buddy(app: AppHandle) -> Result<(), String> {
    eprintln!("[companion] show_buddy invoked");
    let window = app.get_webview_window(BUDDY_LABEL).ok_or_else(|| {
        eprintln!("[companion] buddy window not found by label {}", BUDDY_LABEL);
        "companion-buddy window not found".to_string()
    })?;

    refresh_monitor_cache(&app);

    if let Some(pos) = buddy_position_from_cache() {
        eprintln!("[companion] positioning buddy at ({}, {})", pos.x, pos.y);
        let _ = window.set_position(pos);
    } else {
        eprintln!("[companion] no cursor position available — showing at last known");
    }

    window.show().map_err(|e| {
        eprintln!("[companion] window.show() failed: {}", e);
        e.to_string()
    })?;
    eprintln!("[companion] buddy window shown");

    #[cfg(target_os = "macos")]
    apply_buddy_chrome(&window);

    track_window(BUDDY_LABEL, app);

    Ok(())
}

#[tauri::command]
pub async fn companion_hide_buddy(app: AppHandle) -> Result<(), String> {
    eprintln!("[companion] hide_buddy invoked");
    untrack_window(BUDDY_LABEL);

    if let Some(window) = app.get_webview_window(BUDDY_LABEL) {
        window.hide().map_err(|e| e.to_string())?;
        eprintln!("[companion] buddy window hidden");
    } else {
        eprintln!("[companion] hide_buddy: window not found");
    }

    Ok(())
}

// ---------------------------------------------------------------------------
// Overlay window management
// ---------------------------------------------------------------------------

#[tauri::command]
pub async fn companion_ensure_overlays(app: AppHandle) -> Result<Vec<String>, String> {
    let monitors = app.available_monitors().map_err(|e| e.to_string())?;
    eprintln!(
        "[companion] ensure_overlays — Tauri reports {} monitor(s)",
        monitors.len()
    );
    for (i, m) in monitors.iter().enumerate() {
        eprintln!(
            "[companion]   monitor {}: name={:?} pos=({},{}) size={}x{} scale={}",
            i,
            m.name(),
            m.position().x,
            m.position().y,
            m.size().width,
            m.size().height,
            m.scale_factor()
        );
    }

    let mut labels_guard = overlay_labels()
        .lock()
        .map_err(|e| format!("overlay labels lock poisoned: {}", e))?;

    let mut result = Vec::new();

    for (idx, monitor) in monitors.iter().enumerate() {
        let label = format!("companion-overlay-{}", idx);
        result.push(label.clone());

        if labels_guard.contains(&label) {
            // Idempotent: resize to current display dimensions in case config changed.
            if let Some(win) = app.get_webview_window(&label) {
                let size = monitor.size();
                let _ = win.set_size(PhysicalSize::new(size.width, size.height));
                let pos = monitor.position();
                let _ = win.set_position(PhysicalPosition::new(pos.x, pos.y));
            }
            continue;
        }

        let size = monitor.size();
        let pos = monitor.position();

        // Builder takes logical coordinates.
        let scale = monitor.scale_factor();
        let logical_w = size.width as f64 / scale;
        let logical_h = size.height as f64 / scale;
        let logical_x = pos.x as f64 / scale;
        let logical_y = pos.y as f64 / scale;

        let url = WebviewUrl::App(
            format!("index.html?window=companion-overlay-{}", idx).into(),
        );

        // visible(true) at creation so WebKit eagerly loads index.html and the
        // React `CompanionOverlay` mounts + registers its `companion:points`
        // listener BEFORE the first PTT press. With visible(false), Tauri
        // lazy-loads the WebContents on the first show() call, racing the
        // broadcast and dropping events. Empty + transparent + click-through
        // means an idle overlay is visually invisible anyway.
        let win = tauri::WebviewWindowBuilder::new(&app, &label, url)
            .title("Companion Overlay")
            .inner_size(logical_w, logical_h)
            .position(logical_x, logical_y)
            .transparent(true)
            .decorations(false)
            .always_on_top(true)
            .skip_taskbar(true)
            .shadow(false)
            .visible(true)
            .build()
            .map_err(|e| format!("failed to create overlay {}: {}", label, e))?;

        win.set_ignore_cursor_events(true)
            .map_err(|e| format!("set_ignore_cursor_events failed: {}", e))?;

        #[cfg(target_os = "macos")]
        {
            set_collection_behavior_all_spaces(&win);
            // Raise above the Dock so pointer sprites land on top of dock
            // icons rather than rendering behind them. Tauri's always_on_top
            // = NSFloatingWindowLevel (3) is below kCGDockWindowLevel (~20).
            raise_overlay_above_dock(&win);
        }

        labels_guard.push(label);
    }

    Ok(result)
}

#[tauri::command]
pub async fn companion_set_overlays_visible(
    app: AppHandle,
    visible: bool,
) -> Result<(), String> {
    let labels = overlay_labels()
        .lock()
        .map_err(|e| format!("lock poisoned: {}", e))?
        .clone();

    eprintln!(
        "[companion] set_overlays_visible({}) — {} overlay(s) registered",
        visible,
        labels.len()
    );

    for label in &labels {
        match app.get_webview_window(label) {
            Some(win) => {
                let res = if visible { win.show() } else { win.hide() };
                eprintln!(
                    "[companion] overlay {} {} -> {:?}",
                    label,
                    if visible { "show" } else { "hide" },
                    res.as_ref().map(|_| "ok").unwrap_or("err")
                );
            }
            None => {
                eprintln!("[companion] overlay {} NOT FOUND in window registry", label);
            }
        }
    }

    Ok(())
}

// ---------------------------------------------------------------------------
// Cursor tracker (60 Hz tokio task)
// ---------------------------------------------------------------------------

/// Add a window label to the cursor-follow set. Idempotent. Spawns the
/// 60 Hz tracker thread if it isn't already running.
pub(crate) fn track_window(label: &'static str, app: AppHandle) {
    {
        let mut guard = TRACKED_LABELS.lock().expect("tracked labels poisoned");
        if !guard.contains(&label) {
            guard.push(label);
        }
    }
    start_cursor_tracker(app);
}

/// Remove a window label from the cursor-follow set. The tracker keeps
/// running until at least one label remains; if the set empties, the
/// tracker exits on its next tick.
pub(crate) fn untrack_window(label: &str) {
    if let Ok(mut guard) = TRACKED_LABELS.lock() {
        guard.retain(|l| *l != label);
    }
}

fn start_cursor_tracker(app: AppHandle) {
    if TRACKER_SPAWNED.swap(true, Ordering::SeqCst) {
        return;
    }
    TRACKER_RUNNING.store(true, Ordering::SeqCst);

    tauri::async_runtime::spawn(async move {
        let interval = Duration::from_millis(16);
        let mut last: Option<(i32, i32)> = None;

        while TRACKER_RUNNING.load(Ordering::SeqCst) {
            // Snapshot the tracked-label set each tick so add/remove from
            // other threads is reflected promptly.
            let labels: Vec<&'static str> = match TRACKED_LABELS.lock() {
                Ok(g) => g.clone(),
                Err(_) => Vec::new(),
            };
            if labels.is_empty() {
                // Nothing to track — exit the loop. track_window() will
                // re-spawn us.
                break;
            }

            if let Some(pos) = buddy_position_from_cache() {
                let moved = match last {
                    Some((lx, ly)) => {
                        let dx = pos.x.saturating_sub(lx).abs();
                        let dy = pos.y.saturating_sub(ly).abs();
                        dx >= 1 || dy >= 1
                    }
                    None => true,
                };
                if moved {
                    for label in &labels {
                        if let Some(win) = app.get_webview_window(label) {
                            let _ = win.set_position(pos);
                        }
                    }
                    last = Some((pos.x, pos.y));
                }
            }
            tokio::time::sleep(interval).await;
        }

        tracing::info!("[companion] cursor tracker stopped");
        TRACKER_SPAWNED.store(false, Ordering::SeqCst);
    });
}

// ---------------------------------------------------------------------------
// Cursor position computation
// ---------------------------------------------------------------------------

fn buddy_position_from_cache() -> Option<PhysicalPosition<i32>> {
    #[cfg(target_os = "macos")]
    return macos_buddy_position();
    #[cfg(not(target_os = "macos"))]
    return None;
}

/// Public-crate wrapper used by `floating.rs` so the Whispr HUD's initial
/// position before the tracker takes over matches what the buddy would use.
pub(crate) fn buddy_position_from_cache_pub() -> Option<PhysicalPosition<i32>> {
    buddy_position_from_cache()
}

/// Get the current mouse location in CG global top-origin point coordinates.
///
/// Uses `CGEventSource` + `CGEvent::new().location()` because `NSEvent::mouseLocation()`
/// is only safe on the main thread — calling it from a tokio worker (where the
/// cursor tracker runs) returns stale values and the buddy never follows the
/// cursor. CG is thread-safe and returns the live HID cursor position.
#[cfg(target_os = "macos")]
pub(crate) fn cg_mouse_location() -> Option<(f64, f64)> {
    use core_graphics::event::CGEvent;
    use core_graphics::event_source::{CGEventSource, CGEventSourceStateID};

    let source = CGEventSource::new(CGEventSourceStateID::HIDSystemState).ok()?;
    let event = CGEvent::new(source).ok()?;
    let loc = event.location();
    Some((loc.x, loc.y))
}

/// Convert a CG global-point cursor location (top-origin, logical points) to
/// the `PhysicalPosition` Tauri expects, applying the buddy sprite offset so
/// the orb sits to the bottom-right of the cursor.
///
/// Tauri's monitor.position() is in physical pixels with top-origin, matching
/// CG's global coordinate system. Primary is at (0, 0); secondaries can be at
/// positive or negative offsets depending on the user's Displays arrangement.
#[cfg(target_os = "macos")]
fn macos_buddy_position() -> Option<PhysicalPosition<i32>> {
    let (mouse_x_pt, mouse_y_pt) = cg_mouse_location()?;

    let monitors = cached_monitors().lock().ok()?;
    if monitors.is_empty() {
        return None;
    }

    // Find which monitor the cursor is on by converting each monitor's physical
    // bounds to logical points and point-in-rect testing.
    let monitor = monitors
        .iter()
        .find(|m| {
            let scale = m.scale_factor();
            let x_pt = m.position().x as f64 / scale;
            let y_pt = m.position().y as f64 / scale;
            let w_pt = m.size().width as f64 / scale;
            let h_pt = m.size().height as f64 / scale;
            mouse_x_pt >= x_pt
                && mouse_x_pt < x_pt + w_pt
                && mouse_y_pt >= y_pt
                && mouse_y_pt < y_pt + h_pt
        })
        .or_else(|| monitors.first())?;

    let scale = monitor.scale_factor();
    // Global cursor position in physical pixels (same space Tauri's set_position uses).
    let cursor_x_px = mouse_x_pt * scale;
    let cursor_y_px = mouse_y_pt * scale;
    let offset_px = BUDDY_OFFSET_PT * scale;

    Some(PhysicalPosition::new(
        (cursor_x_px + offset_px).round() as i32,
        (cursor_y_px + offset_px).round() as i32,
    ))
}

// ---------------------------------------------------------------------------
// macOS window chrome helpers
// ---------------------------------------------------------------------------

/// Set NSWindow collection behavior so the window follows across all Spaces
/// and is allowed in fullscreen. Called for both buddy and overlay windows.
#[cfg(target_os = "macos")]
fn set_collection_behavior_all_spaces(window: &tauri::WebviewWindow) {
    use objc2_app_kit::{NSWindow, NSWindowCollectionBehavior};
    let _ = window.with_webview(|webview| {
        unsafe {
            let ns_win: &NSWindow = &*webview.ns_window().cast();
            let behavior = NSWindowCollectionBehavior::CanJoinAllSpaces
                | NSWindowCollectionBehavior::Stationary
                | NSWindowCollectionBehavior::FullScreenAuxiliary;
            ns_win.setCollectionBehavior(behavior);
        }
    });
}

/// Raise the overlay's NSWindow level above the macOS Dock.
///
/// Tauri's `.always_on_top(true)` sets `NSFloatingWindowLevel` (= 3), which
/// is BELOW the Dock's level (~20 / `kCGDockWindowLevel`). Without this hop,
/// the pointer sprite renders behind any dock icon it's pointing at — which
/// is exactly the case when answering "how do I open settings".
///
/// We use `NSPopUpMenuWindowLevel` (101) — well above the Dock and the
/// menu bar (NSMainMenuWindowLevel = 24) but below `NSScreenSaverWindowLevel`
/// (1000) so we don't fight system UI like the screensaver.
#[cfg(target_os = "macos")]
fn raise_overlay_above_dock(window: &tauri::WebviewWindow) {
    use objc2_app_kit::{NSPopUpMenuWindowLevel, NSWindow};
    let _ = window.with_webview(|webview| {
        unsafe {
            let ns_win: &NSWindow = &*webview.ns_window().cast();
            ns_win.setLevel(NSPopUpMenuWindowLevel);
        }
    });
}

#[cfg(target_os = "macos")]
fn apply_buddy_chrome(window: &tauri::WebviewWindow) {
    use objc2_app_kit::{NSFloatingWindowLevel, NSWindow};
    set_collection_behavior_all_spaces(window);
    let _ = window.with_webview(|webview| {
        unsafe {
            let ns_win: &NSWindow = &*webview.ns_window().cast();
            // NSFloatingWindowLevel (= 3) floats above normal windows but below system UI.
            ns_win.setLevel(NSFloatingWindowLevel);
            ns_win.setHidesOnDeactivate(false);
        }
    });
}
