//! Coding agent command bridge.
//!
//! Spawns the Pi RPC sidecar and streams JSONL events back to the frontend
//! via `app.emit("coding-agent:event", …)`, and supports sending follow-up
//! messages and graceful shutdown.
//!
//! # Binary selection
//!
//! Debug builds use `sidecar/pi-agent/node_modules/.bin/pi` (requires Node in
//! PATH).  Release builds use the self-contained Bun binary produced by
//! `scripts/build-binary.sh`, placed at `Contents/MacOS/nooto-pi-agent-<triple>`.
//!
//! # Asset resolution
//!
//! Pi's Bun binary resolves assets via `dirname(process.execPath)`, but Tauri
//! copies `bundle.resources` into `Contents/Resources/`, not `Contents/MacOS/`.
//! We override with `PI_PACKAGE_DIR=<resource_dir>/pi-agent/` so Pi finds its
//! themes, wasm, and extensions regardless of executable placement.

use std::collections::HashMap;
use std::io::Write;
use std::process::{Child, ChildStdin};
use std::sync::Mutex;
use std::time::Duration;

use serde_json::Value;
use tauri::{AppHandle, Emitter, Manager, State};

#[cfg(not(debug_assertions))]
use tauri_plugin_shell::ShellExt;

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

/// Mutable state registered with `app.manage()`.
pub struct CodingAgentState {
    /// Running Pi child processes keyed by session_id.
    pub children: Mutex<HashMap<String, Child>>,
    /// Stdin handles kept separately — `Child` doesn't allow borrowing stdin
    /// while the `Child` itself is also held.
    pub stdins: Mutex<HashMap<String, ChildStdin>>,
}

impl Default for CodingAgentState {
    fn default() -> Self {
        Self {
            children: Mutex::new(HashMap::new()),
            stdins: Mutex::new(HashMap::new()),
        }
    }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/// Resolve the `pi-agent/` resource directory.
///
/// Release: `Contents/Resources/pi-agent/` (Tauri resource bundler).
/// Debug: walks up from `resource_dir` to find `sidecar/pi-agent/` in the repo.
fn pi_resource_dir(app: &AppHandle) -> Result<std::path::PathBuf, String> {
    let resource_dir = app
        .path()
        .resource_dir()
        .map_err(|e| format!("resource_dir unavailable: {e}"))?;

    let release_candidate = resource_dir.join("pi-agent");
    if release_candidate.exists() {
        return Ok(release_candidate);
    }

    // Dev: walk up from the debug resource dir to the repo root.
    let mut dir = resource_dir.as_path();
    for _ in 0..8 {
        let candidate = dir.join("sidecar/pi-agent");
        if candidate.exists() {
            return Ok(candidate);
        }
        match dir.parent() {
            Some(p) => dir = p,
            None => break,
        }
    }

    Err(format!(
        "Could not locate pi-agent resource directory relative to {}",
        resource_dir.display()
    ))
}

/// Convert a `PathBuf` to `&str`, returning an error instead of silently
/// producing an empty string on non-UTF-8 paths.
fn path_str(p: &std::path::Path) -> Result<&str, String> {
    p.to_str()
        .ok_or_else(|| format!("Path is not valid UTF-8: {}", p.display()))
}

// ---------------------------------------------------------------------------
// Commands
// ---------------------------------------------------------------------------

/// Open a native folder-picker and return the selected path, or `None` if the
/// user cancelled.
#[tauri::command]
pub async fn coding_agent_pick_folder(app: AppHandle) -> Result<Option<String>, String> {
    use tauri_plugin_dialog::DialogExt;
    Ok(app.dialog().file().blocking_pick_folder().map(|p| p.to_string()))
}

/// Spawn the Pi sidecar, write the initial prompt, and start streaming events
/// back to the frontend as `"coding-agent:event"` with payload
/// `{ session_id, line }`.
#[tauri::command]
pub async fn coding_agent_start_session(
    folder: String,
    prompt: String,
    session_id: String,
    id_token: String,
    backend_url: String,
    app: AppHandle,
) -> Result<(), String> {
    let state: State<CodingAgentState> = app.state();

    let pi_dir = pi_resource_dir(&app)?;
    let ext_backend = pi_dir.join("extensions/nooto-backend/index.ts");
    let ext_perms = pi_dir.join("extensions/nooto-permissions/index.ts");
    let ext_td = pi_dir.join("extensions/nooto-td/index.ts");

    // Validate extensions exist before spawning so the error is actionable.
    for (label, path) in [
        ("nooto-backend", &ext_backend),
        ("nooto-permissions", &ext_perms),
        ("nooto-td", &ext_td),
    ] {
        if !path.exists() {
            return Err(format!("{label} extension not found at {}", path.display()));
        }
    }

    // Resolve binary: Node wrapper in debug, compiled sidecar in release.
    #[cfg(debug_assertions)]
    let pi_bin = pi_dir.join("node_modules/.bin/pi");

    #[cfg(not(debug_assertions))]
    let pi_bin = {
        // Replicate tauri_plugin_shell's relative_command_path: sidecar lives
        // next to the app binary in Contents/MacOS/.
        let exe_dir = std::env::current_exe()
            .map_err(|e| format!("current_exe() failed: {e}"))?
            .parent()
            .ok_or("current_exe() has no parent")?
            .to_path_buf();

        // Tauri appends the target triple at bundle time, e.g.
        // `nooto-pi-agent-aarch64-apple-darwin`.  Ask the shell plugin to
        // validate the name is declared; the resolved path comes from exe_dir.
        let _ = app
            .shell()
            .sidecar("nooto-pi-agent")
            .map_err(|e| format!("sidecar 'nooto-pi-agent' not declared: {e}"))?;

        std::fs::read_dir(&exe_dir)
            .map_err(|e| format!("Cannot read MacOS/ dir: {e}"))?
            .filter_map(|e| e.ok())
            .map(|e| e.path())
            .find(|p| {
                p.file_name()
                    .and_then(|n| n.to_str())
                    .map(|n| n.starts_with("nooto-pi-agent-"))
                    .unwrap_or(false)
            })
            .ok_or_else(|| format!("nooto-pi-agent-* not found in {}", exe_dir.display()))?
    };

    let mut cmd = std::process::Command::new(&pi_bin);
    cmd.current_dir(&folder)
        .env("NOOTO_BACKEND_URL", &backend_url)
        .env("NOOTO_ID_TOKEN", &id_token);

    // Release only: redirect Pi's asset resolver to the bundled resource dir.
    // Not needed in debug because the Node.js wrapper walks its own package root.
    #[cfg(not(debug_assertions))]
    cmd.env("PI_PACKAGE_DIR", path_str(&pi_dir)?);

    cmd.args([
        "--mode", "rpc",
        "-e", path_str(&ext_backend)?,
        "-e", path_str(&ext_perms)?,
        "-e", path_str(&ext_td)?,
        "--provider", "nooto-backend",
        "--model", "nooto-backend/qwen3.6-35b-a3b",
        "--no-session",
    ])
    .stdin(std::process::Stdio::piped())
    .stdout(std::process::Stdio::piped())
    .stderr(std::process::Stdio::null());

    let mut child = cmd.spawn().map_err(|e| format!("Failed to spawn Pi sidecar: {e}"))?;
    let mut stdin = child.stdin.take().ok_or("Pi sidecar stdin unavailable")?;
    let stdout = child.stdout.take().ok_or("Pi sidecar stdout unavailable")?;

    writeln!(
        stdin,
        "{}",
        serde_json::json!({ "id": "r1", "type": "prompt", "message": prompt })
    )
    .map_err(|e| format!("Failed to write initial prompt: {e}"))?;

    {
        let mut children = state.children.lock().map_err(|e| format!("lock poisoned: {e}"))?;
        let mut stdins = state.stdins.lock().map_err(|e| format!("lock poisoned: {e}"))?;
        children.insert(session_id.clone(), child);
        stdins.insert(session_id.clone(), stdin);
    }

    let app_handle = app.clone();
    let sid = session_id.clone();
    tauri::async_runtime::spawn(async move {
        use std::io::BufRead;

        for raw_line in std::io::BufReader::new(stdout).lines() {
            match raw_line {
                Ok(line) if !line.is_empty() => {
                    let parsed: Value =
                        serde_json::from_str(&line).unwrap_or_else(|_| Value::String(line));
                    let _ = app_handle.emit(
                        "coding-agent:event",
                        serde_json::json!({ "session_id": sid, "line": parsed }),
                    );
                }
                Ok(_) => {}
                Err(e) => {
                    tracing::warn!("[coding_agent] stdout read error: {e}");
                    break;
                }
            }
        }

        // Pipe closed — let the frontend know the session ended.
        let _ = app_handle.emit(
            "coding-agent:event",
            serde_json::json!({
                "session_id": sid,
                "line": { "type": "agent_end", "messages": [] }
            }),
        );
        tracing::info!("[coding_agent] session {sid} reader exited");
    });

    Ok(())
}

/// Write a follow-up prompt to a running session's stdin.
#[tauri::command]
pub async fn coding_agent_send_message(
    session_id: String,
    message: String,
    app: AppHandle,
) -> Result<(), String> {
    let state: State<CodingAgentState> = app.state();
    let mut stdins = state.stdins.lock().map_err(|e| format!("lock poisoned: {e}"))?;
    let stdin = stdins
        .get_mut(&session_id)
        .ok_or_else(|| format!("No active session: {session_id}"))?;
    writeln!(
        stdin,
        "{}",
        serde_json::json!({ "type": "prompt", "message": message, "streamingBehavior": "steer" })
    )
    .map_err(|e| format!("Failed to write to Pi stdin: {e}"))
}

/// Gracefully shut down a session: send `{"type":"shutdown"}`, wait up to 2 s,
/// then kill if still alive.
#[tauri::command]
pub async fn coding_agent_stop_session(session_id: String, app: AppHandle) -> Result<(), String> {
    let state: State<CodingAgentState> = app.state();

    {
        let mut stdins = state.stdins.lock().map_err(|e| format!("lock poisoned: {e}"))?;
        if let Some(stdin) = stdins.get_mut(&session_id) {
            let _ = writeln!(stdin, r#"{{"type":"shutdown"}}"#);
        }
        stdins.remove(&session_id);
    }

    let child_opt = {
        let mut children = state.children.lock().map_err(|e| format!("lock poisoned: {e}"))?;
        children.remove(&session_id)
    };

    if let Some(mut child) = child_opt {
        let deadline = std::time::Instant::now() + Duration::from_secs(2);
        loop {
            match child.try_wait() {
                Ok(Some(_)) => break,
                Ok(None) => {
                    if std::time::Instant::now() >= deadline {
                        let _ = child.kill();
                        break;
                    }
                    tokio::time::sleep(Duration::from_millis(100)).await;
                }
                Err(e) => {
                    tracing::warn!("[coding_agent] try_wait error: {e}");
                    let _ = child.kill();
                    break;
                }
            }
        }
    }

    Ok(())
}
