/// OCR via Windows.Media.Ocr (built into Windows 10+, no external dependency).
///
/// Reads a JPEG file from disk and returns the recognized text.

use anyhow::{Context, Result};
use std::path::Path;

/// Extract text from an image file using Windows OCR.
/// Falls back gracefully on non-Windows or if WinRT is unavailable.
#[cfg(target_os = "windows")]
pub fn ocr_image_file(path: &Path) -> Result<String> {
    use windows::core::HSTRING;
    use windows::Globalization::Language;
    use windows::Graphics::Imaging::BitmapDecoder;
    use windows::Media::Ocr::OcrEngine;
    use windows::Storage::{FileAccessMode, StorageFile};

    // WinRT calls must be made on a thread with COM initialized.
    // We run this synchronously since it's called from a tokio blocking task.
    let path_str = path.to_string_lossy().to_string();

    // Load file via WinRT StorageFile
    let storage_file = StorageFile::GetFileFromPathAsync(&HSTRING::from(&path_str))
        .context("StorageFile::GetFileFromPathAsync")?
        .get()
        .context("Await GetFileFromPath")?;

    let stream = storage_file
        .OpenAsync(FileAccessMode::Read)
        .context("OpenAsync")?
        .get()
        .context("Await OpenAsync")?;

    let decoder = BitmapDecoder::CreateAsync(&stream)
        .context("BitmapDecoder::CreateAsync")?
        .get()
        .context("Await CreateAsync")?;

    let software_bitmap = decoder
        .GetSoftwareBitmapAsync()
        .context("GetSoftwareBitmapAsync")?
        .get()
        .context("Await GetSoftwareBitmap")?;

    // Try English OCR engine, fall back to user profile language
    let engine = Language::CreateLanguage(&HSTRING::from("en"))
        .ok()
        .and_then(|lang| OcrEngine::TryCreateFromLanguage(&lang).ok())
        .map(Ok)
        .unwrap_or_else(|| {
            OcrEngine::TryCreateFromUserProfileLanguages()
                .context("No OCR engine available for this language")
        })?;

    let result = engine
        .RecognizeAsync(&software_bitmap)
        .context("OcrEngine::RecognizeAsync")?
        .get()
        .context("Await RecognizeAsync")?;

    Ok(result.Text()?.to_string())
}

#[cfg(not(target_os = "windows"))]
pub fn ocr_image_file(_path: &Path) -> Result<String> {
    Ok(String::new())
}
