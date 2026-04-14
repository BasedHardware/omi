use serde::{Deserialize, Serialize};
use std::sync::OnceLock;
use std::time::{Duration, Instant};
use tauri::command;

fn http_client() -> &'static reqwest::Client {
    static CLIENT: OnceLock<reqwest::Client> = OnceLock::new();
    CLIENT.get_or_init(|| {
        reqwest::Client::builder()
            .timeout(Duration::from_secs(30))
            .build()
            .expect("failed to build reqwest client")
    })
}

#[derive(Serialize)]
pub struct BackendPingResult {
    pub status: Option<u16>,
    pub body_preview: String,
    pub elapsed_ms: u128,
    pub error: Option<String>,
}

#[command]
pub async fn debug_backend_ping(url: String, token: Option<String>) -> Result<BackendPingResult, String> {
    let start = Instant::now();
    tracing::info!("[debug_backend_ping] GET {}", url);

    let mut req = http_client().get(&url);
    if let Some(t) = token {
        req = req.header("Authorization", format!("Bearer {t}"));
    }

    match req.send().await {
        Ok(resp) => {
            let status = resp.status().as_u16();
            let body = resp.text().await.unwrap_or_default();
            let preview: String = body.chars().take(300).collect();
            tracing::info!("[debug_backend_ping] {} → {} in {}ms", url, status, start.elapsed().as_millis());
            Ok(BackendPingResult {
                status: Some(status),
                body_preview: preview,
                elapsed_ms: start.elapsed().as_millis(),
                error: None,
            })
        }
        Err(e) => {
            tracing::error!("[debug_backend_ping] {} failed: {}", url, e);
            Ok(BackendPingResult {
                status: None,
                body_preview: String::new(),
                elapsed_ms: start.elapsed().as_millis(),
                error: Some(e.to_string()),
            })
        }
    }
}

#[derive(Deserialize)]
pub struct BackendRequestArgs {
    pub method: String,
    pub url: String,
    pub token: Option<String>,
    pub body: Option<String>,
}

#[derive(Serialize)]
pub struct BackendResponse {
    pub status: u16,
    pub body: String,
}

#[command]
pub async fn backend_request(args: BackendRequestArgs) -> Result<BackendResponse, String> {
    let start = Instant::now();
    let method = reqwest::Method::from_bytes(args.method.as_bytes())
        .map_err(|e| format!("invalid method: {e}"))?;

    let mut req = http_client()
        .request(method.clone(), &args.url)
        .header("Content-Type", "application/json");

    if let Some(t) = args.token {
        req = req.header("Authorization", format!("Bearer {t}"));
    }

    if let Some(body) = args.body {
        req = req.body(body);
    }

    let resp = req.send().await.map_err(|e| {
        tracing::error!("[backend_request] {} {} failed: {}", method, args.url, e);
        format!("request failed: {e}")
    })?;

    let status = resp.status().as_u16();
    let body = resp.text().await.unwrap_or_default();
    tracing::info!("[backend_request] {} {} → {} in {}ms", method, args.url, status, start.elapsed().as_millis());

    Ok(BackendResponse { status, body })
}
