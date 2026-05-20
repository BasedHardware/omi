/// Background screen capture task: screenshot → OCR → DB.

use tokio::time::{interval, Duration};
use base64::Engine;
use crate::config::AppConfig;

pub async fn run_capture_task(db: omi_db::Database, interval_secs: u64, initial_cfg: AppConfig) {
    tracing::info!("[CAPTURE] Task spawned, waiting for first tick in {interval_secs}s...");

    // Capture one frame immediately on startup so we don't wait a full interval
    capture_one(&db, &initial_cfg).await;

    let mut tick = interval(Duration::from_secs(interval_secs));
    tick.tick().await; // consume the immediate tick
    tracing::info!("[CAPTURE] Periodic loop running every {interval_secs}s");

    loop {
        tick.tick().await;
        // Reload config each loop so toggling in Settings takes effect
        let cfg = AppConfig::load();
        if !cfg.screen_capture_enabled {
            tracing::info!("[CAPTURE] Screen capture disabled in config, sleeping");
            tokio::time::sleep(Duration::from_secs(1)).await;
            continue;
        }
        capture_one(&db, &cfg).await;
    }
}

async fn capture_one(db: &omi_db::Database, cfg: &AppConfig) {
    tracing::info!("[CAPTURE] Capturing screen...");

    let db_clone = db.clone();
    let result = tokio::task::spawn_blocking(move || {
        omi_capture::capture_and_ocr()
    })
    .await;

    match result {
        Ok(Ok(Some(mut record))) => {
            tracing::info!("[CAPTURE] Frame captured: path={} window={:?} ocr_chars={}",
                record.thumbnail_path,
                record.window_title,
                record.ocr_text.as_ref().map(|t| t.len()).unwrap_or(0)
            );

            // Respect OCR enabled setting
            if !cfg.ocr_enabled {
                record.ocr_text = None;
            } else if let Some(ref mut text) = record.ocr_text {
                // Truncate OCR text per-config to avoid huge payloads
                let max_chars = cfg.ocr_summary_max_chars.min(5000).max(64);
                if text.len() > max_chars {
                    text.truncate(max_chars);
                    text.push_str("...");
                }
            }

            // Read JPEG bytes and encode as base64 data URI so the webview
            // can render it without file:// protocol restrictions.
            let data_uri = match std::fs::read(&record.thumbnail_path) {
                Ok(bytes) => {
                    let b64 = base64::engine::general_purpose::STANDARD.encode(&bytes);
                    tracing::info!("[CAPTURE] Encoded {} bytes as base64", bytes.len());
                    Some(format!("data:image/jpeg;base64,{b64}"))
                }
                Err(e) => {
                    tracing::error!("[CAPTURE] Failed to read JPEG for base64: {e}");
                    // Fall back to file path
                    Some(record.thumbnail_path.clone())
                }
            };
            match db_clone.insert_screenshot(
                None,
                record.window_title.as_deref(),
                record.ocr_text.as_deref(),
                data_uri.as_deref(),
            ) {
                Ok(id) => {
                    tracing::info!("[CAPTURE] Saved to DB: {id}");

                    if cfg.screenshot_auto_extract_enabled {
                        let db_extract = db_clone.clone();
                        let cfg_extract = cfg.clone();
                        let window_title = record.window_title.clone();
                        let ocr_text = record.ocr_text.clone();

                        tokio::spawn(async move {
                            let extraction = crate::llm::extract_screenshot_artifacts(
                                &cfg_extract,
                                window_title.as_deref(),
                                ocr_text.as_deref(),
                            )
                            .await;

                            let extraction = match extraction {
                                Ok(extraction) => extraction,
                                Err(e) => {
                                    tracing::error!("[CAPTURE] Screenshot extraction failed: {e}");
                                    return;
                                }
                            };

                            if !extraction.summary.trim().is_empty() {
                                tracing::info!(
                                    "[CAPTURE] Screenshot summary: {}",
                                    extraction.summary.trim()
                                );

                                if cfg_extract.screenshot_auto_save_memory {
                                    if let Err(e) = db_extract.insert_memory(
                                        None,
                                        extraction.summary.trim(),
                                        Some("screenshot"),
                                    ) {
                                        tracing::error!("[CAPTURE] Failed to save screenshot summary memory: {e}");
                                    }
                                }
                            }

                            if cfg_extract.screenshot_auto_save_action_items {
                                for item in extraction.action_items {
                                    let content = item.trim();
                                    if content.is_empty() {
                                        continue;
                                    }

                                    if let Err(e) = db_extract.insert_action_item(None, content) {
                                        tracing::error!("[CAPTURE] Failed to save screenshot action item: {e}");
                                    }
                                }
                            }

                            if cfg_extract.screenshot_auto_save_memory {
                                for memory in extraction.memories {
                                    let content = memory.content.trim();
                                    if content.is_empty() {
                                        continue;
                                    }

                                    if let Err(e) = db_extract.insert_memory(
                                        None,
                                        content,
                                        memory.category.as_deref(),
                                    ) {
                                        tracing::error!("[CAPTURE] Failed to save screenshot memory: {e}");
                                    }
                                }
                            }
                        });
                    }
                }
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
