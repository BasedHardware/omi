pub mod dxgi;
pub mod ocr;
pub mod video_chunk;

use anyhow::Result;
use dxgi::FrameDeduplicator;

/// A screenshot + OCR result ready for DB insertion.
#[derive(Debug, Clone)]
pub struct ScreenRecord {
    pub thumbnail_path: String,
    pub window_title: Option<String>,
    pub ocr_text: Option<String>,
}

/// Stateful capture engine with frame deduplication.
pub struct CaptureEngine {
    dedup: FrameDeduplicator,
    video_encoder: Option<video_chunk::VideoChunkEncoder>,
}

impl CaptureEngine {
    pub fn new(enable_video: bool, ffmpeg_path: Option<String>) -> Self {
        let video_encoder = if enable_video {
            match video_chunk::VideoChunkEncoder::new(dxgi::screenshot_dir().join("videos"), ffmpeg_path) {
                Ok(enc) => {
                    tracing::info!("[CAPTURE] Video chunk encoder enabled");
                    Some(enc)
                }
                Err(e) => {
                    tracing::warn!("[CAPTURE] Video chunk encoder disabled: {e}");
                    None
                }
            }
        } else {
            None
        };
        Self {
            dedup: FrameDeduplicator::new(),
            video_encoder,
        }
    }

    /// Capture one frame, dedup, OCR, and optionally encode video.
    /// Returns None if the frame was skipped (dedup) or capture failed.
    pub fn capture_tick(&mut self, monitor_mode: &str) -> Result<Option<ScreenRecord>> {
        let frames = match monitor_mode {
            "all" => dxgi::capture_all_monitors()?,
            idx if idx.parse::<usize>().is_ok() => {
                let i = idx.parse::<usize>().unwrap();
                match dxgi::capture_monitor(i)? {
                    Some(f) => vec![f],
                    None => return Ok(None),
                }
            }
            _ => match dxgi::capture_screen_jpeg()? {
                Some(f) => vec![f],
                None => return Ok(None),
            },
        };

        let mut result: Option<ScreenRecord> = None;

        for frame in frames {
            if let Some(ref rgba) = frame.rgba_image {
                if self.dedup.should_skip(rgba) {
                    tracing::debug!(
                        "[CAPTURE] Skipped (dedup) — total skipped={}, captured={}",
                        self.dedup.skipped, self.dedup.captured
                    );
                    continue;
                }

                if let Some(ref mut enc) = self.video_encoder {
                    if let Err(e) = enc.add_frame(rgba) {
                        tracing::warn!("[CAPTURE] Video encode error: {e}");
                    }
                }
            }

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

            result = Some(ScreenRecord {
                thumbnail_path: frame.path.to_string_lossy().into_owned(),
                window_title: frame.window_title,
                ocr_text,
            });
        }

        Ok(result)
    }

    pub fn dedup_stats(&self) -> (u64, u64) {
        (self.dedup.skipped, self.dedup.captured)
    }

    pub fn finalize_video(&mut self) -> Option<std::path::PathBuf> {
        self.video_encoder.as_mut().and_then(|enc| {
            match enc.finalize_current() {
                Ok(p) => p,
                Err(e) => {
                    tracing::warn!("[CAPTURE] Video finalize error: {e}");
                    None
                }
            }
        })
    }
}

/// Simple one-shot capture (no dedup, no video). Backwards-compatible.
pub fn capture_and_ocr() -> Result<Option<ScreenRecord>> {
    match dxgi::capture_screen_jpeg()? {
        None => Ok(None),
        Some(frame) => {
            let ocr_text = match ocr::ocr_image_file(&frame.path) {
                Ok(text) if !text.trim().is_empty() => Some(text),
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
