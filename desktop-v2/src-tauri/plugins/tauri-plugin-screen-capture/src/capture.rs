use crate::models::{CaptureConfig, Screenshot};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::mpsc::Sender;

/// Shared flag used to signal the continuous capture loop to stop.
static CAPTURE_RUNNING: AtomicBool = AtomicBool::new(false);

/// Take a single screenshot and return it as a JPEG-encoded `Screenshot`.
pub fn capture_screen(config: &CaptureConfig) -> Result<Screenshot, String> {
    platform::capture_screen_impl(config)
}

/// Start a continuous capture loop on the current thread.
/// Takes a screenshot every `config.interval_ms` milliseconds and sends it
/// through `tx`. Runs until `stop_continuous_capture()` is called.
pub fn start_continuous_capture(config: CaptureConfig, tx: Sender<Screenshot>) {
    CAPTURE_RUNNING.store(true, Ordering::SeqCst);
    let interval = std::time::Duration::from_millis(config.interval_ms);

    tracing::info!(
        "Starting continuous screen capture: interval={}ms, quality={}, max_width={}",
        config.interval_ms,
        config.quality,
        config.max_width
    );

    while CAPTURE_RUNNING.load(Ordering::SeqCst) {
        match capture_screen(&config) {
            Ok(screenshot) => {
                if tx.send(screenshot).is_err() {
                    tracing::warn!("Screenshot receiver dropped, stopping capture");
                    break;
                }
            }
            Err(e) => {
                tracing::error!("Screen capture failed: {}", e);
            }
        }
        std::thread::sleep(interval);
    }

    tracing::info!("Continuous screen capture stopped");
}

/// Signal the continuous capture loop to stop.
pub fn stop_continuous_capture() {
    CAPTURE_RUNNING.store(false, Ordering::SeqCst);
}

/// Returns whether continuous capture is currently running.
pub fn is_capturing() -> bool {
    CAPTURE_RUNNING.load(Ordering::SeqCst)
}

// ---------------------------------------------------------------------------
// Linux implementation (X11 via x11rb)
// ---------------------------------------------------------------------------
#[cfg(target_os = "linux")]
mod platform {
    use super::*;
    use image::codecs::jpeg::JpegEncoder;
    use image::{ImageBuffer, RgbaImage};
    use x11rb::connection::Connection;
    use x11rb::protocol::xproto::{ConnectionExt as _, ImageFormat, ImageOrder};
    use x11rb::rust_connection::RustConnection;

    pub fn capture_screen_impl(config: &CaptureConfig) -> Result<Screenshot, String> {
        let (conn, screen_num) =
            RustConnection::connect(None).map_err(|e| format!("X11 connect failed: {}", e))?;

        let screen = &conn.setup().roots[screen_num];
        let root = screen.root;
        let width = screen.width_in_pixels;
        let height = screen.height_in_pixels;

        // Grab the full root window contents.
        let image = conn
            .get_image(
                ImageFormat::Z_PIXMAP,
                root,
                0,
                0,
                width,
                height,
                u32::MAX, // all planes
            )
            .map_err(|e| format!("get_image request failed: {}", e))?
            .reply()
            .map_err(|e| format!("get_image reply failed: {}", e))?;

        let depth = image.depth;
        let raw = image.data;

        // Convert raw pixel data to RGBA.
        // X11 ZPixmap with depth 24/32 is typically BGRx or BGRA in little-endian.
        let pixel_count = (width as usize) * (height as usize);
        let bytes_per_pixel = if raw.len() >= pixel_count * 4 {
            4
        } else if raw.len() >= pixel_count * 3 {
            3
        } else {
            return Err(format!(
                "Unexpected image data size: {} bytes for {}x{} depth={}",
                raw.len(),
                width,
                height,
                depth
            ));
        };

        let mut rgba = Vec::with_capacity(pixel_count * 4);
        let is_lsb = conn.setup().image_byte_order == ImageOrder::LSB_FIRST;

        for i in 0..pixel_count {
            let offset = i * bytes_per_pixel;
            let (r, g, b) = if is_lsb {
                // LSB first (common): stored as B, G, R, [X]
                (raw[offset + 2], raw[offset + 1], raw[offset])
            } else {
                // MSB first: stored as [X], R, G, B
                if bytes_per_pixel == 4 {
                    (raw[offset + 1], raw[offset + 2], raw[offset + 3])
                } else {
                    (raw[offset], raw[offset + 1], raw[offset + 2])
                }
            };
            rgba.push(r);
            rgba.push(g);
            rgba.push(b);
            rgba.push(255);
        }

        let img: RgbaImage =
            ImageBuffer::from_raw(width as u32, height as u32, rgba).ok_or_else(|| {
                "Failed to create image buffer from raw pixel data".to_string()
            })?;

        // Resize if wider than max_width.
        let img = if (width as u32) > config.max_width {
            let scale = config.max_width as f64 / width as f64;
            let new_height = (height as f64 * scale) as u32;
            image::imageops::resize(
                &img,
                config.max_width,
                new_height,
                image::imageops::FilterType::Triangle,
            )
        } else {
            img
        };

        let final_width = img.width();
        let final_height = img.height();

        // Encode as JPEG.
        let mut jpeg_buf: Vec<u8> = Vec::new();
        let mut encoder = JpegEncoder::new_with_quality(&mut jpeg_buf, config.quality);
        encoder
            .encode_image(&img)
            .map_err(|e| format!("JPEG encode failed: {}", e))?;

        let timestamp = chrono::Utc::now().timestamp_millis();

        Ok(Screenshot {
            timestamp,
            image_data: jpeg_buf,
            width: final_width,
            height: final_height,
            format: "jpeg".to_string(),
        })
    }
}

// ---------------------------------------------------------------------------
// macOS stub
// ---------------------------------------------------------------------------
#[cfg(target_os = "macos")]
mod platform {
    use super::*;

    pub fn capture_screen_impl(_config: &CaptureConfig) -> Result<Screenshot, String> {
        Err("Screen capture is not yet implemented on macOS".to_string())
    }
}

// ---------------------------------------------------------------------------
// Windows stub
// ---------------------------------------------------------------------------
#[cfg(target_os = "windows")]
mod platform {
    use super::*;

    pub fn capture_screen_impl(_config: &CaptureConfig) -> Result<Screenshot, String> {
        Err("Screen capture is not yet implemented on Windows".to_string())
    }
}

// ---------------------------------------------------------------------------
// Fallback for any other OS
// ---------------------------------------------------------------------------
#[cfg(not(any(target_os = "linux", target_os = "macos", target_os = "windows")))]
mod platform {
    use super::*;

    pub fn capture_screen_impl(_config: &CaptureConfig) -> Result<Screenshot, String> {
        Err("Screen capture is not supported on this platform".to_string())
    }
}
