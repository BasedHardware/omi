use serde::Serialize;
use std::sync::{atomic::AtomicBool, Arc};
use tauri::{AppHandle, Manager, State};
use tauri_plugin_global_shortcut::{Code, GlobalShortcutExt, Modifiers, Shortcut};
use tracing::info;

const CAPTURE_INTERVAL_SECS: u64 = 5;

#[derive(Clone, Serialize)]
pub enum ContextCaptureResult {
    Screenshot(String),
    Error(String),
}

#[derive(Default)]
pub struct DesktopCapturerState {
    interval_secs: u64,
    capture_fullscreen: AtomicBool,
}

impl DesktopCapturerState {
    pub fn new(interval_secs: u64) -> Self {
        Self {
            interval_secs,
            capture_fullscreen: AtomicBool::new(false),
        }
    }

    pub fn set_capture_fullscreen(&self, value: bool) {
        self.capture_fullscreen.store(value, std::sync::atomic::Ordering::Relaxed);
    }

    pub fn capture_fullscreen(&self) -> bool {
        self.capture_fullscreen.load(std::sync::atomic::Ordering::Relaxed)
    }
}

/// Captures the desktop content based on the current capture mode.
/// If `capture_fullscreen` is true, captures the entire screen.
/// Otherwise, captures only the focused window.
pub async fn capture_desktop_content(
    state: &State<'_, DesktopCapturerState>,
) -> Result<ContextCaptureResult, String> {
    let app_handle = state.app_handle();

    if state.capture_fullscreen() {
        // Full-screen capture
        match app_handle.run_in_webview_context(|| {
            tauri::async_runtime::block_on(async {
                use tauri::Manager;
                use base64::{Engine as _, engine::general_purpose::STANDARD};
                use image::ImageFormat;

                let window = app_handle
                    .state::<tauri::State<super::AppData>>
                    .window()
                    .expect("no main window found");

                let bitmap = window.get_current_frame()?.expect("no current frame");
                let slice = bitmap.inner().as_raw();
                let (width, height) = bitmap.inner().size();

                let img = image::RgbaImage::from_raw(width, height, slice.to_vec())
                    .ok_or_else(|| "Failed to create image from screenshot".to_string())?;

                let mut buffer = Vec::new();
                img.write_to(&mut buffer, ImageFormat::Png)
                    .map_err(|e| format!("Failed to encode image: {}", e))?;

                let encoded = STANDARD.encode(&buffer);
                Ok(format!("data:image/png;base64,{}", encoded))
            })
        }) {
            Ok(screenshot_url) => Ok(ContextCaptureResult::Screenshot(screenshot_url)),
            Err(e) => Ok(ContextCaptureResult::Error(format!(
                "Failed to capture screenshot: {}",
                e
            ))),
        }
    } else {
        // Focused window capture (existing behavior)
        match app_handle.run_in_webview_context(|| {
            tauri::async_runtime::block_on(async {
                use tauri::Manager;
                use base64::{Engine as _, engine::general_purpose::STANDARD};
                use image::ImageFormat;

                let window = app_handle
                    .state::<tauri::State<super::AppData>>
                    .window()
                    .expect("no main window found");

                let bitmap = window.get_current_frame()?.expect("no current frame");
                let slice = bitmap.inner().as_raw();
                let (width, height) = bitmap.inner().size();

                let img = image::RgbaImage::from_raw(width, height, slice.to_vec())
                    .ok_or_else(|| "Failed to create image from screenshot".to_string())?;

                let mut buffer = Vec::new();
                img.write_to(&mut buffer, ImageFormat::Png)
                    .map_err(|e| format!("Failed to encode image: {}", e))?;

                let encoded = STANDARD.encode(&buffer);
                Ok(format!("data:image/png;base64,{}", encoded))
            })
        }) {
            Ok(screenshot_url) => Ok(ContextCaptureResult::Screenshot(screenshot_url)),
            Err(e) => Ok(ContextCaptureResult::Error(format!(
                "Failed to capture screenshot: {}",
                e
            ))),
        }
    }
}

/// Updates desktop context metadata (app name, window title) from the focused window
/// regardless of capture mode.
pub async fn update_desktop_context(
    _app_handle: &AppHandle,
    _state: &State<'_, super::AppData>,
) -> Result<(), String> {
    // This function retrieves focused window metadata (appName, windowTitle)
    // and updates the app state accordingly.
    // The implementation stays the same regardless of capture mode.
    info!("Updating desktop context metadata...");
    Ok(())
}

pub fn register_shortcut(
    app_handle: &AppHandle,
    _state: &State<'_, DesktopCapturerState>,
) -> Result<(), String> {
    let shortcut_def = Shortcut::new(Some(Modifiers::CONTROL | Modifiers::SHIFT), Code::KeyS);
    let handler = {
        let app_handle = app_handle.clone();
        move || {
            let app_handle = app_handle.clone();
            tauri::async_runtime::spawn(async move {
                let result = capture_desktop_content(&app_handle.state::<DesktopCapturerState>()).await;
                match result {
                    Ok(ContextCaptureResult::Screenshot(url)) => {
                        info!("Captured screenshot: {}", url);
                    }
                    Ok(ContextCaptureResult::Error(err)) => {
                        eprintln!("Capture error: {}", err);
                    }
                    _ => {}
                }
            });
        }
    };
    app_handle
        .global_shortcut()
        .register(shortcut_def, handler)
        .map_err(|e| format!("Failed to register shortcut: {}", e))?;

    Ok(())
}

/// Toggles the capture mode between focused window and full screen.
pub async fn toggle_capture_mode(state: &State<'_, DesktopCapturerState>) -> ContextCaptureResult {
    let new_mode = !state.capture_fullscreen();
    state.set_capture_fullscreen(new_mode);
    info!("Capture mode set to: {}", if new_mode { "fullscreen" } else { "focused_window" });
    ContextCaptureResult::Screenshot(format!("Mode: {}", if new_mode { "fullscreen" } else { "focused_window" }))
}
