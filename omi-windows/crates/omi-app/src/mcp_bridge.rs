/// Google MCP Bridge — manages the Python FastAPI MCP backend subprocess
/// and routes queries to it over HTTP.
///
/// The MCP backend lives at `mcp/backend/` and exposes:
///   POST /api/chat  { "message": "...", "stream": false }
///   GET  /api/health
///
/// The bridge:
///   1. Auto-detects the mcp/backend path relative to the omi-windows binary
///   2. Starts the Python FastAPI server as a subprocess on port 8002
///   3. Exposes `query_mcp(text, cfg)` and `confirm_mcp(...)` for the agent runtime
///   4. Detects Google-intent keywords to decide when to use MCP
///
/// If the Python venv is not set up, MCP gracefully degrades (returns None).

use anyhow::{Context, Result};
use std::path::PathBuf;
use std::process::Stdio;
use std::sync::{Arc, OnceLock};
use tokio::process::Child;
use tokio::sync::Mutex;
use tracing::{error, info, warn};

use crate::config::AppConfig;

// ── Singleton subprocess handle ────────────────────────────────────────────────

static MCP_PROCESS: OnceLock<Arc<Mutex<Option<Child>>>> = OnceLock::new();

fn process_store() -> &'static Arc<Mutex<Option<Child>>> {
    MCP_PROCESS.get_or_init(|| Arc::new(Mutex::new(None)))
}

/// Resolve the path to the mcp/backend directory.
/// Tries several locations relative to the binary and the workspace root.
pub fn find_mcp_backend_path(cfg: &AppConfig) -> Option<PathBuf> {
    // 1. User-configured path
    if !cfg.mcp_backend_path.is_empty() {
        let p = PathBuf::from(&cfg.mcp_backend_path);
        if p.exists() {
            return Some(p);
        }
    }

    // 2. Next to the binary (production)
    if let Ok(exe) = std::env::current_exe() {
        let candidate = exe
            .parent()
            .and_then(|p| p.parent())
            .and_then(|p| p.parent())
            .map(|p| p.join("mcp").join("backend"));
        if let Some(p) = candidate {
            if p.exists() {
                return Some(p);
            }
        }
    }

    // 3. Workspace root heuristic (dev mode)
    if let Ok(cwd) = std::env::current_dir() {
        // Walk up to find root containing mcp/backend
        let mut dir = cwd.as_path();
        for _ in 0..6 {
            let candidate = dir.join("mcp").join("backend");
            if candidate.exists() {
                return Some(candidate);
            }
            match dir.parent() {
                Some(p) => dir = p,
                None => break,
            }
        }
    }

    None
}

/// Detect if a Python venv is available in the mcp/backend directory.
fn find_python(mcp_dir: &PathBuf) -> Option<PathBuf> {
    // Try venv inside mcp/backend
    let venv_python = mcp_dir.join("venv").join("Scripts").join("python.exe");
    if venv_python.exists() {
        return Some(venv_python);
    }

    // Try system python
    for name in &["python", "python3", "py"] {
        if which_python(name).is_some() {
            return which_python(name);
        }
    }
    None
}

fn which_python(name: &str) -> Option<PathBuf> {
    std::process::Command::new("where")
        .arg(name)
        .output()
        .ok()
        .and_then(|o| {
            if o.status.success() {
                String::from_utf8(o.stdout)
                    .ok()
                    .and_then(|s| s.lines().next().map(|l| PathBuf::from(l.trim())))
            } else {
                None
            }
        })
}

/// Start the MCP backend subprocess if not already running.
pub async fn ensure_started(cfg: &AppConfig) -> Result<()> {
    let mut guard = process_store().lock().await;
    if guard.is_some() {
        return Ok(()); // already running
    }

    let mcp_dir = find_mcp_backend_path(cfg)
        .context("MCP backend directory not found. Set mcp_backend_path in config.")?;

    let python = find_python(&mcp_dir)
        .context("Python not found. Ensure mcp/backend/venv exists or Python is in PATH.")?;

    info!("[MCP] Starting backend: python={}", python.display());
    info!("[MCP] Working dir: {}", mcp_dir.display());

    // The FastAPI app entry point: `uvicorn backend.api.main:app`
    // We run it as `python -m uvicorn backend.api.main:app --port 8002`
    let child = tokio::process::Command::new(&python)
        .args([
            "-m",
            "uvicorn",
            "api.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8002",
            "--log-level",
            "warning",
        ])
        .current_dir(&mcp_dir)
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .context("Failed to spawn MCP backend subprocess")?;

    *guard = Some(child);
    info!("[MCP] Backend subprocess started on http://127.0.0.1:8002");
    drop(guard);

    let mut started = false;
    for i in 0..15 {
        tokio::time::sleep(tokio::time::Duration::from_secs(2)).await;
        if let Ok(true) = health_check().await {
            info!("[MCP] Backend health check passed ✅ after {}s", (i + 1) * 2);
            started = true;
            break;
        }
    }

    if !started {
        warn!("[MCP] Backend health check failed to pass after 30 seconds");
    }

    Ok(())
}

/// Ping the MCP health endpoint.
async fn health_check() -> Result<bool> {
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(5))
        .build()?;
    let resp = client.get("http://127.0.0.1:8002/api/health").send().await?;
    Ok(resp.status().is_success())
}

/// Detect if the user's query is directed at Google Workspace tools.
pub fn is_google_query(query: &str) -> bool {
    let q = query.to_lowercase();
    let keywords = [
        "email", "gmail", "mail", "inbox", "send email", "draft",
        "calendar", "schedule", "event", "meeting", "appointment",
        "drive", "doc", "document", "spreadsheet", "sheet",
        "google", "workspace",
    ];
    keywords.iter().any(|kw| q.contains(kw))
}

#[derive(Debug, Clone)]
pub enum McpResponse {
    Text(String),
    HitlRequest { thread_id: String, message: String },
}

/// Send a query to the MCP backend and return the response.
pub async fn query_mcp(user_query: &str, cfg: &AppConfig) -> Option<McpResponse> {
    if !cfg.mcp_enabled {
        return None;
    }

    // Ensure server is running
    if let Err(e) = ensure_started(cfg).await {
        warn!("[MCP] Failed to start backend: {e:#}");
        return None;
    }

    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(30))
        .build()
        .ok()?;

    let body = serde_json::json!({
        "message": user_query,
        "stream": false,
        "conversation_id": "omi-windows-session"
    });

    info!("[MCP] Sending query: {}", &user_query[..user_query.len().min(80)]);

    let mut req = client.post("http://127.0.0.1:8002/api/message").json(&body);
    if !cfg.firebase_id_token.is_empty() {
        req = req.header("Authorization", format!("Bearer {}", cfg.firebase_id_token));
    }

    match req.send().await
    {
        Ok(resp) if resp.status().is_success() => {
            let json: serde_json::Value = resp.json().await.ok()?;
            
            // Check for Human-In-The-Loop interruption
            if let Some(true) = json.get("interrupted").and_then(|v| v.as_bool()) {
                if let Some(conf) = json.get("confirmation_required") {
                    let thread_id = conf.get("thread_id").and_then(|v| v.as_str()).unwrap_or("").to_string();
                    let message = conf.get("message").and_then(|v| v.as_str()).unwrap_or("Confirmation required").to_string();
                    return Some(McpResponse::HitlRequest { thread_id, message });
                }
            }

            let text = json
                .get("message")
                .or_else(|| json.get("response"))
                .and_then(|v| v.as_str())
                .map(|s| s.to_string());

            if let Some(ref t) = text {
                info!("[MCP] Got response: {} chars", t.len());
            }
            text.map(McpResponse::Text)
        }
        Ok(resp) => {
            let status = resp.status();
            let body = resp.text().await.unwrap_or_default();
            error!("[MCP] Backend error HTTP {status}: {body}");
            None
        }
        Err(e) => {
            error!("[MCP] Request failed: {e:#}");
            None
        }
    }
}

/// Kill the MCP backend subprocess on app shutdown.
pub async fn shutdown() {
    let mut guard = process_store().lock().await;
    if let Some(mut child) = guard.take() {
        let _ = child.kill().await;
        info!("[MCP] Backend subprocess killed");
    }
}

/// Check if MCP backend is reachable right now (non-blocking heuristic).
pub async fn is_running() -> bool {
    health_check().await.unwrap_or(false)
}

/// Send a HITL confirmation back to the MCP backend.
pub async fn confirm_mcp(thread_id: &str, user_response: &str, cfg: &AppConfig) -> Option<McpResponse> {
    if !cfg.mcp_enabled {
        return None;
    }

    if let Err(e) = ensure_started(cfg).await {
        warn!("[MCP] Failed to start backend for confirm: {e:#}");
        return None;
    }

    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(60))
        .build()
        .ok()?;

    let body = serde_json::json!({
        "thread_id": thread_id,
        "response": user_response
    });

    info!("[MCP] Sending HITL confirm: {}", user_response);

    match client
        .post("http://127.0.0.1:8002/api/message/confirm")
        .json(&body)
        .send()
        .await
    {
        Ok(resp) if resp.status().is_success() => {
            let json: serde_json::Value = resp.json().await.ok()?;
            
            if let Some(true) = json.get("interrupted").and_then(|v| v.as_bool()) {
                if let Some(conf) = json.get("confirmation_required") {
                    let thread_id = conf.get("thread_id").and_then(|v| v.as_str()).unwrap_or("").to_string();
                    let message = conf.get("message").and_then(|v| v.as_str()).unwrap_or("Confirmation required").to_string();
                    return Some(McpResponse::HitlRequest { thread_id, message });
                }
            }

            let text = json
                .get("message")
                .or_else(|| json.get("response"))
                .and_then(|v| v.as_str())
                .map(|s| s.to_string());

            text.map(McpResponse::Text)
        }
        Ok(resp) => {
            let status = resp.status();
            let body = resp.text().await.unwrap_or_default();
            error!("[MCP] Confirm error HTTP {status}: {body}");
            None
        }
        Err(e) => {
            error!("[MCP] Confirm request failed: {e:#}");
            None
        }
    }
}
