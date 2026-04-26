mod active_window;
mod capture;
mod database;
mod dhash;
mod models;
mod ocr;
#[cfg(target_os = "macos")]
mod ocr_vision;

use database::{CompanionSession, CompanionSessionInput, CompanionSessionPatch, EmbeddingBacklogItem, RewindDatabase, ScreenshotRow, SemanticHit};
use models::{CaptureConfig, CaptureState, DisplayMetadata};
use ocr::OcrTextBlock;
use std::sync::{Arc, Mutex};
use tauri::{
    plugin::{Builder, TauriPlugin},
    Manager, Runtime, State,
};

// ---------------------------------------------------------------------------
// Managed state
// ---------------------------------------------------------------------------

/// Managed state for the screen-capture plugin.
struct ScreenCaptureState {
    inner: Mutex<CaptureState>,
}

/// Managed state for the Rewind SQLite database.
struct DatabaseState {
    db: Arc<RewindDatabase>,
}

// ---------------------------------------------------------------------------
// Response types
// ---------------------------------------------------------------------------

/// Response from take_screenshot_with_ocr containing both image and text.
#[derive(serde::Serialize)]
struct ScreenshotWithOcr {
    /// Base64-encoded JPEG image data.
    image: String,
    /// Full OCR text extracted from the screenshot.
    ocr_text: String,
    /// Per-block OCR detections with image-pixel bounding boxes. Used by the
    /// Companion pipeline to snap Gemini's approximate label coordinates to
    /// the exact center of matching on-screen text. Empty when OCR was
    /// skipped (dHash dedup) or failed.
    ocr_blocks: Vec<OcrTextBlock>,
    /// Row ID of the persisted record, if saving succeeded.
    db_id: Option<i64>,
    /// Captured-display metadata so the Companion overlay can convert
    /// Gemini's image-pixel points to overlay-window-local CSS points.
    /// Set in both the dHash-dedup early-return and the full path; the
    /// dedup path uses the storage-resize dimensions for capture_*_px.
    display: DisplayMetadata,
}

// ---------------------------------------------------------------------------
// Existing commands (unchanged behaviour)
// ---------------------------------------------------------------------------

/// Take a single screenshot and return it as a base64-encoded JPEG string.
#[tauri::command]
async fn take_screenshot(
    state: State<'_, ScreenCaptureState>,
    config: Option<CaptureConfig>,
) -> Result<String, String> {
    let config = config.unwrap_or_default();

    let screenshot =
        tokio::task::spawn_blocking(move || capture::capture_screen(&config))
            .await
            .map_err(|e| format!("capture task panicked: {}", e))??;

    if let Ok(mut s) = state.inner.lock() {
        s.screenshot_count += 1;
        s.last_capture = Some(screenshot.timestamp);
    }

    use base64::Engine;
    let encoded = base64::engine::general_purpose::STANDARD.encode(&screenshot.image_data);
    Ok(encoded)
}

/// Take a screenshot and run OCR on it, then persist to the database.
/// Returns image (base64), OCR text, and the new database row ID.
///
/// Performs dHash deduplication: if the new frame is visually identical to the
/// previous one (≤ 5 bits of difference), OCR and DB insertion are skipped and
/// `db_id` is returned as `None`.
#[tauri::command]
async fn take_screenshot_with_ocr(
    state: State<'_, ScreenCaptureState>,
    db_state: State<'_, DatabaseState>,
    config: Option<CaptureConfig>,
) -> Result<ScreenshotWithOcr, String> {
    let config = config.unwrap_or_default();

    // Capture is always native-resolution: dHash + OCR work better with the
    // raw pixel grid, so we ignore `config.max_width` here. The user-facing
    // `max_width` is interpreted as the *storage* cap and applied below
    // after OCR has already extracted text from the high-res image.
    let native_config = CaptureConfig {
        max_width: 0,
        ..config.clone()
    };
    let storage_max_width = config.max_width;
    let storage_quality = config.quality;

    let screenshot =
        tokio::task::spawn_blocking(move || capture::capture_screen(&native_config))
            .await
            .map_err(|e| format!("capture task panicked: {}", e))??;

    if let Ok(mut s) = state.inner.lock() {
        s.screenshot_count += 1;
        s.last_capture = Some(screenshot.timestamp);
    }

    // --- dHash deduplication ---
    let image_data_for_hash = screenshot.image_data.clone();
    let new_hash = tokio::task::spawn_blocking(move || dhash::compute_dhash(&image_data_for_hash))
        .await
        .map_err(|e| format!("dhash task panicked: {}", e))?
        .ok(); // None if decode failed — skip dedup in that case

    if let Some(hash) = new_hash {
        let db_for_dedup = Arc::clone(&db_state.db);
        let prev_hash = tokio::task::spawn_blocking(move || db_for_dedup.get_latest_dhash())
            .await
            .map_err(|e| format!("dhash lookup panicked: {}", e))?
            .ok()
            .flatten();

        if let Some(prev_hex) = prev_hash {
            if let Ok(prev) = dhash::hex_to_dhash(&prev_hex) {
                let distance = dhash::hamming_distance(hash, prev);
                tracing::info!(
                    "dHash distance from previous frame: {} (threshold: {})",
                    distance,
                    dhash::DEDUP_THRESHOLD
                );
                if dhash::is_duplicate(hash, prev) {
                    tracing::info!("Frame skipped (dHash duplicate)");
                    // Return the storage-sized version so the UI gets a small
                    // payload (the captured frame is full resolution; sending
                    // megabytes of base64 over IPC for a duplicate would be
                    // wasteful). OCR and DB persistence are skipped — the
                    // Companion grounding pipeline gracefully handles empty
                    // ocr_blocks by falling back to Gemini's pixel coords.
                    let (storage_bytes, storage_w, storage_h) = capture::resize_jpeg(
                        &screenshot.image_data,
                        storage_max_width,
                        storage_quality,
                    )
                    .unwrap_or_else(|e| {
                        tracing::warn!("dedup-path resize failed: {} (returning native bytes)", e);
                        (screenshot.image_data.clone(), screenshot.width, screenshot.height)
                    });
                    let mut display = capture::display_metadata_for_screenshot(&screenshot);
                    display.capture_width_px = storage_w;
                    display.capture_height_px = storage_h;
                    use base64::Engine;
                    let encoded = base64::engine::general_purpose::STANDARD.encode(&storage_bytes);
                    return Ok(ScreenshotWithOcr {
                        image: encoded,
                        ocr_text: String::new(),
                        ocr_blocks: Vec::new(),
                        db_id: None,
                        display,
                    });
                }
            }
        }
    }

    let dhash_hex = new_hash.map(dhash::dhash_to_hex);

    // Convert unix millis timestamp to ISO-8601 for consistent storage and JS compatibility.
    let ts_iso = chrono::DateTime::from_timestamp_millis(screenshot.timestamp)
        .map(|dt| dt.to_rfc3339_opts(chrono::SecondsFormat::Millis, true))
        .unwrap_or_else(|| chrono::Utc::now().to_rfc3339_opts(chrono::SecondsFormat::Millis, true));

    // --- OCR (blocking — involves ONNX inference) ---
    let image_data_for_ocr = screenshot.image_data.clone();
    let ocr_result = tokio::task::spawn_blocking(move || ocr::extract_text(&image_data_for_ocr))
        .await
        .map_err(|e| format!("OCR task panicked: {}", e))?;

    let (ocr_text, ocr_blocks_native, ocr_blocks_json) = match ocr_result {
        Ok(result) => {
            tracing::debug!(
                "OCR extracted {} blocks, {} chars",
                result.blocks.len(),
                result.full_text.len()
            );
            let blocks_json = serde_json::to_string(&result.blocks).ok();
            (result.full_text, result.blocks, blocks_json)
        }
        Err(e) => {
            tracing::warn!("OCR failed: {}", e);
            (String::new(), Vec::new(), None)
        }
    };

    // --- Get active window info for DB metadata ---
    let window_info = tokio::task::spawn_blocking(active_window::get_active_window)
        .await
        .map_err(|e| format!("active window task panicked: {}", e))?
        .unwrap_or_else(|_| models::ActiveWindow {
            app_name: String::new(),
            window_title: String::new(),
            pid: 0,
        });

    // Capture display metadata BEFORE we move screenshot.image_data — the
    // helper needs an intact &Screenshot for NSScreen lookup.
    let mut display = capture::display_metadata_for_screenshot(&screenshot);

    // --- Downscale for storage / return payload ---
    // OCR is done; we don't need the high-res bytes any further. Drop to
    // the user-configured storage cap so the SQLite blob and IPC payload
    // stay small. Falls back to the native bytes if the resize fails for
    // any reason.
    let native_bytes = screenshot.image_data;
    let (storage_bytes, storage_width, storage_height) = {
        let bytes_for_resize = native_bytes.clone();
        tokio::task::spawn_blocking(move || {
            capture::resize_jpeg(&bytes_for_resize, storage_max_width, storage_quality)
        })
        .await
        .map_err(|e| format!("resize task panicked: {}", e))?
        .unwrap_or_else(|e| {
            tracing::warn!("storage-resize failed: {} (storing native bytes)", e);
            (native_bytes.clone(), screenshot.width, screenshot.height)
        })
    };
    drop(native_bytes);

    // --- Persist to database ---
    let db = Arc::clone(&db_state.db);
    let image_data_for_db = storage_bytes.clone();
    let ts_for_db = ts_iso.clone();
    let ocr_text_clone = ocr_text.clone();
    let ocr_blocks_clone = ocr_blocks_json.clone();
    let dhash_clone = dhash_hex.clone();
    let app_name = window_info.app_name.clone();
    let win_title = window_info.window_title.clone();

    let db_id = tokio::task::spawn_blocking(move || {
        db.insert_screenshot(
            &ts_for_db,
            &app_name,
            &win_title,
            &image_data_for_db,
            if ocr_text_clone.is_empty() { None } else { Some(ocr_text_clone.as_str()) },
            ocr_blocks_clone.as_deref(),
            dhash_clone.as_deref(),
            storage_width,
            storage_height,
        )
    })
    .await
    .map_err(|e| format!("db insert task panicked: {}", e))
    .and_then(|res| res.map_err(|e| format!("db insert failed: {}", e)))
    .map(Some)
    .unwrap_or_else(|e| {
        tracing::error!("Failed to persist screenshot: {}", e);
        None
    });

    use base64::Engine;
    let encoded = base64::engine::general_purpose::STANDARD.encode(&storage_bytes);

    let native_w = display.capture_width_px;
    let native_h = display.capture_height_px;
    display.capture_width_px = storage_width;
    display.capture_height_px = storage_height;

    // OCR ran against the native-resolution screenshot; scale bboxes down to
    // match the resized JPEG we're returning so TS coordinate math stays in
    // a single image-pixel space.
    let ocr_blocks = if native_w > 0 && native_h > 0 && (native_w != storage_width || native_h != storage_height) {
        let sx = storage_width as f64 / native_w as f64;
        let sy = storage_height as f64 / native_h as f64;
        ocr_blocks_native
            .into_iter()
            .map(|b| OcrTextBlock {
                text: b.text,
                confidence: b.confidence,
                bbox: [
                    (b.bbox[0] as f64 * sx).round() as u32,
                    (b.bbox[1] as f64 * sy).round() as u32,
                    (b.bbox[2] as f64 * sx).round() as u32,
                    (b.bbox[3] as f64 * sy).round() as u32,
                ],
            })
            .collect()
    } else {
        ocr_blocks_native
    };

    Ok(ScreenshotWithOcr { image: encoded, ocr_text, ocr_blocks, db_id, display })
}

/// Start continuous screen capture.
#[tauri::command]
async fn start_screen_capture(
    state: State<'_, ScreenCaptureState>,
    config: Option<CaptureConfig>,
) -> Result<(), String> {
    {
        let s = state
            .inner
            .lock()
            .map_err(|_| "Failed to lock state".to_string())?;
        if s.is_capturing {
            return Err("Screen capture is already running".to_string());
        }
    }

    let config = config.unwrap_or_default();

    {
        let mut s = state
            .inner
            .lock()
            .map_err(|_| "Failed to lock state".to_string())?;
        s.is_capturing = true;
        s.screenshot_count = 0;
        s.last_capture = None;
    }

    let (tx, rx) = std::sync::mpsc::channel();

    std::thread::Builder::new()
        .name("screen-capture-loop".into())
        .spawn(move || {
            capture::start_continuous_capture(config, tx);
        })
        .map_err(|e| format!("Failed to spawn capture thread: {}", e))?;

    std::thread::Builder::new()
        .name("screen-capture-recv".into())
        .spawn(move || {
            while let Ok(screenshot) = rx.recv() {
                tracing::debug!(
                    "Captured screenshot: {}x{} ({} bytes) at ts={}",
                    screenshot.width,
                    screenshot.height,
                    screenshot.image_data.len(),
                    screenshot.timestamp,
                );
            }
        })
        .map_err(|e| format!("Failed to spawn receiver thread: {}", e))?;

    tracing::info!("Continuous screen capture started");
    Ok(())
}

/// Stop continuous screen capture.
#[tauri::command]
async fn stop_screen_capture(state: State<'_, ScreenCaptureState>) -> Result<(), String> {
    capture::stop_continuous_capture();

    if let Ok(mut s) = state.inner.lock() {
        s.is_capturing = false;
    }

    tracing::info!("Continuous screen capture stopped");
    Ok(())
}

/// Return information about the currently active (focused) window.
#[tauri::command]
async fn get_active_window_info() -> Result<models::ActiveWindow, String> {
    tokio::task::spawn_blocking(active_window::get_active_window)
        .await
        .map_err(|e| format!("active window task panicked: {}", e))?
}

/// Return the current capture state.
#[tauri::command]
async fn get_screen_capture_state(
    state: State<'_, ScreenCaptureState>,
) -> Result<CaptureState, String> {
    let mut s = state
        .inner
        .lock()
        .map_err(|_| "Failed to lock state".to_string())?;
    s.is_capturing = capture::is_capturing();
    Ok(s.clone())
}

// ---------------------------------------------------------------------------
// New database commands
// ---------------------------------------------------------------------------

/// Save a screenshot (base64-encoded image) along with metadata to the database.
/// Returns the new row ID.
#[tauri::command]
async fn save_screenshot(
    db_state: State<'_, DatabaseState>,
    timestamp: String,
    app_name: String,
    window_title: String,
    image_b64: String,
    ocr_text: Option<String>,
    ocr_blocks_json: Option<String>,
    dhash: Option<String>,
    width: u32,
    height: u32,
) -> Result<i64, String> {
    use base64::Engine;
    let image_data = base64::engine::general_purpose::STANDARD
        .decode(&image_b64)
        .map_err(|e| format!("Failed to decode base64 image: {}", e))?;

    let db = Arc::clone(&db_state.db);
    tokio::task::spawn_blocking(move || {
        db.insert_screenshot(
            &timestamp,
            &app_name,
            &window_title,
            &image_data,
            ocr_text.as_deref(),
            ocr_blocks_json.as_deref(),
            dhash.as_deref(),
            width,
            height,
        )
    })
    .await
    .map_err(|e| format!("db task panicked: {}", e))?
    .map_err(|e| format!("db insert failed: {}", e))
}

/// Full-text search over screenshot OCR text, window titles, and app names.
#[tauri::command]
async fn search_screenshots(
    db_state: State<'_, DatabaseState>,
    query: String,
    limit: Option<u32>,
) -> Result<Vec<ScreenshotRow>, String> {
    let limit = limit.unwrap_or(50);
    let db = Arc::clone(&db_state.db);
    tokio::task::spawn_blocking(move || db.search_fts(&query, limit))
        .await
        .map_err(|e| format!("db task panicked: {}", e))?
        .map_err(|e| format!("search failed: {}", e))
}

/// Return a paginated list of recent screenshots (metadata only, no image bytes).
#[tauri::command]
async fn get_recent_screenshots(
    db_state: State<'_, DatabaseState>,
    limit: Option<u32>,
    offset: Option<u32>,
) -> Result<Vec<ScreenshotRow>, String> {
    let limit = limit.unwrap_or(50);
    let offset = offset.unwrap_or(0);
    let db = Arc::clone(&db_state.db);
    tokio::task::spawn_blocking(move || db.get_recent(limit, offset))
        .await
        .map_err(|e| format!("db task panicked: {}", e))?
        .map_err(|e| format!("get_recent failed: {}", e))
}

/// Return the raw image data for a specific screenshot as a base64-encoded string.
#[tauri::command]
async fn get_screenshot_image(
    db_state: State<'_, DatabaseState>,
    id: i64,
) -> Result<Option<String>, String> {
    let db = Arc::clone(&db_state.db);
    let bytes = tokio::task::spawn_blocking(move || db.get_image_data(id))
        .await
        .map_err(|e| format!("db task panicked: {}", e))?
        .map_err(|e| format!("get_image_data failed: {}", e))?;

    use base64::Engine;
    Ok(bytes.map(|b| base64::engine::general_purpose::STANDARD.encode(&b)))
}

/// Return metadata for a single screenshot by ID.
#[tauri::command]
async fn get_screenshot_by_id(
    db_state: State<'_, DatabaseState>,
    id: i64,
) -> Result<Option<ScreenshotRow>, String> {
    let db = Arc::clone(&db_state.db);
    tokio::task::spawn_blocking(move || db.get_screenshot(id))
        .await
        .map_err(|e| format!("db task panicked: {}", e))?
        .map_err(|e| format!("get_screenshot failed: {}", e))
}

/// Delete all screenshots older than the given timestamp string.
/// Returns the number of deleted rows.
#[tauri::command]
async fn delete_old_screenshots(
    db_state: State<'_, DatabaseState>,
    before_timestamp: String,
) -> Result<u64, String> {
    let db = Arc::clone(&db_state.db);
    tokio::task::spawn_blocking(move || db.delete_older_than(&before_timestamp))
        .await
        .map_err(|e| format!("db task panicked: {}", e))?
        .map_err(|e| format!("delete failed: {}", e))
}

/// Delete a single screenshot by database ID.
#[tauri::command]
async fn delete_screenshot_by_id(
    db_state: State<'_, DatabaseState>,
    id: i64,
) -> Result<bool, String> {
    let db = Arc::clone(&db_state.db);
    tokio::task::spawn_blocking(move || db.delete_screenshot(id))
        .await
        .map_err(|e| format!("db task panicked: {}", e))?
        .map_err(|e| format!("delete failed: {}", e))
}

/// Delete ALL screenshots from the database. Returns the number of deleted rows.
#[tauri::command]
async fn delete_all_screenshots(
    db_state: State<'_, DatabaseState>,
) -> Result<u64, String> {
    let db = Arc::clone(&db_state.db);
    tokio::task::spawn_blocking(move || db.delete_all())
        .await
        .map_err(|e| format!("db task panicked: {}", e))?
        .map_err(|e| format!("delete_all failed: {}", e))
}

// ---------------------------------------------------------------------------
// Semantic search commands (Gemini gemini-embedding-001, 3072-dim, L2-normalized).
// Embeddings are computed in TS (`services/embeddingService.ts`) and pushed
// down via `save_screenshot_embedding`. Query-side search is done here so
// the full BLOB scan stays off the renderer thread.
// ---------------------------------------------------------------------------

/// Persist an embedding against an existing screenshot row.
#[tauri::command]
async fn save_screenshot_embedding(
    db_state: State<'_, DatabaseState>,
    id: i64,
    embedding: Vec<f32>,
) -> Result<(), String> {
    let db = Arc::clone(&db_state.db);
    tokio::task::spawn_blocking(move || db.update_screenshot_embedding(id, &embedding))
        .await
        .map_err(|e| format!("db task panicked: {}", e))?
        .map_err(|e| format!("update_screenshot_embedding failed: {}", e))
}

/// Cosine-similarity search over stored embeddings. `limit` defaults to 50;
/// `min_similarity` defaults to 0.5 (matches Swift's RewindViewModel).
#[tauri::command]
async fn search_screenshots_semantic(
    db_state: State<'_, DatabaseState>,
    query_embedding: Vec<f32>,
    limit: Option<u32>,
    min_similarity: Option<f32>,
) -> Result<Vec<SemanticHit>, String> {
    let limit = limit.unwrap_or(50) as usize;
    let min_sim = min_similarity.unwrap_or(0.5);
    let db = Arc::clone(&db_state.db);
    tokio::task::spawn_blocking(move || db.search_similar_screenshots(&query_embedding, limit, min_sim))
        .await
        .map_err(|e| format!("db task panicked: {}", e))?
        .map_err(|e| format!("semantic search failed: {}", e))
}

/// Return screenshots with OCR text but no embedding yet (for TS backfill).
#[tauri::command]
async fn screenshots_missing_embeddings(
    db_state: State<'_, DatabaseState>,
    limit: Option<u32>,
) -> Result<Vec<EmbeddingBacklogItem>, String> {
    let limit = limit.unwrap_or(200);
    let db = Arc::clone(&db_state.db);
    tokio::task::spawn_blocking(move || db.get_screenshots_missing_embeddings(limit))
        .await
        .map_err(|e| format!("db task panicked: {}", e))?
        .map_err(|e| format!("screenshots_missing_embeddings failed: {}", e))
}

// ---------------------------------------------------------------------------
// Companion session commands
// ---------------------------------------------------------------------------

/// Persist a companion Q&A session. Returns the new row id.
#[tauri::command]
async fn save_companion_session(
    db_state: State<'_, DatabaseState>,
    session: CompanionSessionInput,
) -> Result<i64, String> {
    let db = Arc::clone(&db_state.db);
    tokio::task::spawn_blocking(move || db.insert_companion_session(&session))
        .await
        .map_err(|e| format!("db task panicked: {}", e))?
        .map_err(|e| format!("save_companion_session failed: {}", e))
}

/// Return the most recent companion sessions, newest first.
#[tauri::command]
async fn get_recent_companion_sessions(
    db_state: State<'_, DatabaseState>,
    limit: u32,
) -> Result<Vec<CompanionSession>, String> {
    let db = Arc::clone(&db_state.db);
    tokio::task::spawn_blocking(move || db.get_recent_companion_sessions(limit))
        .await
        .map_err(|e| format!("db task panicked: {}", e))?
        .map_err(|e| format!("get_recent_companion_sessions failed: {}", e))
}

/// Delete a companion session by id.
#[tauri::command]
async fn delete_companion_session(
    db_state: State<'_, DatabaseState>,
    id: i64,
) -> Result<(), String> {
    let db = Arc::clone(&db_state.db);
    tokio::task::spawn_blocking(move || db.delete_companion_session(id))
        .await
        .map_err(|e| format!("db task panicked: {}", e))?
        .map_err(|e| format!("delete_companion_session failed: {}", e))
}

/// Patch an existing companion_sessions row with chain outcome / post-Gemini
/// telemetry. Called by the Companion chain controller when the chain ends so
/// we capture the FULL interaction (was it completed, how many steps, which
/// grounding methods fired) — not just the planning step.
#[tauri::command]
async fn update_companion_session(
    db_state: State<'_, DatabaseState>,
    patch: CompanionSessionPatch,
) -> Result<(), String> {
    let db = Arc::clone(&db_state.db);
    tokio::task::spawn_blocking(move || db.update_companion_session(&patch))
        .await
        .map_err(|e| format!("db task panicked: {}", e))?
        .map_err(|e| format!("update_companion_session failed: {}", e))
}

// ---------------------------------------------------------------------------
// Plugin init
// ---------------------------------------------------------------------------

/// Initialize the screen-capture plugin.
pub fn init<R: Runtime>() -> TauriPlugin<R> {
    Builder::new("screen-capture")
        .invoke_handler(tauri::generate_handler![
            take_screenshot,
            take_screenshot_with_ocr,
            start_screen_capture,
            stop_screen_capture,
            get_active_window_info,
            get_screen_capture_state,
            save_screenshot,
            search_screenshots,
            get_recent_screenshots,
            get_screenshot_image,
            get_screenshot_by_id,
            delete_old_screenshots,
            delete_screenshot_by_id,
            delete_all_screenshots,
            save_screenshot_embedding,
            search_screenshots_semantic,
            screenshots_missing_embeddings,
            save_companion_session,
            get_recent_companion_sessions,
            delete_companion_session,
            update_companion_session,
        ])
        .setup(|app, _api| {
            app.manage(ScreenCaptureState {
                inner: Mutex::new(CaptureState::default()),
            });

            // Initialise the Rewind database in the app's data directory.
            let data_dir = app
                .path()
                .app_data_dir()
                .map_err(|e| Box::new(e) as Box<dyn std::error::Error>)?;

            let db = RewindDatabase::init(&data_dir)
                .map_err(|e| Box::new(e) as Box<dyn std::error::Error>)?;

            app.manage(DatabaseState { db: Arc::new(db) });

            tracing::info!("Screen capture plugin initialized");
            Ok(())
        })
        .build()
}
