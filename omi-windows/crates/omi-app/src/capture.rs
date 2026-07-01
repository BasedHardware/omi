/// Background screen capture task: screenshot → dedup → OCR → DB.

use tokio::time::{interval, Duration};
use base64::Engine;
use crate::config::AppConfig;

pub async fn run_capture_task(db: omi_db::Database, interval_secs: u64, initial_cfg: AppConfig) {
    tracing::info!("[CAPTURE] Task spawned, waiting for first tick in {interval_secs}s...");

    let enable_video = initial_cfg.video_chunk_encoding_enabled;
    let ffmpeg_path = if initial_cfg.ffmpeg_path.is_empty() { None } else { Some(initial_cfg.ffmpeg_path.clone()) };
    let monitor_mode = initial_cfg.capture_monitor_mode.clone();

    let engine = std::sync::Arc::new(std::sync::Mutex::new(
        omi_capture::CaptureEngine::new(enable_video, ffmpeg_path)
    ));

    capture_one(&db, &initial_cfg, &engine, &monitor_mode).await;

    let mut tick = interval(Duration::from_secs(interval_secs));
    tick.tick().await;
    tracing::info!("[CAPTURE] Periodic loop running every {interval_secs}s");

    loop {
        tick.tick().await;
        let cfg = AppConfig::load();
        if !cfg.screen_capture_enabled {
            tracing::info!("[CAPTURE] Screen capture disabled in config, sleeping");
            tokio::time::sleep(Duration::from_secs(1)).await;
            continue;
        }
        let mode = cfg.capture_monitor_mode.clone();
        capture_one(&db, &cfg, &engine, &mode).await;
    }
}

async fn capture_one(
    db: &omi_db::Database,
    cfg: &AppConfig,
    engine: &std::sync::Arc<std::sync::Mutex<omi_capture::CaptureEngine>>,
    monitor_mode: &str,
) {
    let db_clone = db.clone();
    let engine_clone = engine.clone();
    let mode = monitor_mode.to_string();

    let result = tokio::task::spawn_blocking(move || {
        let mut eng = engine_clone.lock().unwrap();
        eng.capture_tick(&mode)
    })
    .await;

    match result {
        Ok(Ok(Some(mut record))) => {
            tracing::info!("[CAPTURE] Frame captured: path={} window={:?} ocr_chars={}",
                record.thumbnail_path,
                record.window_title,
                record.ocr_text.as_ref().map(|t| t.len()).unwrap_or(0)
            );

            if !cfg.ocr_enabled {
                record.ocr_text = None;
            } else if let Some(ref mut text) = record.ocr_text {
                let max_chars = cfg.ocr_summary_max_chars.min(5000).max(64) as usize;
                if text.chars().count() > max_chars {
                    if let Some((byte_idx, _)) = text.char_indices().nth(max_chars) {
                        text.truncate(byte_idx);
                        text.push_str("...");
                    }
                }
            }

            let data_uri = match std::fs::read(&record.thumbnail_path) {
                Ok(bytes) => {
                    let b64 = base64::engine::general_purpose::STANDARD.encode(&bytes);
                    Some(format!("data:image/jpeg;base64,{b64}"))
                }
                Err(e) => {
                    tracing::error!("[CAPTURE] Failed to read JPEG for base64: {e}");
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
                                    } else {
                                        let backend_url = cfg_extract.backend_url.clone();
                                        let token = cfg_extract.firebase_id_token.clone();
                                        let c_content = extraction.summary.trim().to_string();
                                        let c_category = "screenshot".to_string();
                                        tokio::spawn(async move {
                                            crate::sync::upload_memory(backend_url, token, c_content, c_category).await;
                                        });
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
                                    } else {
                                        let backend_url = cfg_extract.backend_url.clone();
                                        let token = cfg_extract.firebase_id_token.clone();
                                        let c_content = content.to_string();
                                        let c_category = memory.category.as_deref().unwrap_or("interesting").to_string();
                                        tokio::spawn(async move {
                                            crate::sync::upload_memory(backend_url, token, c_content, c_category).await;
                                        });
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
            tracing::debug!("[CAPTURE] Frame skipped (dedup or no monitor)");
        }
        Ok(Err(e)) => {
            tracing::error!("[CAPTURE] capture error: {e:#}");
        }
        Err(e) => {
            tracing::error!("[CAPTURE] spawn_blocking panicked: {e}");
        }
    }
}
