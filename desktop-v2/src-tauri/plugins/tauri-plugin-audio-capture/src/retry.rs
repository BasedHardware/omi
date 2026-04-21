//! Background retry service for transcription sessions.
//!
//! Rust port of Swift `TranscriptionRetryService`. Runs a 60s interval loop
//! that:
//!   1. Recovers crashed `recording` sessions on startup (turning them into
//!      `pending_upload` or deleting them if empty).
//!   2. Uploads `pending_upload` sessions to
//!      `/v1/conversations/from-segments`.
//!   3. Retries `failed` sessions with exponential backoff (up to 5 tries).
//!   4. Rescues sessions stuck in `uploading` > 5 min (likely killed mid-POST).
//!
//! On success the conversation `id` is recorded and a `meeting:synced`
//! event is emitted so the frontend can swap the local-only placeholder for
//! the real backend row.

use std::sync::Arc;
use std::time::Duration;

use chrono::Utc;
use tauri::{AppHandle, Emitter, Runtime};
use tokio_util::sync::CancellationToken;

use crate::storage::TranscriptionStorage;
use crate::transcription::{post_conversation, TranscriptSegmentRequest};

const RETRY_INTERVAL_SECS: u64 = 60;
const MAX_RETRIES: i32 = 5;
const STUCK_UPLOAD_AGE_SECS: i64 = 300;
const CRASHED_RECORDING_AGE_SECS: i64 = 30;

/// Long-lived handle to the retry loop task. Dropping it cancels the loop.
pub struct TranscriptionRetryService<R: Runtime> {
    storage: Arc<TranscriptionStorage>,
    app: AppHandle<R>,
    cancel: CancellationToken,
}

impl<R: Runtime> TranscriptionRetryService<R> {
    /// Start the retry loop. Runs one recovery + upload tick immediately,
    /// then ticks every 60 s.
    pub fn start(storage: Arc<TranscriptionStorage>, app: AppHandle<R>) -> Self {
        let cancel = CancellationToken::new();
        let svc = Self {
            storage: storage.clone(),
            app: app.clone(),
            cancel: cancel.clone(),
        };

        let storage_task = storage.clone();
        let app_task = app.clone();
        // Use tauri::async_runtime::spawn because this is called from the
        // plugin's synchronous setup hook, which has no ambient Tokio runtime —
        // a bare tokio::spawn would panic with "no reactor running".
        tauri::async_runtime::spawn(async move {
            tracing::info!("[retry] starting TranscriptionRetryService");

            // Recover once on startup.
            recover_on_start(&storage_task).await;

            // Kick one retry tick immediately so pending meetings sync
            // without waiting 60 s.
            process_retry_queue(&storage_task, &app_task).await;

            let mut interval =
                tokio::time::interval(Duration::from_secs(RETRY_INTERVAL_SECS));
            interval.tick().await; // skip the immediate tick
            loop {
                tokio::select! {
                    _ = cancel.cancelled() => {
                        tracing::info!("[retry] retry service cancelled");
                        break;
                    }
                    _ = interval.tick() => {
                        process_retry_queue(&storage_task, &app_task).await;
                    }
                }
            }
        });

        svc
    }

    /// User-triggered retry — bypasses backoff and re-uploads immediately.
    pub async fn retry_now(&self, session_id: i64) -> Result<(), String> {
        upload_session(&self.storage, &self.app, session_id).await
    }

    /// Cancel the retry loop.
    #[allow(dead_code)]
    pub fn stop(&self) {
        self.cancel.cancel();
    }
}

/// One-shot recovery on app launch:
///  - Any session still in `recording` is either finished (if it has
///    segments) or deleted (if it was empty) — whichever applies depends
///    on whether we actually captured anything before the crash.
///  - Any session stuck in `uploading` for > 5 min is pushed back to
///    `pending_upload` so the loop can retry.
async fn recover_on_start(storage: &Arc<TranscriptionStorage>) {
    tracing::info!("[retry] checking for pending transcriptions");

    match storage.get_crashed_sessions() {
        Ok(crashed) if !crashed.is_empty() => {
            tracing::info!("[retry] found {} crashed sessions", crashed.len());
            for session in crashed {
                // Skip sessions that are suspiciously recent — they might
                // actually be mid-capture for a race where the DB opened
                // just before the consumer wrote its first segment.
                let created_age = parse_age_secs(&session.created_at);
                if created_age < CRASHED_RECORDING_AGE_SECS {
                    tracing::info!(
                        "[retry] skipping recent crashed session {} (age={}s)",
                        session.id,
                        created_age,
                    );
                    continue;
                }

                match storage.get_segment_count(session.id) {
                    Ok(0) => {
                        tracing::info!("[retry] deleting empty crashed session {}", session.id);
                        if let Err(e) = storage.delete_session(session.id) {
                            tracing::warn!("[retry] delete failed: {}", e);
                        }
                    }
                    Ok(n) => {
                        tracing::info!(
                            "[retry] marking crashed session {} as pending_upload ({} segments)",
                            session.id,
                            n
                        );
                        if let Err(e) = storage.finish_session(session.id) {
                            tracing::warn!("[retry] finish_session failed: {}", e);
                        }
                    }
                    Err(e) => tracing::warn!("[retry] get_segment_count failed: {}", e),
                }
            }
        }
        Ok(_) => {}
        Err(e) => tracing::warn!("[retry] get_crashed_sessions failed: {}", e),
    }

    // Push stuck-uploading sessions back to pending_upload so the loop
    // picks them up normally.
    match storage.get_stuck_uploading(STUCK_UPLOAD_AGE_SECS) {
        Ok(stuck) if !stuck.is_empty() => {
            tracing::info!("[retry] found {} stuck uploading sessions", stuck.len());
            for session in stuck {
                if let Err(e) = storage.finish_session(session.id) {
                    tracing::warn!("[retry] reset stuck session {} failed: {}", session.id, e);
                }
            }
        }
        Ok(_) => {}
        Err(e) => tracing::warn!("[retry] get_stuck_uploading failed: {}", e),
    }
}

/// One loop tick — process every candidate session found in the DB.
async fn process_retry_queue<R: Runtime>(
    storage: &Arc<TranscriptionStorage>,
    app: &AppHandle<R>,
) {
    // Pending upload — freshest stops first.
    let pending = storage.list_by_status("pending_upload").unwrap_or_else(|e| {
        tracing::warn!("[retry] list pending failed: {}", e);
        Vec::new()
    });
    for session in pending {
        let _ = upload_session(storage, app, session.id).await;
    }

    // Stuck upload — shove back to pending and try again.
    if let Ok(stuck) = storage.get_stuck_uploading(STUCK_UPLOAD_AGE_SECS) {
        for session in stuck {
            tracing::info!("[retry] resetting stuck session {}", session.id);
            if let Err(e) = storage.finish_session(session.id) {
                tracing::warn!("[retry] reset stuck {} failed: {}", session.id, e);
                continue;
            }
            let _ = upload_session(storage, app, session.id).await;
        }
    }

    // Failed but retry-eligible.
    let failed = storage
        .list_failed_ready(MAX_RETRIES)
        .unwrap_or_else(|e| {
            tracing::warn!("[retry] list failed failed: {}", e);
            Vec::new()
        });
    for session in failed {
        let _ = upload_session(storage, app, session.id).await;
    }
}

/// Upload a single session. Bypasses backoff — callers decide when.
async fn upload_session<R: Runtime>(
    storage: &Arc<TranscriptionStorage>,
    app: &AppHandle<R>,
    session_id: i64,
) -> Result<(), String> {
    let session = match storage.get_session(session_id) {
        Ok(Some(s)) => s,
        Ok(None) => {
            tracing::warn!("[retry] session {} not found", session_id);
            return Err("session not found".into());
        }
        Err(e) => {
            tracing::warn!("[retry] load session {} failed: {}", session_id, e);
            return Err(format!("load session: {e}"));
        }
    };

    let segments = match storage.get_segments(session_id) {
        Ok(s) => s,
        Err(e) => {
            tracing::warn!("[retry] load segments {} failed: {}", session_id, e);
            return Err(format!("load segments: {e}"));
        }
    };

    if segments.is_empty() {
        tracing::info!(
            "[retry] session {} has no segments, deleting",
            session_id
        );
        let _ = storage.delete_session(session_id);
        return Ok(());
    }

    // Read id_token fresh each attempt — refresh may have rotated it since
    // the session was recorded.
    let id_token = match crate::read_id_token(app) {
        Some(t) if !t.is_empty() => t,
        _ => {
            tracing::warn!(
                "[retry] skipping session {} — no id_token (user signed out?)",
                session_id
            );
            return Err("no auth token".into());
        }
    };

    if let Err(e) = storage.mark_uploading(session_id) {
        tracing::warn!("[retry] mark_uploading failed: {}", e);
    }

    let started_at = match chrono::DateTime::parse_from_rfc3339(&session.started_at) {
        Ok(dt) => dt.with_timezone(&Utc),
        Err(_) => Utc::now(),
    };
    let finished_at = session
        .finished_at
        .as_ref()
        .and_then(|s| chrono::DateTime::parse_from_rfc3339(s).ok())
        .map(|dt| dt.with_timezone(&Utc))
        .unwrap_or_else(Utc::now);

    let request_segments: Vec<TranscriptSegmentRequest> = segments
        .into_iter()
        .map(|s| TranscriptSegmentRequest {
            text: s.text,
            speaker: s.speaker,
            speaker_id: s.speaker_id,
            is_user: s.is_user,
            person_id: None,
            start: s.start_time,
            end: s.end_time,
        })
        .collect();

    match post_conversation(
        crate::BACKEND_URL,
        &id_token,
        request_segments,
        started_at,
        finished_at,
        session.input_device_name.clone(),
        &session.language,
    )
    .await
    {
        Ok(backend_id) => {
            tracing::info!(
                "[retry] session {} uploaded (backend_id={:?})",
                session_id,
                backend_id
            );
            if let Err(e) = storage.mark_completed(session_id, &backend_id) {
                tracing::warn!("[retry] mark_completed failed: {}", e);
            }
            if let Err(e) = app.emit(
                "meeting:synced",
                serde_json::json!({
                    "session_id": session_id,
                    "backend_id": backend_id,
                }),
            ) {
                tracing::warn!("[retry] emit meeting:synced failed: {}", e);
            }
            Ok(())
        }
        Err(e) => {
            tracing::warn!(
                "[retry] upload session {} failed: {} (retry_count={})",
                session_id,
                e,
                session.retry_count,
            );
            let current_retry = session.retry_count;
            // Schedule next attempt: 1, 2, 4, 8, 16 minutes.
            let minutes = 2_i64.pow(current_retry.max(0) as u32);
            let next = (Utc::now() + chrono::Duration::minutes(minutes)).to_rfc3339();
            if let Err(e2) = storage.increment_retry(session_id, &next) {
                tracing::warn!("[retry] increment_retry failed: {}", e2);
            }
            if let Err(e2) = storage.mark_failed(session_id, &e) {
                tracing::warn!("[retry] mark_failed failed: {}", e2);
            }
            Err(e)
        }
    }
}

/// Parse an ISO-8601 UTC timestamp and return `now - t` in whole seconds.
/// Falls back to 0 (i.e. "very recent") on parse failure so we err on the
/// side of NOT treating a malformed row as crashed.
fn parse_age_secs(iso: &str) -> i64 {
    match chrono::DateTime::parse_from_rfc3339(iso) {
        Ok(dt) => (Utc::now() - dt.with_timezone(&Utc)).num_seconds(),
        Err(_) => 0,
    }
}

/// Free-standing helper for the Tauri `retry_sync_now` command, which doesn't
/// have access to a `TranscriptionRetryService` instance.
pub async fn retry_one<R: Runtime>(
    storage: &Arc<TranscriptionStorage>,
    app: &AppHandle<R>,
    session_id: i64,
) -> Result<(), String> {
    upload_session(storage, app, session_id).await
}

