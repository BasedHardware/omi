/// Background screen capture task: screenshot → OCR → DB.

use tokio::time::{interval, Duration};

pub async fn run_capture_task(db: omi_db::Database, interval_secs: u64) {
    tracing::info!("[CAPTURE] Task spawned, waiting for first tick in {interval_secs}s...");

    // Capture one frame immediately on startup so we don't wait a full interval
    capture_one(&db).await;

    let mut tick = interval(Duration::from_secs(interval_secs));
    tick.tick().await; // consume the immediate tick
    tracing::info!("[CAPTURE] Periodic loop running every {interval_secs}s");

    loop {
        tick.tick().await;
        capture_one(&db).await;
    }
}

async fn capture_one(db: &omi_db::Database) {
    tracing::info!("[CAPTURE] Capturing screen...");

    let db_clone = db.clone();
    let result = tokio::task::spawn_blocking(move || {
        omi_capture::capture_and_ocr()
    })
    .await;

    match result {
        Ok(Ok(Some(record))) => {
            tracing::info!("[CAPTURE] Frame captured: path={} window={:?} ocr_chars={}",
                record.thumbnail_path,
                record.window_title,
                record.ocr_text.as_ref().map(|t| t.len()).unwrap_or(0)
            );
            match db_clone.insert_screenshot(
                None,
                record.window_title.as_deref(),
                record.ocr_text.as_deref(),
                Some(&record.thumbnail_path),
            ) {
                Ok(id) => tracing::info!("[CAPTURE] Saved to DB: {id}"),
                Err(e) => tracing::error!("[CAPTURE] DB insert failed: {e:#}"),
            }
        }
        Ok(Ok(None)) => {
            tracing::warn!("[CAPTURE] capture_and_ocr returned None (no monitor?)");
        }
        Ok(Err(e)) => {
            tracing::error!("[CAPTURE] capture_and_ocr error: {e:#}");
        }
        Err(e) => {
            tracing::error!("[CAPTURE] spawn_blocking panicked: {e}");
        }
    }
}
