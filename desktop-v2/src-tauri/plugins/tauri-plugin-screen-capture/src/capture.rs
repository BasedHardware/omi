use crate::models::{CaptureConfig, DisplayMetadata, DisplayOriginPt, DisplaySizePt, Screenshot};
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

/// Build a `DisplayMetadata` value for the given screenshot.
///
/// On macOS, looks up the `NSScreen` whose `NSScreenNumber` device-description
/// key matches `screenshot.display_id`, then reads `backingScaleFactor` and
/// `frame`.  Done once per capture on the calling (blocking) thread — no
/// caching because display arrangement can change between captures.
///
/// On other platforms returns a sensible default derived from the capture
/// dimensions alone (no display ID, scale factor 1.0, origin at origin).
pub fn display_metadata_for_screenshot(screenshot: &Screenshot) -> DisplayMetadata {
    platform::display_metadata_impl(screenshot)
}

/// Downscale an existing JPEG to a smaller JPEG with a given quality.
///
/// Used by the OCR pipeline to keep the high-resolution capture for text
/// extraction while persisting a lighter copy to disk. If `max_width` is
/// 0 or already ≥ the source width, the original bytes are returned
/// unchanged (with the original dimensions) — no decode, no re-encode.
pub fn resize_jpeg(
    jpeg_data: &[u8],
    max_width: u32,
    quality: u8,
) -> Result<(Vec<u8>, u32, u32), String> {
    use image::codecs::jpeg::JpegEncoder;

    // Cheap dimension peek so we can short-circuit when no resize is needed.
    let (src_w, src_h) = image::ImageReader::with_format(
        std::io::Cursor::new(jpeg_data),
        image::ImageFormat::Jpeg,
    )
    .into_dimensions()
    .map_err(|e| format!("resize_jpeg: failed to read dimensions: {}", e))?;

    if max_width == 0 || src_w <= max_width {
        return Ok((jpeg_data.to_vec(), src_w, src_h));
    }

    // Full decode + bilinear resize + re-encode.
    let img = image::load_from_memory_with_format(jpeg_data, image::ImageFormat::Jpeg)
        .map_err(|e| format!("resize_jpeg: decode failed: {}", e))?
        .to_rgb8();

    let scale = max_width as f64 / src_w as f64;
    let new_h = (src_h as f64 * scale).round().max(1.0) as u32;
    let resized = image::imageops::resize(
        &img,
        max_width,
        new_h,
        image::imageops::FilterType::Triangle,
    );

    let mut out: Vec<u8> = Vec::new();
    JpegEncoder::new_with_quality(&mut out, quality)
        .encode_image(&resized)
        .map_err(|e| format!("resize_jpeg: encode failed: {}", e))?;

    Ok((out, max_width, new_h))
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

        // Resize if wider than max_width. `max_width == 0` means no downscale.
        let img = if config.max_width > 0 && (width as u32) > config.max_width {
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
            display_id: 0,
            native_width: width as u32,
            native_height: height as u32,
        })
    }

    pub fn display_metadata_impl(screenshot: &Screenshot) -> DisplayMetadata {
        // Linux has no display-ID concept; return a minimal metadata block.
        DisplayMetadata {
            display_id: 0,
            capture_width_px: screenshot.width,
            capture_height_px: screenshot.height,
            display_width_px: screenshot.native_width,
            display_height_px: screenshot.native_height,
            display_scale_factor: 1.0,
            display_origin_pt: DisplayOriginPt { x: 0.0, y: 0.0 },
            display_size_pt: DisplaySizePt {
                w: screenshot.native_width as f64,
                h: screenshot.native_height as f64,
            },
        }
    }
}

// ---------------------------------------------------------------------------
// macOS implementation (Core Graphics)
// ---------------------------------------------------------------------------
//
// Uses `CGDisplayCreateImage` against the main display. This API is marked
// deprecated as of macOS 14 in favour of ScreenCaptureKit, but it still
// returns a valid image through macOS 26 provided the app holds the Screen
// Recording entitlement / TCC grant. Without that grant, the call returns a
// non-null image whose pixels are entirely the desktop wallpaper — the
// caller will see "captures" but no real content. We don't try to detect
// that here; the onboarding flow is responsible for surfacing the prompt.
#[cfg(target_os = "macos")]
mod platform {
    use super::*;
    use core_graphics::display::{CGDisplay, CGMainDisplayID};
    use core_graphics::event::CGEvent;
    use core_graphics::event_source::{CGEventSource, CGEventSourceStateID};
    use core_graphics::image::CGImage;
    use image::codecs::jpeg::JpegEncoder;
    use image::{ImageBuffer, RgbaImage};

    /// Return the CGDirectDisplayID of the display the cursor is currently on,
    /// or `None` if we can't determine it.
    ///
    /// Uses `CGEvent` (thread-safe, unlike `NSEvent::mouseLocation`) plus
    /// `CGGetDisplaysWithPoint` via `CGDisplay::active_displays` + bounds
    /// containment.  This intentionally matches the heuristic used by the
    /// Companion buddy positioner so the screenshot follows the cursor across
    /// displays exactly the way the buddy does.
    fn cursor_display_id() -> Option<u32> {
        let source = CGEventSource::new(CGEventSourceStateID::HIDSystemState).ok()?;
        let event = CGEvent::new(source).ok()?;
        let loc = event.location(); // CGPoint, top-origin global coords (logical points)

        let displays = CGDisplay::active_displays().ok()?;
        for id in displays {
            let bounds = CGDisplay::new(id).bounds();
            if loc.x >= bounds.origin.x
                && loc.x < bounds.origin.x + bounds.size.width
                && loc.y >= bounds.origin.y
                && loc.y < bounds.origin.y + bounds.size.height
            {
                return Some(id);
            }
        }
        None
    }

    pub fn capture_screen_impl(config: &CaptureConfig) -> Result<Screenshot, String> {
        // CGImage is `!Send`; everything stays on this thread inside
        // `tokio::task::spawn_blocking` (the caller wraps us in one).
        //
        // Pick the display the cursor is currently on so the screenshot and
        // the Companion overlay describe the same screen the user is looking
        // at. `CGMainDisplayID()` (display with menu bar) often differs from
        // the display the cursor is on in multi-monitor setups, which made
        // Gemini's points land "almost there" on the wrong screen.
        let display_id = cursor_display_id().unwrap_or_else(|| unsafe { CGMainDisplayID() });
        let cg_image: CGImage = CGDisplay::new(display_id)
            .image()
            .ok_or_else(|| {
                "CGDisplayCreateImage returned null — Screen Recording permission missing?"
                    .to_string()
            })?;

        let width = cg_image.width() as u32;
        let height = cg_image.height() as u32;
        let bytes_per_row = cg_image.bytes_per_row() as usize;
        let bits_per_pixel = cg_image.bits_per_pixel();

        if bits_per_pixel != 32 {
            return Err(format!(
                "Unexpected bits_per_pixel from CGImage: {} (expected 32)",
                bits_per_pixel
            ));
        }

        let data = cg_image.data();
        let raw: &[u8] = data.bytes();

        // CGImage on macOS is little-endian BGRA in practice. Repack to
        // straight RGBA for the `image` crate. We can't trust `raw.len()`
        // to equal width*height*4 because of row stride padding.
        let mut rgba = Vec::with_capacity((width as usize) * (height as usize) * 4);
        for y in 0..height as usize {
            let row_start = y * bytes_per_row;
            for x in 0..width as usize {
                let i = row_start + x * 4;
                let b = raw[i];
                let g = raw[i + 1];
                let r = raw[i + 2];
                let a = raw[i + 3];
                rgba.push(r);
                rgba.push(g);
                rgba.push(b);
                rgba.push(a);
            }
        }

        let img: RgbaImage = ImageBuffer::from_raw(width, height, rgba)
            .ok_or_else(|| "Failed to build ImageBuffer from CGImage data".to_string())?;

        // Resize if wider than max_width. `max_width == 0` is the explicit
        // "no downscale" sentinel — used by the Rewind path so OCR runs
        // against the screen's native pixel grid (downscaling to 1280px
        // shredded enough detail to merge adjacent text blocks).
        let img = if config.max_width > 0 && width > config.max_width {
            let scale = config.max_width as f64 / width as f64;
            let new_height = (height as f64 * scale).round() as u32;
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
            display_id,
            native_width: width,
            native_height: height,
        })
    }

    pub fn display_metadata_impl(screenshot: &Screenshot) -> DisplayMetadata {
        // Derive backing scale factor from the active display mode when
        // possible: pixel_width / point_width. Falls back to 2.0 (the most
        // common Retina value) if the mode lookup fails — proper
        // NSScreen-based lookup is a Phase 5 polish item.
        let cg = CGDisplay::new(screenshot.display_id);
        let (scale, point_w, point_h) = cg
            .display_mode()
            .map(|m| {
                let px_w = m.pixel_width() as f64;
                let pt_w = m.width() as f64;
                let pt_h = m.height() as f64;
                let s = if pt_w > 0.0 { px_w / pt_w } else { 2.0 };
                (s, pt_w, pt_h)
            })
            .unwrap_or((
                2.0,
                screenshot.native_width as f64 / 2.0,
                screenshot.native_height as f64 / 2.0,
            ));

        let bounds = cg.bounds();
        DisplayMetadata {
            display_id: screenshot.display_id,
            capture_width_px: screenshot.width,
            capture_height_px: screenshot.height,
            display_width_px: screenshot.native_width,
            display_height_px: screenshot.native_height,
            display_scale_factor: scale,
            display_origin_pt: DisplayOriginPt {
                x: bounds.origin.x,
                y: bounds.origin.y,
            },
            display_size_pt: DisplaySizePt {
                w: point_w,
                h: point_h,
            },
        }
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

    pub fn display_metadata_impl(screenshot: &Screenshot) -> DisplayMetadata {
        DisplayMetadata {
            display_id: 0,
            capture_width_px: screenshot.width,
            capture_height_px: screenshot.height,
            display_width_px: screenshot.native_width,
            display_height_px: screenshot.native_height,
            display_scale_factor: 1.0,
            display_origin_pt: DisplayOriginPt { x: 0.0, y: 0.0 },
            display_size_pt: DisplaySizePt {
                w: screenshot.native_width as f64,
                h: screenshot.native_height as f64,
            },
        }
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

    pub fn display_metadata_impl(screenshot: &Screenshot) -> DisplayMetadata {
        DisplayMetadata {
            display_id: 0,
            capture_width_px: screenshot.width,
            capture_height_px: screenshot.height,
            display_width_px: screenshot.native_width,
            display_height_px: screenshot.native_height,
            display_scale_factor: 1.0,
            display_origin_pt: DisplayOriginPt { x: 0.0, y: 0.0 },
            display_size_pt: DisplaySizePt {
                w: screenshot.native_width as f64,
                h: screenshot.native_height as f64,
            },
        }
    }
}
