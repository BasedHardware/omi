use std::path::PathBuf;
use std::process::{Child, Command, Stdio};

use dioxus::prelude::*;

const BACKEND_URL: &str = "http://localhost:10201";
const HEALTH_ENDPOINT: &str = "/health";
const POLL_INTERVAL_MS: u64 = 2000;
const MAX_RETRIES: u32 = 60;

#[derive(Debug, Clone, PartialEq)]
pub enum BackendStatus {
    Starting,
    Connected,
    Error(String),
}

fn find_backend_binary() -> Option<PathBuf> {
    let candidates = [
        std::env::current_exe()
            .ok()
            .and_then(|p| p.parent().map(|d| d.join("backend-rust").with_extension("exe"))),
        std::env::current_dir()
            .ok()
            .map(|d| d.join("backend").join("target").join("release").join("backend-rust.exe")),
        Some(PathBuf::from("C:\\omi\\desktop\\Backend-Rust\\target\\release\\backend-rust.exe")),
        std::env::current_dir()
            .ok()
            .map(|d| d.join("backend").join("target").join("debug").join("backend-rust.exe")),
        Some(PathBuf::from("C:\\omi\\desktop\\Backend-Rust\\target\\debug\\backend-rust.exe")),
    ];

    for candidate in candidates.into_iter().flatten() {
        if candidate.exists() {
            return Some(candidate);
        }
    }
    None
}

fn spawn_backend() -> Option<Child> {
    let binary = match find_backend_binary() {
        Some(p) => p,
        None => {
            tracing::warn!("[SIDECAR] Backend-Rust binary not found, will poll existing instance");
            return None;
        }
    };

    tracing::info!("[SIDECAR] Spawning backend: {}", binary.display());

    let working_dir = binary.parent().unwrap_or_else(|| std::path::Path::new("."));

    match Command::new(&binary)
        .current_dir(working_dir)
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
    {
        Ok(child) => {
            tracing::info!("[SIDECAR] Backend started (pid {})", child.id());
            Some(child)
        }
        Err(e) => {
            tracing::error!("[SIDECAR] Failed to spawn backend: {e}");
            None
        }
    }
}

pub async fn poll_backend_health(status: &mut Signal<BackendStatus>) {
    let _child = spawn_backend();

    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(2))
        .build()
        .unwrap();

    let url = format!("{BACKEND_URL}{HEALTH_ENDPOINT}");

    for attempt in 1..=MAX_RETRIES {
        match client.get(&url).send().await {
            Ok(resp) if resp.status().is_success() => {
                tracing::info!("[SIDECAR] Backend connected on attempt {attempt}");
                status.set(BackendStatus::Connected);
                return;
            }
            Ok(resp) => {
                tracing::debug!(
                    "[SIDECAR] Health check attempt {attempt}: status {}",
                    resp.status()
                );
            }
            Err(e) => {
                tracing::debug!("[SIDECAR] Health check attempt {attempt}: {e}");
            }
        }

        tokio::time::sleep(std::time::Duration::from_millis(POLL_INTERVAL_MS)).await;
    }

    let msg = format!("Backend did not respond after {MAX_RETRIES} attempts");
    tracing::warn!("[SIDECAR] {msg}");
    status.set(BackendStatus::Error(msg));
}
