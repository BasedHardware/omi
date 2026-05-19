/// Screen capture using `xcap` (cross-platform, no raw Win32 needed).
/// Saves JPEG thumbnails to `%APPDATA%/omi/screenshots/`.

use anyhow::{Context, Result};
use std::path::PathBuf;

/// A captured frame with metadata.
#[derive(Debug, Clone)]
pub struct CapturedFrame {
    /// Absolute path to the saved JPEG thumbnail.
    pub path: PathBuf,
    /// Active window title at capture time (best-effort).
    pub window_title: Option<String>,
}

/// Directory where screenshots are stored.
pub fn screenshot_dir() -> PathBuf {
    let base = std::env::var("APPDATA").unwrap_or_else(|_| ".".into());
    PathBuf::from(base).join("omi").join("screenshots")
}

/// Capture the primary monitor and save as JPEG thumbnail.
/// Uses `xcap` for cross-platform screen capture (no raw Win32 needed).
pub fn capture_screen_jpeg() -> Result<Option<CapturedFrame>> {
    use xcap::Monitor;

    // Get the active window title (Windows-only best-effort)
    let window_title = get_foreground_title();
    tracing::info!("[DXGI] capture_screen_jpeg called | active_window={:?}", window_title);

    // Grab the primary monitor, fall back to first available
    let mut monitors = Monitor::all().context("Failed to enumerate monitors")?;
    tracing::info!("[DXGI] Found {} monitors", monitors.len());
    let primary = monitors.iter().position(|m| m.is_primary())
        .map(|i| monitors.remove(i))
        .or_else(|| if monitors.is_empty() { None } else { Some(monitors.remove(0)) });

    let monitor = match primary {
        Some(m) => m,
        None => {
            tracing::warn!("[CAPTURE] No monitor found");
            return Ok(None);
        }
    };

    // Capture as RGBA image
    let rgba = monitor.capture_image().context("Monitor::capture_image failed")?;

    // Scale to thumbnail (max 1280px wide)
    let (w, h) = (rgba.width(), rgba.height());
    let thumb_w = w.min(1280);
    let thumb_h = (h as f32 * thumb_w as f32 / w as f32) as u32;
    let thumb = image::imageops::resize(&rgba, thumb_w, thumb_h, image::imageops::FilterType::Triangle);

    // Save as JPEG
    std::fs::create_dir_all(screenshot_dir()).context("create screenshot dir")?;
    let ts = chrono::Utc::now().format("%Y%m%d_%H%M%S");
    let path = screenshot_dir().join(format!("{ts}.jpg"));
    thumb.save_with_format(&path, image::ImageFormat::Jpeg)
        .context("Failed to save JPEG")?;

    Ok(Some(CapturedFrame { path, window_title }))
}

/// Get the foreground window title on Windows; returns None on other platforms.
#[cfg(target_os = "windows")]
fn get_foreground_title() -> Option<String> {
    use windows::Win32::UI::WindowsAndMessaging::{GetForegroundWindow, GetWindowTextW};
    unsafe {
        let hwnd = GetForegroundWindow();
        if hwnd.0.is_null() {
            return None;
        }
        let mut buf = [0u16; 512];
        let len = GetWindowTextW(hwnd, &mut buf);
        if len > 0 {
            Some(String::from_utf16_lossy(&buf[..len as usize]))
        } else {
            None
        }
    }
}

#[cfg(not(target_os = "windows"))]
fn get_foreground_title() -> Option<String> {
    None
}
