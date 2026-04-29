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

use sha2::{Digest, Sha256};
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
/// Debug: source dir at `<CARGO_MANIFEST_DIR>/sidecar/pi-agent/`. We do NOT
/// fall back to `<resource_dir>/pi-agent/` because Tauri may have populated a
/// stale partial copy there from `bundle.resources`, missing newly-added
/// extensions.
///
/// Release: `Contents/Resources/pi-agent/` (Tauri resource bundler).
#[cfg(debug_assertions)]
fn pi_resource_dir(_app: &AppHandle) -> Result<std::path::PathBuf, String> {
    let manifest_dir = env!("CARGO_MANIFEST_DIR");
    let candidate = std::path::Path::new(manifest_dir).join("sidecar/pi-agent");
    if candidate.exists() {
        Ok(candidate)
    } else {
        Err(format!(
            "sidecar/pi-agent not found at {} (CARGO_MANIFEST_DIR + sidecar/pi-agent)",
            candidate.display()
        ))
    }
}

#[cfg(not(debug_assertions))]
fn pi_resource_dir(app: &AppHandle) -> Result<std::path::PathBuf, String> {
    let resource_dir = app
        .path()
        .resource_dir()
        .map_err(|e| format!("resource_dir unavailable: {e}"))?;
    let candidate = resource_dir.join("pi-agent");
    if candidate.exists() {
        Ok(candidate)
    } else {
        Err(format!(
            "pi-agent resource bundle not found at {}",
            candidate.display()
        ))
    }
}

/// Convert a `PathBuf` to `&str`, returning an error instead of silently
/// producing an empty string on non-UTF-8 paths.
fn path_str(p: &std::path::Path) -> Result<&str, String> {
    p.to_str()
        .ok_or_else(|| format!("Path is not valid UTF-8: {}", p.display()))
}

/// Compute the per-project session directory:
/// `~/.nooto/coding-agent/sessions/<sha256(folder)[:12]>/`
///
/// Using a hash of the absolute folder path keeps the directory name
/// path-safe (no slashes, fixed length) while still being scoped per project.
pub fn session_dir_for_folder(folder: &str) -> Result<std::path::PathBuf, String> {
    let home = std::env::var("HOME")
        .map(std::path::PathBuf::from)
        .map_err(|_| "HOME environment variable not set".to_string())?;

    let mut hasher = Sha256::new();
    hasher.update(folder.as_bytes());
    let hash_bytes = hasher.finalize();
    // Take the first 12 hex characters (6 bytes).
    let hash_prefix: String = hash_bytes
        .iter()
        .take(6)
        .map(|b| format!("{:02x}", b))
        .collect();

    Ok(home
        .join(".nooto")
        .join("coding-agent")
        .join("sessions")
        .join(&hash_prefix))
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

/// Report whether the agent is in direct (self-hosted) or cloud mode, plus the
/// model id that direct mode will use. Lets the UI swap the dropdown for a
/// static badge when the picker is meaningless.
#[tauri::command]
pub fn coding_agent_get_mode_info() -> serde_json::Value {
    let direct_url = std::env::var("NOOTO_DIRECT_LLM_URL").ok();
    let direct_model = std::env::var("NOOTO_DIRECT_LLM_MODEL").ok();
    serde_json::json!({
        "direct": direct_url.is_some(),
        "directUrl": direct_url,
        "directModel": direct_model,
    })
}

/// Spawn the Pi sidecar, write the initial prompt, and start streaming events
/// back to the frontend as `"coding-agent:event"` with payload
/// `{ session_id, line }`.
///
/// When `session_path` is `Some`, Pi is asked to resume an existing session
/// via the RPC `switch_session` command (written to stdin before the prompt).
/// When `None`, Pi creates a fresh session in the per-project session-dir.
/// Image attachment forwarded into Pi's RPC `prompt` command.
/// Field names match Pi's expected `ImageContent` shape exactly.
#[derive(Debug, serde::Deserialize, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct AttachedImage {
    /// Always "image" — kept explicit for the JSON shape.
    #[serde(rename = "type")]
    pub kind: String,
    /// Base64-encoded image bytes (no data: prefix).
    pub data: String,
    /// MIME type, e.g. "image/png".
    pub mime_type: String,
}

#[tauri::command]
pub async fn coding_agent_start_session(
    folder: String,
    prompt: String,
    session_id: String,
    id_token: String,
    backend_url: String,
    model: Option<String>,
    session_path: Option<String>,
    images: Option<Vec<AttachedImage>>,
    app: AppHandle,
) -> Result<(), String> {
    // In direct mode (NOOTO_DIRECT_LLM_URL set), the Pi extension only
    // registers the single model named by NOOTO_DIRECT_LLM_MODEL — the
    // dropdown selection from the UI is irrelevant because the local server
    // probably doesn't serve Claude/GPT/etc. Override here so --model matches
    // what the extension registered.
    let resolved_model = if std::env::var("NOOTO_DIRECT_LLM_URL").is_ok() {
        std::env::var("NOOTO_DIRECT_LLM_MODEL").unwrap_or_else(|_| "qwen3.6-35b-a3b".to_string())
    } else {
        model.unwrap_or_else(|| "anthropic/claude-sonnet-4.5".to_string())
    };
    let model_arg = format!("nooto-backend/{}", resolved_model);
    let state: State<CodingAgentState> = app.state();

    let pi_dir = pi_resource_dir(&app)?;
    let ext_backend = pi_dir.join("extensions/nooto-backend/index.ts");
    let ext_perms = pi_dir.join("extensions/nooto-permissions/index.ts");
    let ext_td = pi_dir.join("extensions/nooto-td/index.ts");
    let ext_terminal = pi_dir.join("extensions/nooto-terminal/index.ts");
    let ext_mcp = pi_dir.join("extensions/nooto-mcp/index.ts");
    let ext_gstack = pi_dir.join("extensions/nooto-gstack/index.ts");

    // Validate extensions exist before spawning so the error is actionable.
    for (label, path) in [
        ("nooto-backend", &ext_backend),
        ("nooto-permissions", &ext_perms),
        ("nooto-td", &ext_td),
        ("nooto-terminal", &ext_terminal),
        ("nooto-mcp", &ext_mcp),
        ("nooto-gstack", &ext_gstack),
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

    // When set in the parent shell (e.g. `NOOTO_DIRECT_LLM_URL=http://<vllm-host>:<port>/v1`),
    // the Pi extension switches to direct mode and bypasses the cloud backend
    // entirely — pointing Pi straight at a self-hosted vLLM/Ollama endpoint.
    if let Ok(direct_url) = std::env::var("NOOTO_DIRECT_LLM_URL") {
        cmd.env("NOOTO_DIRECT_LLM_URL", direct_url);
    }
    if let Ok(direct_model) = std::env::var("NOOTO_DIRECT_LLM_MODEL") {
        cmd.env("NOOTO_DIRECT_LLM_MODEL", direct_model);
    }

    // Release only: redirect Pi's asset resolver to the bundled resource dir.
    // Not needed in debug because the Node.js wrapper walks its own package root.
    #[cfg(not(debug_assertions))]
    cmd.env("PI_PACKAGE_DIR", path_str(&pi_dir)?);

    let sess_dir = session_dir_for_folder(&folder)?;
    std::fs::create_dir_all(&sess_dir)
        .map_err(|e| format!("Cannot create session dir {}: {e}", sess_dir.display()))?;
    let sess_dir_str = path_str(&sess_dir)?.to_string();

    cmd.args([
        "--mode", "rpc",
        "-e", path_str(&ext_backend)?,
        "-e", path_str(&ext_perms)?,
        "-e", path_str(&ext_td)?,
        "-e", path_str(&ext_terminal)?,
        "-e", path_str(&ext_mcp)?,
        "-e", path_str(&ext_gstack)?,
        "--provider", "nooto-backend",
        "--model", &model_arg,
        "--session-dir", &sess_dir_str,
    ])
    .stdin(std::process::Stdio::piped())
    .stdout(std::process::Stdio::piped())
    .stderr(std::process::Stdio::piped());

    // Detach Pi (and every process Pi spawns — including dispatch_bash dev
    // servers) into its own session/process group. Without this, killing Pi
    // can cascade signals back through Tauri's group and take the whole app
    // down. With it, we can SIGTERM the Pi group cleanly and Tauri stays up.
    #[cfg(unix)]
    {
        use std::os::unix::process::CommandExt;
        unsafe {
            cmd.pre_exec(|| {
                if libc::setsid() == -1 {
                    return Err(std::io::Error::last_os_error());
                }
                Ok(())
            });
        }
    }

    let mut child = cmd.spawn().map_err(|e| format!("Failed to spawn Pi sidecar: {e}"))?;
    let mut stdin = child.stdin.take().ok_or("Pi sidecar stdin unavailable")?;
    let stdout = child.stdout.take().ok_or("Pi sidecar stdout unavailable")?;
    let stderr = child.stderr.take().ok_or("Pi sidecar stderr unavailable")?;

    // If a specific session file was requested, send `switch_session` first so
    // Pi loads the prior conversation before accepting the new prompt.
    if let Some(ref sp) = session_path {
        writeln!(
            stdin,
            "{}",
            serde_json::json!({ "type": "switch_session", "sessionPath": sp })
        )
        .map_err(|e| format!("Failed to write switch_session RPC: {e}"))?;
    }

    // An empty prompt with a session_path = pure restore: load the JSONL via
    // switch_session above, but don't kick off an agent turn. Pi would
    // otherwise call the model with an empty user message and the chat would
    // hang at "Starting agent…" forever (no turn_start, no text_delta).
    let send_initial = !prompt.is_empty() || images.as_ref().map_or(false, |v| !v.is_empty());
    if send_initial {
        let mut prompt_json = serde_json::json!({
            "id": "r1",
            "type": "prompt",
            "message": prompt,
        });
        if let Some(imgs) = images {
            if !imgs.is_empty() {
                prompt_json["images"] = serde_json::to_value(&imgs)
                    .map_err(|e| format!("Failed to serialize images: {e}"))?;
            }
        }
        writeln!(stdin, "{}", prompt_json)
            .map_err(|e| format!("Failed to write initial prompt: {e}"))?;
    }

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

    // Forward Pi sidecar stderr to the frontend as `extension_error` events so
    // spawn failures (Node missing, extension crash, etc.) surface in the UI
    // instead of being silently discarded.
    let app_handle_err = app.clone();
    let sid_err = session_id.clone();
    tauri::async_runtime::spawn(async move {
        use std::io::BufRead;
        for raw_line in std::io::BufReader::new(stderr).lines() {
            match raw_line {
                Ok(line) if !line.is_empty() => {
                    tracing::warn!("[coding_agent stderr] {line}");
                    let _ = app_handle_err.emit(
                        "coding-agent:event",
                        serde_json::json!({
                            "session_id": sid_err,
                            "line": { "type": "extension_error", "error": line }
                        }),
                    );
                }
                Ok(_) => {}
                Err(_) => break,
            }
        }
    });

    Ok(())
}

/// Write a single JSONL line to the stdin of a running session.
fn write_stdin_line(
    stdins: &mut std::sync::MutexGuard<HashMap<String, ChildStdin>>,
    session_id: &str,
    json_value: &Value,
) -> Result<(), String> {
    let stdin = stdins
        .get_mut(session_id)
        .ok_or_else(|| format!("No active session: {session_id}"))?;
    writeln!(stdin, "{json_value}").map_err(|e| format!("Failed to write to Pi stdin: {e}"))
}

/// Write a follow-up prompt to a running session's stdin. Optional image
/// attachments forward into Pi's RPC `images` field, which Pi includes in the
/// outgoing `UserMessage.content` to the model.
#[tauri::command]
pub async fn coding_agent_send_message(
    session_id: String,
    message: String,
    images: Option<Vec<AttachedImage>>,
    app: AppHandle,
) -> Result<(), String> {
    let state: State<CodingAgentState> = app.state();
    let mut stdins = state.stdins.lock().map_err(|e| format!("lock poisoned: {e}"))?;
    let mut prompt_json = serde_json::json!({
        "type": "prompt",
        "message": message,
        "streamingBehavior": "steer",
    });
    if let Some(imgs) = images {
        if !imgs.is_empty() {
            prompt_json["images"] = serde_json::to_value(&imgs)
                .map_err(|e| format!("Failed to serialize images: {e}"))?;
        }
    }
    write_stdin_line(&mut stdins, &session_id, &prompt_json)
}

/// Write a raw JSON value as a newline-terminated JSONL line to a running
/// session's stdin.  Used by the frontend to send Pi RPC commands that are
/// not prompts (e.g. `get_state`, `switch_session`, `set_session_name`).
#[tauri::command]
pub async fn coding_agent_send_raw_rpc(
    session_id: String,
    json_value: Value,
    app: AppHandle,
) -> Result<(), String> {
    let state: State<CodingAgentState> = app.state();
    let mut stdins = state.stdins.lock().map_err(|e| format!("lock poisoned: {e}"))?;
    write_stdin_line(&mut stdins, &session_id, &json_value)
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
        let pid = child.id() as i32;
        let deadline = std::time::Instant::now() + Duration::from_secs(2);
        loop {
            match child.try_wait() {
                Ok(Some(_)) => break,
                Ok(None) => {
                    if std::time::Instant::now() >= deadline {
                        kill_process_group(pid);
                        break;
                    }
                    tokio::time::sleep(Duration::from_millis(100)).await;
                }
                Err(e) => {
                    tracing::warn!("[coding_agent] try_wait error: {e}");
                    kill_process_group(pid);
                    break;
                }
            }
        }
    }

    Ok(())
}

/// Send SIGTERM (then SIGKILL after 500ms) to the entire process group whose
/// leader is `pid`. Pi was spawned with `setsid()` so this group includes Pi
/// AND every shell/dev-server it dispatched, but NOT the Tauri host. Without
/// the negative-pid form, an orphaned `npm run dev` would survive Stop and
/// keep its port bound.
#[cfg(unix)]
fn kill_process_group(pid: i32) {
    unsafe {
        // negative pid = process group
        libc::kill(-pid, libc::SIGTERM);
    }
    std::thread::sleep(Duration::from_millis(500));
    unsafe {
        libc::kill(-pid, libc::SIGKILL);
    }
}

#[cfg(not(unix))]
fn kill_process_group(_pid: i32) {
    // Windows: process groups work differently; fall back to per-process kill.
    // Implement when we ship Windows builds.
}
