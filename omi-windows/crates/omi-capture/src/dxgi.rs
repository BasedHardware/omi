/// Screen capture using `xcap` (cross-platform, no raw Win32 needed).
/// Saves JPEG thumbnails to `%APPDATA%/omi/screenshots/`.

use anyhow::{Context, Result};
use image::RgbaImage;
use std::path::PathBuf;

/// A captured frame with metadata.
#[derive(Debug, Clone)]
pub struct CapturedFrame {
    /// Absolute path to the saved JPEG thumbnail.
    pub path: PathBuf,
    /// Active window title at capture time (best-effort).
    pub window_title: Option<String>,
    /// Raw RGBA image for downstream processing (dedup, video encoding).
    pub rgba_image: Option<RgbaImage>,
}

/// Info about an available monitor.
#[derive(Debug, Clone)]
pub struct MonitorInfo {
    pub name: String,
    pub width: u32,
    pub height: u32,
    pub is_primary: bool,
    pub index: usize,
}

/// Compute a perceptual hash (dHash) of an RGBA image.
/// Scales to 9×8 grayscale, compares each pixel to its right neighbor → 64-bit hash.
pub fn dhash(img: &RgbaImage) -> u64 {
    let small = image::imageops::resize(img, 9, 8, image::imageops::FilterType::Nearest);
    let mut hash: u64 = 0;
    for y in 0..8 {
        for x in 0..8 {
            let px = small.get_pixel(x, y);
            let nx = small.get_pixel(x + 1, y);
            let gray_l = 0.299 * px[0] as f32 + 0.587 * px[1] as f32 + 0.114 * px[2] as f32;
            let gray_r = 0.299 * nx[0] as f32 + 0.587 * nx[1] as f32 + 0.114 * nx[2] as f32;
            if gray_l > gray_r {
                hash |= 1 << (y * 8 + x);
            }
        }
    }
    hash
}

pub fn hamming_distance(a: u64, b: u64) -> u32 {
    (a ^ b).count_ones()
}

/// Tracks the last frame hash to skip near-identical captures.
pub struct FrameDeduplicator {
    last_hash: Option<u64>,
    pub skipped: u64,
    pub captured: u64,
}

impl FrameDeduplicator {
    pub fn new() -> Self {
        Self { last_hash: None, skipped: 0, captured: 0 }
    }

    /// Returns true if this frame should be skipped (too similar to previous).
    pub fn should_skip(&mut self, img: &RgbaImage) -> bool {
        let hash = dhash(img);
        let skip = match self.last_hash {
            Some(prev) => hamming_distance(prev, hash) <= 5,
            None => false,
        };
        self.last_hash = Some(hash);
        if skip { self.skipped += 1; } else { self.captured += 1; }
        skip
    }
}

/// Directory where screenshots are stored.
pub fn screenshot_dir() -> PathBuf {
    let base = std::env::var("APPDATA").unwrap_or_else(|_| ".".into());
    PathBuf::from(base).join("omi").join("screenshots")
}

/// List all available monitors.
pub fn list_monitors() -> Result<Vec<MonitorInfo>> {
    use xcap::Monitor;
    let monitors = Monitor::all().context("Failed to enumerate monitors")?;
    Ok(monitors.iter().enumerate().map(|(i, m)| MonitorInfo {
        name: m.name().to_string(),
        width: m.width(),
        height: m.height(),
        is_primary: m.is_primary(),
        index: i,
    }).collect())
}

/// Capture a specific monitor by index.
pub fn capture_monitor(index: usize) -> Result<Option<CapturedFrame>> {
    use xcap::Monitor;
    let monitors = Monitor::all().context("Failed to enumerate monitors")?;
    match monitors.into_iter().nth(index) {
        Some(m) => capture_monitor_inner(m, Some(index)),
        None => {
            tracing::warn!("[CAPTURE] Monitor index {index} not found");
            Ok(None)
        }
    }
}

/// Capture all monitors, returning one frame per monitor.
pub fn capture_all_monitors() -> Result<Vec<CapturedFrame>> {
    use xcap::Monitor;
    let monitors = Monitor::all().context("Failed to enumerate monitors")?;
    let mut frames = Vec::new();
    for (i, m) in monitors.into_iter().enumerate() {
        match capture_monitor_inner(m, Some(i))? {
            Some(f) => frames.push(f),
            None => {}
        }
    }
    Ok(frames)
}

/// Capture the primary monitor and save as JPEG thumbnail.
pub fn capture_screen_jpeg() -> Result<Option<CapturedFrame>> {
    use xcap::Monitor;

    let mut monitors = Monitor::all().context("Failed to enumerate monitors")?;
    let primary = monitors.iter().position(|m| m.is_primary())
        .map(|i| monitors.remove(i))
        .or_else(|| if monitors.is_empty() { None } else { Some(monitors.remove(0)) });

    match primary {
        Some(m) => capture_monitor_inner(m, None),
        None => {
            tracing::warn!("[CAPTURE] No monitor found");
            Ok(None)
        }
    }
}

fn capture_monitor_inner(monitor: xcap::Monitor, monitor_idx: Option<usize>) -> Result<Option<CapturedFrame>> {
    let window_title = get_foreground_title();

    let rgba = match monitor.capture_image() {
        Ok(img) => img,
        Err(e) => {
            tracing::error!("[DXGI] capture_image FAILED: {e:#}");
            return Err(anyhow::anyhow!("capture_image failed: {e}"));
        }
    };

    let (w, h) = (rgba.width(), rgba.height());
    let thumb_w = w.min(1280);
    let thumb_h = (h as f32 * thumb_w as f32 / w as f32) as u32;
    let thumb_rgba = image::imageops::resize(&rgba, thumb_w, thumb_h, image::imageops::FilterType::Triangle);

    let thumb_rgb = image::DynamicImage::ImageRgba8(thumb_rgba.clone()).into_rgb8();

    std::fs::create_dir_all(screenshot_dir()).context("create screenshot dir")?;
    let ts = chrono::Utc::now().format("%Y%m%d_%H%M%S");
    let suffix = monitor_idx.map(|i| format!("_m{i}")).unwrap_or_default();
    let path = screenshot_dir().join(format!("{ts}{suffix}.jpg"));
    thumb_rgb.save_with_format(&path, image::ImageFormat::Jpeg)
        .context("Failed to save JPEG")?;

    Ok(Some(CapturedFrame { path, window_title, rgba_image: Some(thumb_rgba) }))
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
