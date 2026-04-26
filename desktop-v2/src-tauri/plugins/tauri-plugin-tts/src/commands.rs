//! Tauri command handlers and supervisor for the TTS plugin.

use std::io::{BufRead, BufReader, Write};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
use std::time::Duration;

use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Emitter, Runtime};
use tokio::sync::oneshot;
use tracing;

// ---------------------------------------------------------------------------
// Public types
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TtsVoice {
    pub id: String,
    pub name: String,
    pub lang: String,
    pub quality: String,
}

// ---------------------------------------------------------------------------
// Request-ID counter
// ---------------------------------------------------------------------------

static REQUEST_COUNTER: AtomicU64 = AtomicU64::new(1);

fn next_request_id() -> String {
    REQUEST_COUNTER.fetch_add(1, Ordering::Relaxed).to_string()
}

// ---------------------------------------------------------------------------
// Voices response waiter — one-shot channel keyed by a disposable token
// ---------------------------------------------------------------------------

struct VoicesWaiter {
    tx: oneshot::Sender<Vec<TtsVoice>>,
}

static VOICES_WAITER: Mutex<Option<VoicesWaiter>> = Mutex::new(None);

// ---------------------------------------------------------------------------
// Supervisor — long-lived child process
// ---------------------------------------------------------------------------

struct TtsSupervisor {
    stdin: Mutex<std::process::ChildStdin>,
    /// The child is held so it gets reaped on Drop.
    _child: Mutex<Child>,
}

unsafe impl Send for TtsSupervisor {}
unsafe impl Sync for TtsSupervisor {}

impl TtsSupervisor {
    fn spawn<R: Runtime>(app: &AppHandle<R>) -> Result<Self, String> {
        let path = resolve_helper_path()?;
        tracing::info!("[tts] spawning speech-helper: {}", path.display());

        let mut child = Command::new(&path)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .map_err(|e| format!("failed to spawn speech-helper: {e}"))?;

        let stdin = child.stdin.take().ok_or("no stdin pipe")?;
        let stdout = child.stdout.take().ok_or("no stdout pipe")?;
        let stderr = child.stderr.take().ok_or("no stderr pipe")?;

        // Stderr logger thread.
        std::thread::Builder::new()
            .name("speech-helper-stderr".into())
            .spawn(move || {
                let reader = BufReader::new(stderr);
                for line in reader.lines().flatten() {
                    tracing::info!("[speech-helper] {}", line);
                }
            })
            .map_err(|e| format!("failed to spawn stderr logger: {e}"))?;

        // Stdout reader thread — parses JSON events and emits Tauri events.
        {
            let app = app.clone();
            std::thread::Builder::new()
                .name("speech-helper-stdout".into())
                .spawn(move || {
                    let reader = BufReader::new(stdout);
                    for line in reader.lines().flatten() {
                        handle_event_line(&app, &line);
                    }
                    tracing::info!("[tts] stdout reader thread exiting");
                })
                .map_err(|e| format!("failed to spawn stdout reader: {e}"))?;
        }

        Ok(Self {
            stdin: Mutex::new(stdin),
            _child: Mutex::new(child),
        })
    }

    fn send_command(&self, cmd: &serde_json::Value) -> Result<(), String> {
        let mut line = serde_json::to_string(cmd).map_err(|e| e.to_string())?;
        line.push('\n');
        let mut stdin = self.stdin.lock().map_err(|_| "stdin lock poisoned")?;
        stdin
            .write_all(line.as_bytes())
            .map_err(|e| format!("stdin write failed: {e}"))
    }
}

fn handle_event_line<R: Runtime>(app: &AppHandle<R>, line: &str) {
    let value: serde_json::Value = match serde_json::from_str(line) {
        Ok(v) => v,
        Err(e) => {
            tracing::warn!("[tts] failed to parse sidecar event: {} — line: {}", e, line);
            return;
        }
    };

    let event_name = match value.get("event").and_then(|v| v.as_str()) {
        Some(e) => e,
        None => {
            tracing::warn!("[tts] sidecar event missing 'event' key: {}", line);
            return;
        }
    };

    match event_name {
        "voices" => {
            let voices: Vec<TtsVoice> =
                serde_json::from_value(value["voices"].clone()).unwrap_or_default();
            let waiter = VOICES_WAITER.lock().ok().and_then(|mut g| g.take());
            if let Some(w) = waiter {
                let _ = w.tx.send(voices);
            }
        }
        "didStart" => {
            let _ = app.emit("tts:didStart", value.clone());
        }
        "willSpeakRange" => {
            let _ = app.emit("tts:willSpeakRange", value.clone());
        }
        "didFinish" => {
            let _ = app.emit("tts:didFinish", value.clone());
        }
        "didCancel" => {
            let _ = app.emit("tts:didCancel", value.clone());
        }
        "error" => {
            tracing::warn!("[tts] sidecar error: {}", line);
            let _ = app.emit("tts:error", value.clone());
        }
        _ => {
            tracing::warn!("[tts] unknown sidecar event '{}': {}", event_name, line);
        }
    }
}

// ---------------------------------------------------------------------------
// Global supervisor singleton — spawned lazily on first command.
// Wrapped in a Mutex so that concurrent first callers serialise the spawn:
// exactly one child process is ever started even under concurrent commands.
// ---------------------------------------------------------------------------

static SUPERVISOR: Mutex<Option<Arc<TtsSupervisor>>> = Mutex::new(None);

fn get_or_init_supervisor<R: Runtime>(app: &AppHandle<R>) -> Result<Arc<TtsSupervisor>, String> {
    let mut guard = SUPERVISOR.lock().map_err(|_| "supervisor lock poisoned")?;
    if let Some(sup) = guard.as_ref() {
        return Ok(sup.clone());
    }
    let sup = Arc::new(TtsSupervisor::spawn(app)?);
    *guard = Some(sup.clone());
    Ok(sup)
}

/// Returns the supervisor if already running, without spawning.
fn supervisor_if_running() -> Option<Arc<TtsSupervisor>> {
    SUPERVISOR.lock().ok()?.as_ref().cloned()
}

// ---------------------------------------------------------------------------
// Tauri commands
// ---------------------------------------------------------------------------

/// Speak `text` via the system TTS synthesizer.
///
/// If something is already speaking it is interrupted immediately.
/// Returns a request-id string that the caller can use to correlate the
/// `tts:didStart` / `tts:didFinish` / `tts:didCancel` events.
#[tauri::command]
pub fn tts_speak(
    app: AppHandle<impl Runtime>,
    text: String,
    voice: Option<String>,
    rate: Option<f64>,
) -> Result<String, String> {
    let sup = get_or_init_supervisor(&app)?;
    let id = next_request_id();

    let mut cmd = serde_json::json!({
        "action": "speak",
        "id": id,
        "text": text,
    });
    if let Some(v) = voice {
        cmd["voice"] = serde_json::Value::String(v);
    }
    if let Some(r) = rate {
        cmd["rate"] = serde_json::Value::from(r);
    }

    sup.send_command(&cmd)?;
    Ok(id)
}

/// Stop any currently speaking utterance immediately.
///
/// Returns `Ok(())` even if nothing is speaking (no-op in that case).
#[tauri::command]
pub fn tts_stop(_app: AppHandle<impl Runtime>) -> Result<(), String> {
    let Some(sup) = supervisor_if_running() else {
        return Ok(());
    };
    sup.send_command(&serde_json::json!({"action": "stop"}))
}

/// List all installed `AVSpeechSynthesisVoice` voices.
///
/// Sends a `voices` command to the sidecar and awaits its response via a
/// one-shot channel.  Times out after 3 seconds.
#[tauri::command]
pub async fn tts_list_voices(app: AppHandle<impl Runtime>) -> Result<Vec<TtsVoice>, String> {
    let sup = get_or_init_supervisor(&app)?;

    let (tx, rx) = oneshot::channel::<Vec<TtsVoice>>();
    {
        let mut guard = VOICES_WAITER.lock().map_err(|_| "voices waiter lock poisoned")?;
        *guard = Some(VoicesWaiter { tx });
    }

    sup.send_command(&serde_json::json!({"action": "voices"}))?;

    tokio::time::timeout(Duration::from_secs(3), rx)
        .await
        .map_err(|_| "tts_list_voices: timed out after 3 s".to_string())?
        .map_err(|_| "tts_list_voices: one-shot channel dropped".to_string())
}

// ---------------------------------------------------------------------------
// Helper — binary resolution (mirrors system_audio_macos.rs pattern)
// ---------------------------------------------------------------------------

/// Locate the compiled speech-helper binary. Search order:
///   1. `OMI_SPEECH_HELPER` env override (manual testing).
///   2. Alongside the main executable (production bundle layout).
///   3. `swift-helpers/bin/speech-helper` walked up from the executable dir
///      (dev mode — `cargo run` from `desktop-v2/src-tauri/`).
fn resolve_helper_path() -> Result<PathBuf, String> {
    if let Ok(override_path) = std::env::var("OMI_SPEECH_HELPER") {
        let p = PathBuf::from(override_path);
        if p.is_file() {
            return Ok(p);
        }
    }
    if let Ok(exe) = std::env::current_exe() {
        if let Some(dir) = exe.parent() {
            let candidate = dir.join("speech-helper");
            if candidate.is_file() {
                return Ok(candidate);
            }
            let mut cur = dir.to_path_buf();
            for _ in 0..6 {
                let candidate = cur.join("swift-helpers/bin/speech-helper");
                if candidate.is_file() {
                    return Ok(candidate);
                }
                if !cur.pop() {
                    break;
                }
            }
        }
    }
    Err(
        "could not find speech-helper. Run `bash swift-helpers/speech/build.sh` \
         or set OMI_SPEECH_HELPER=/path/to/binary"
            .to_string(),
    )
}
