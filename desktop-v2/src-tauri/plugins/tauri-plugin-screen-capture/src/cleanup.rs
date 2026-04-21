use std::sync::Arc;
use std::time::Duration;

use chrono::{SecondsFormat, Utc};

use crate::config::RetentionConfig;
use crate::database::RewindDatabase;

const CLEANUP_INTERVAL: Duration = Duration::from_secs(24 * 3600);

/// Spawn a background task that purges screenshots older than the configured
/// retention window. Runs immediately on startup and then every 24h. Re-reads
/// the retention setting on every tick so user changes take effect without a
/// restart.
pub fn start_cleanup_task(db: Arc<RewindDatabase>, retention: Arc<RetentionConfig>) {
    tauri::async_runtime::spawn(async move {
        let mut ticker = tokio::time::interval(CLEANUP_INTERVAL);
        loop {
            ticker.tick().await;
            run_once(&db, &retention).await;
        }
    });
}

async fn run_once(db: &Arc<RewindDatabase>, retention: &Arc<RetentionConfig>) {
    let days = retention.current_days();
    let cutoff = match Utc::now().checked_sub_signed(chrono::Duration::days(days as i64)) {
        Some(ts) => ts.to_rfc3339_opts(SecondsFormat::Millis, true),
        None => {
            tracing::warn!("retention cutoff overflow for days={}", days);
            return;
        }
    };

    let db = Arc::clone(db);
    let cutoff_for_task = cutoff.clone();
    let result = tokio::task::spawn_blocking(move || db.delete_older_than(&cutoff_for_task)).await;

    match result {
        Ok(Ok(deleted)) => {
            tracing::info!(
                "Retention cleanup purged {} screenshots older than {} (cutoff {}d)",
                deleted,
                cutoff,
                days
            );
        }
        Ok(Err(e)) => {
            tracing::warn!("Retention cleanup db error: {}", e);
        }
        Err(e) => {
            tracing::warn!("Retention cleanup task panicked: {}", e);
        }
    }
}
