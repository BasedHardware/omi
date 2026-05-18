use dioxus::prelude::*;

const BACKEND_URL: &str = "http://localhost:10201";
const HEALTH_ENDPOINT: &str = "/health";
const POLL_INTERVAL_MS: u64 = 2000;
const MAX_RETRIES: u32 = 60;

/// Backend sidecar connection status.
#[derive(Debug, Clone, PartialEq)]
pub enum BackendStatus {
    Starting,
    Connected,
    Error(String),
}

/// Poll the Backend-Rust sidecar health endpoint until it responds.
///
/// This runs as an async task spawned from the root component.
/// In production, we would also spawn the backend binary as a child process
/// here — for now we just poll an already-running instance.
pub async fn poll_backend_health(status: &mut Signal<BackendStatus>) {
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(2))
        .build()
        .unwrap();

    let url = format!("{BACKEND_URL}{HEALTH_ENDPOINT}");

    for attempt in 1..=MAX_RETRIES {
        match client.get(&url).send().await {
            Ok(resp) if resp.status().is_success() => {
                tracing::info!("Backend sidecar connected on attempt {attempt}");
                status.set(BackendStatus::Connected);
                return;
            }
            Ok(resp) => {
                tracing::debug!(
                    "Backend health check attempt {attempt}: status {}",
                    resp.status()
                );
            }
            Err(e) => {
                tracing::debug!("Backend health check attempt {attempt}: {e}");
            }
        }

        tokio::time::sleep(std::time::Duration::from_millis(POLL_INTERVAL_MS)).await;
    }

    let msg = format!("Backend did not respond after {MAX_RETRIES} attempts");
    tracing::warn!("{msg}");
    status.set(BackendStatus::Error(msg));
}
