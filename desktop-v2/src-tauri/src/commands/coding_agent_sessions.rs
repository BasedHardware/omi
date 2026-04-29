//! Session listing, renaming, and deletion for the coding agent.
//!
//! Reads Pi JSONL session files directly from
//! `~/.nooto/coding-agent/sessions/<sha256(folder)[:12]>/`.
//! Each file starts with a `SessionHeader` JSON line carrying `id`, `cwd`,
//! `timestamp`, and optionally `name`.

use std::io::{BufRead, Read};
use std::path::PathBuf;

use serde::Serialize;

use super::coding_agent::session_dir_for_folder;

// ---------------------------------------------------------------------------
// Public types
// ---------------------------------------------------------------------------

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SessionMeta {
    pub id: String,
    pub file_path: String,
    pub cwd: String,
    pub name: Option<String>,
    /// Unix milliseconds taken from the `timestamp` field in the header line.
    pub created_at: i64,
    /// Unix milliseconds taken from the file mtime.
    pub modified_at: i64,
    /// Line count, capped at 1 000 (only first 256 KB is read).
    pub message_count: usize,
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/// `~/.nooto/coding-agent/sessions/`
fn sessions_root() -> Result<PathBuf, String> {
    let home = std::env::var("HOME")
        .map(PathBuf::from)
        .map_err(|_| "HOME environment variable not set".to_string())?;

    Ok(home.join(".nooto").join("coding-agent").join("sessions"))
}

/// Parse the Pi `SessionHeader` from the first line of a JSONL file.
/// Expected shape:
/// ```json
/// { "type": "session", "id": "…", "cwd": "…", "timestamp": "…", "name": "…" }
/// ```
fn parse_header(first_line: &str) -> Option<(String, String, String, Option<String>)> {
    let v: serde_json::Value = serde_json::from_str(first_line).ok()?;
    let obj = v.as_object()?;
    // Tolerate either "session" type or any header-looking object.
    let id = obj.get("id")?.as_str()?.to_string();
    let cwd = obj.get("cwd")?.as_str()?.to_string();
    let timestamp = obj.get("timestamp")?.as_str()?.to_string();
    let name = obj.get("name").and_then(|n| n.as_str()).map(|s| s.to_string());
    Some((id, cwd, timestamp, name))
}

/// Parse an ISO-8601 timestamp string to Unix milliseconds.
fn parse_iso_ms(ts: &str) -> i64 {
    // chrono is already a dependency via the Cargo.toml.
    use chrono::DateTime;
    DateTime::parse_from_rfc3339(ts)
        .map(|dt| dt.timestamp_millis())
        .unwrap_or(0)
}

/// Read the session metadata from a single JSONL path.
fn read_session_meta(path: &std::path::Path) -> Option<SessionMeta> {
    let file = std::fs::File::open(path).ok()?;
    let modified_at = file
        .metadata()
        .ok()
        .and_then(|m| m.modified().ok())
        .and_then(|t| t.duration_since(std::time::UNIX_EPOCH).ok())
        .map(|d| d.as_millis() as i64)
        .unwrap_or(0);
    let mut reader = std::io::BufReader::new(file);

    // First line: header.
    let mut first_line = String::new();
    reader.read_line(&mut first_line).ok()?;
    let first_line = first_line.trim_end();
    if first_line.is_empty() {
        return None;
    }

    let (id, cwd, timestamp, name) = parse_header(first_line)?;
    let created_at = parse_iso_ms(&timestamp);

    // Count remaining lines (≤ 1 000) from the first 256 KB.
    const PEEK_BYTES: usize = 256 * 1024;
    const LINE_CAP: usize = 1_000;

    let mut buf = vec![0u8; PEEK_BYTES];
    let n = reader.read(&mut buf).unwrap_or(0);
    let slice = &buf[..n];
    let extra_lines = slice.iter().filter(|&&b| b == b'\n').count().min(LINE_CAP);
    // +1 for the header line itself.
    let message_count = (extra_lines + 1).min(LINE_CAP);

    Some(SessionMeta {
        id,
        file_path: path.to_string_lossy().into_owned(),
        cwd,
        name,
        created_at,
        modified_at,
        message_count,
    })
}

// ---------------------------------------------------------------------------
// Commands
// ---------------------------------------------------------------------------

/// List sessions. If `folder` is given, scope to that project's subdir;
/// otherwise return all sessions across all projects.
/// Results are sorted by `modified_at` descending (most recent first).
#[tauri::command]
pub fn coding_agent_list_sessions(folder: Option<String>) -> Result<Vec<SessionMeta>, String> {
    let root = sessions_root()?;

    let subdirs: Vec<PathBuf> = if let Some(f) = folder {
        let subdir = session_dir_for_folder(&f)?;
        if subdir.exists() {
            vec![subdir]
        } else {
            vec![]
        }
    } else {
        // Walk all `<hash>/` subdirs.
        if !root.exists() {
            return Ok(vec![]);
        }
        std::fs::read_dir(&root)
            .map_err(|e| format!("Cannot read sessions dir: {e}"))?
            .filter_map(|e| e.ok())
            .map(|e| e.path())
            .filter(|p| p.is_dir())
            .collect()
    };

    let mut sessions: Vec<SessionMeta> = subdirs
        .into_iter()
        .flat_map(|dir| {
            std::fs::read_dir(&dir)
                .into_iter()
                .flatten()
                .filter_map(|e| e.ok())
                .map(|e| e.path())
                .filter(|p| {
                    p.extension()
                        .and_then(|ext| ext.to_str())
                        .map(|ext| ext == "jsonl")
                        .unwrap_or(false)
                })
                .filter_map(|p| read_session_meta(&p))
        })
        .collect();

    sessions.sort_by(|a, b| b.modified_at.cmp(&a.modified_at));
    Ok(sessions)
}

/// Delete a session JSONL file.
#[tauri::command]
pub fn coding_agent_delete_session(file_path: String) -> Result<(), String> {
    std::fs::remove_file(&file_path).map_err(|e| format!("Failed to delete session: {e}"))
}

/// Read a session JSONL and return every entry whose `type === "message"`,
/// stripped down to the `message` payload. The frontend translates these into
/// AgentEvents so the chat repopulates when a session is restored.
///
/// Pi's switch_session loads state internally without re-emitting message
/// events, which is why we have to load history on the client side.
#[tauri::command]
pub fn coding_agent_load_session_messages(file_path: String) -> Result<Vec<serde_json::Value>, String> {
    let f = std::fs::File::open(&file_path).map_err(|e| format!("Failed to open session file: {e}"))?;
    let reader = std::io::BufReader::new(f);
    let mut out = Vec::new();
    for line in reader.lines() {
        let line = line.map_err(|e| format!("Read error: {e}"))?;
        if line.is_empty() {
            continue;
        }
        let val: serde_json::Value = match serde_json::from_str(&line) {
            Ok(v) => v,
            Err(_) => continue,
        };
        if val.get("type").and_then(|v| v.as_str()) == Some("message") {
            if let Some(msg) = val.get("message").cloned() {
                out.push(msg);
            }
        }
    }
    Ok(out)
}

/// Rename a session by updating the `name` field in the header line.
/// Writes atomically via a temp-file + rename.
#[tauri::command]
pub fn coding_agent_rename_session(file_path: String, name: String) -> Result<(), String> {
    let path = std::path::Path::new(&file_path);

    // Read the full file.
    let content = std::fs::read_to_string(path)
        .map_err(|e| format!("Failed to read session file: {e}"))?;

    let first_line = content
        .lines()
        .next()
        .ok_or("Session file is empty")?;

    // Modify the header line's `name` field.
    let mut header: serde_json::Value =
        serde_json::from_str(first_line).map_err(|e| format!("Failed to parse header: {e}"))?;
    if let Some(obj) = header.as_object_mut() {
        if name.is_empty() {
            obj.remove("name");
        } else {
            obj.insert("name".to_string(), serde_json::Value::String(name));
        }
    }
    let new_header = serde_json::to_string(&header)
        .map_err(|e| format!("Failed to re-encode header: {e}"))?;

    // Build new content: updated header + original remainder lines.
    let mut out = String::with_capacity(content.len() + 128);
    out.push_str(&new_header);
    for line in content.lines().skip(1) {
        out.push('\n');
        out.push_str(line);
    }
    // Preserve a trailing newline if the original had one.
    if content.ends_with('\n') {
        out.push('\n');
    }

    // Atomic write: temp file in the same dir, then rename.
    let tmp_path = path.with_extension("jsonl.tmp");
    std::fs::write(&tmp_path, &out)
        .map_err(|e| format!("Failed to write temp session file: {e}"))?;
    std::fs::rename(&tmp_path, path)
        .map_err(|e| format!("Failed to rename temp session file: {e}"))?;

    Ok(())
}
