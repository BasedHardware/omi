pub mod dxgi;
pub mod ocr;
pub mod video_chunk;

use anyhow::Result;

/// A screenshot + OCR result ready for DB insertion.
#[derive(Debug, Clone)]
pub struct ScreenRecord {
    pub thumbnail_path: String,
    pub window_title: Option<String>,
    pub ocr_text: Option<String>,
}

/// Capture one frame + OCR it. Suitable for calling from a tokio blocking task.
pub fn capture_and_ocr() -> Result<Option<ScreenRecord>> {
    match dxgi::capture_screen_jpeg()? {
        None => Ok(None),
        Some(frame) => {
            let ocr_text = match ocr::ocr_image_file(&frame.path) {
                Ok(text) if !text.trim().is_empty() => {
                    tracing::info!("[CAPTURE] OCR: {} chars", text.len());
                    Some(text)
                }
                Ok(_) => None,
                Err(e) => {
                    tracing::warn!("[CAPTURE] OCR failed: {e}");
                    None
                }
            };
            Ok(Some(ScreenRecord {
                thumbnail_path: frame.path.to_string_lossy().into_owned(),
                window_title: frame.window_title,
                ocr_text,
            }))
        }
    }
}
