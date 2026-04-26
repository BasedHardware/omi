use serde::{Deserialize, Serialize};

/// Origin of a display in global screen coordinates (AppKit bottom-left origin,
/// points).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DisplayOriginPt {
    pub x: f64,
    pub y: f64,
}

/// Size of a display in points.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DisplaySizePt {
    pub w: f64,
    pub h: f64,
}

/// Display geometry metadata attached to every `take_screenshot_with_ocr`
/// response.  Lets the Companion overlay do precise coordinate mapping from
/// Gemini image-space → overlay-window-local points without any additional
/// IPC round-trips.
///
/// All point-space values use the AppKit coordinate system (bottom-left origin,
/// points).  To convert to screen coordinates for an NSWindow, add
/// `display_origin_pt.y` to the y component (AppKit bottom-up).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DisplayMetadata {
    /// `CGDirectDisplayID` of the captured display.
    pub display_id: u32,
    /// Width of the JPEG returned by the plugin (after any downscale).
    pub capture_width_px: u32,
    /// Height of the JPEG returned by the plugin (after any downscale).
    pub capture_height_px: u32,
    /// Native pixel width of the display (before downscale).
    pub display_width_px: u32,
    /// Native pixel height of the display (before downscale).
    pub display_height_px: u32,
    /// `NSScreen.backingScaleFactor` for this display (e.g. 2.0 for Retina).
    pub display_scale_factor: f64,
    /// Display origin in global AppKit points (bottom-left origin).
    pub display_origin_pt: DisplayOriginPt,
    /// Display size in points.
    pub display_size_pt: DisplaySizePt,
}

/// A single captured screenshot.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Screenshot {
    /// Unix timestamp in milliseconds when the screenshot was taken.
    pub timestamp: i64,
    /// Raw image data (JPEG-encoded bytes).
    pub image_data: Vec<u8>,
    /// Width in pixels.
    pub width: u32,
    /// Height in pixels.
    pub height: u32,
    /// Image format identifier (e.g. "jpeg").
    pub format: String,
    /// `CGDirectDisplayID` of the display that was captured. `0` on
    /// platforms that do not expose display IDs (Linux, Windows).
    pub display_id: u32,
    /// Native pixel resolution of the captured display.
    pub native_width: u32,
    pub native_height: u32,
}

/// Information about the currently active (focused) window.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ActiveWindow {
    /// The name of the application owning the window.
    pub app_name: String,
    /// The title of the window.
    pub window_title: String,
    /// Process ID of the owning application.
    pub pid: u32,
}

/// Configuration for screen capture.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CaptureConfig {
    /// Interval between captures in milliseconds.
    #[serde(default = "default_interval_ms")]
    pub interval_ms: u64,
    /// JPEG quality (1-100).
    #[serde(default = "default_quality")]
    pub quality: u8,
    /// Maximum width in pixels; images wider than this will be scaled down.
    #[serde(default = "default_max_width")]
    pub max_width: u32,
}

impl Default for CaptureConfig {
    fn default() -> Self {
        Self {
            interval_ms: default_interval_ms(),
            quality: default_quality(),
            max_width: default_max_width(),
        }
    }
}

fn default_interval_ms() -> u64 {
    3000
}

fn default_quality() -> u8 {
    80
}

fn default_max_width() -> u32 {
    3000
}

/// Runtime state for the capture service.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CaptureState {
    /// Whether continuous capture is currently running.
    pub is_capturing: bool,
    /// Total number of screenshots taken since capture started.
    pub screenshot_count: u64,
    /// Unix timestamp (ms) of the most recent capture, if any.
    pub last_capture: Option<i64>,
}

impl Default for CaptureState {
    fn default() -> Self {
        Self {
            is_capturing: false,
            screenshot_count: 0,
            last_capture: None,
        }
    }
}
