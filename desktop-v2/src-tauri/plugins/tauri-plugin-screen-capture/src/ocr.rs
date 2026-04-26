#[cfg(not(target_os = "macos"))]
use kreuzberg_paddle_ocr::{OcrLite, OcrResult};
use serde::{Deserialize, Serialize};
#[cfg(not(target_os = "macos"))]
use std::path::Path;
#[cfg(not(target_os = "macos"))]
use std::sync::OnceLock;

/// Result of running OCR on a screenshot.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OcrTextResult {
    /// Full concatenated text from all detected regions, separated by newlines.
    pub full_text: String,
    /// Individual text blocks with bounding box coordinates and confidence scores.
    pub blocks: Vec<OcrTextBlock>,
}

/// A single detected text region.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OcrTextBlock {
    /// The recognized text.
    pub text: String,
    /// Confidence score (0.0 - 1.0).
    pub confidence: f32,
    /// Bounding box as [x_min, y_min, x_max, y_max].
    pub bbox: [u32; 4],
}

/// Global OCR engine instance. Initialized once on first use.
#[cfg(not(target_os = "macos"))]
static OCR_ENGINE: OnceLock<Result<OcrLite, String>> = OnceLock::new();

/// Get or initialize the OCR engine.
///
/// Looks for ONNX model files relative to the executable, then falls back
/// to the plugin source directory (for development).
#[cfg(not(target_os = "macos"))]
fn get_ocr_engine() -> Result<&'static OcrLite, String> {
    OCR_ENGINE
        .get_or_init(|| {
            let models_dir = find_models_dir()?;

            // Detection model is language-agnostic (finds text regions).
            let det_path = models_dir.join("ch_PP-OCRv4_det_infer.onnx");
            let cls_path = models_dir.join("ch_ppocr_mobile_v2.0_cls_train.onnx");
            // Latin recognition model covers English + Portuguese + all Latin-script languages.
            let rec_path = models_dir.join("latin_rec.onnx");
            let dict_path = models_dir.join("latin_dict.txt");

            for (name, path) in [
                ("detection", &det_path),
                ("classification", &cls_path),
                ("recognition", &rec_path),
                ("dictionary", &dict_path),
            ] {
                if !path.exists() {
                    return Err(format!(
                        "OCR {} model not found at {}",
                        name,
                        path.display()
                    ));
                }
            }

            let mut ocr = OcrLite::new();

            tracing::info!("Loading OCR models from {}", models_dir.display());

            ocr.init_models_with_dict(
                det_path.to_str().unwrap(),
                cls_path.to_str().unwrap(),
                rec_path.to_str().unwrap(),
                dict_path.to_str().unwrap(),
                2, // thread count for inference
            )
            .map_err(|e| format!("Failed to initialize OCR models: {}", e))?;

            tracing::info!("OCR models loaded successfully");

            Ok(ocr)
        })
        .as_ref()
        .map_err(|e| e.clone())
}

/// Search for the models directory in several locations.
#[cfg(not(target_os = "macos"))]
fn find_models_dir() -> Result<std::path::PathBuf, String> {
    // 1. Check next to executable (production: bundled with app)
    if let Ok(exe) = std::env::current_exe() {
        if let Some(exe_dir) = exe.parent() {
            let candidate = exe_dir.join("models");
            if candidate.is_dir() {
                return Ok(candidate);
            }
            // macOS bundle: Contents/MacOS/../Resources/models
            let mac_candidate = exe_dir.join("../Resources/models");
            if mac_candidate.is_dir() {
                return Ok(mac_candidate);
            }
        }
    }

    // 2. Check in the plugin source directory (development mode)
    let dev_path = Path::new(env!("CARGO_MANIFEST_DIR")).join("models");
    if dev_path.is_dir() {
        return Ok(dev_path);
    }

    Err("Could not find OCR models directory".to_string())
}

/// Run OCR on a JPEG-encoded image buffer.
///
/// macOS uses Apple's Vision framework (`VNRecognizeTextRequest`) — it's
/// trained on screen-rendered glyphs and crushes PaddleOCR on UI text.
/// Other platforms fall back to the bundled PaddleOCR ONNX models.
pub fn extract_text(jpeg_data: &[u8]) -> Result<OcrTextResult, String> {
    #[cfg(target_os = "macos")]
    {
        return crate::ocr_vision::extract_text(jpeg_data);
    }
    #[cfg(not(target_os = "macos"))]
    extract_text_paddle(jpeg_data)
}

/// PaddleOCR fallback used on Linux/Windows where we don't have a system
/// OCR engine.
#[cfg(not(target_os = "macos"))]
fn extract_text_paddle(jpeg_data: &[u8]) -> Result<OcrTextResult, String> {
    let engine = get_ocr_engine()?;

    // Decode JPEG to RGB image.
    let img = image::load_from_memory_with_format(jpeg_data, image::ImageFormat::Jpeg)
        .map_err(|e| format!("Failed to decode image for OCR: {}", e))?
        .to_rgb8();

    // Run OCR detection.
    // Parameters tuned for screen capture:
    // - padding: 10 (small padding for screen content)
    // - max_side_len: 1920 (typical screen width, avoids upscaling)
    // - box_score_thresh: 0.5 (standard threshold)
    // - box_thresh: 0.3 (standard)
    // - un_clip_ratio: 1.6 (standard)
    // - do_angle: false (screens are always upright)
    // - most_angle: false
    let result: OcrResult = engine
        .detect(
            &img,
            10,    // padding
            1920,  // max_side_len
            0.5,   // box_score_thresh
            0.3,   // box_thresh
            1.6,   // un_clip_ratio
            false, // do_angle — screens are always upright
            false, // most_angle
        )
        .map_err(|e| format!("OCR detection failed: {}", e))?;

    // Convert to our result type.
    let blocks: Vec<OcrTextBlock> = result
        .text_blocks
        .iter()
        .filter(|b| !b.text.trim().is_empty())
        .map(|b| {
            // Compute axis-aligned bounding box from the 4-point polygon.
            let x_min = b.box_points.iter().map(|p| p.x).min().unwrap_or(0);
            let y_min = b.box_points.iter().map(|p| p.y).min().unwrap_or(0);
            let x_max = b.box_points.iter().map(|p| p.x).max().unwrap_or(0);
            let y_max = b.box_points.iter().map(|p| p.y).max().unwrap_or(0);

            OcrTextBlock {
                text: b.text.clone(),
                confidence: b.text_score,
                bbox: [x_min, y_min, x_max, y_max],
            }
        })
        .collect();

    let full_text = blocks
        .iter()
        .map(|b| b.text.as_str())
        .collect::<Vec<_>>()
        .join("\n");

    Ok(OcrTextResult { full_text, blocks })
}
