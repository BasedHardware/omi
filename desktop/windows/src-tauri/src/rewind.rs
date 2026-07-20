use std::{
    fs,
    path::{Path, PathBuf},
    sync::{Mutex, MutexGuard},
};

#[cfg(target_os = "macos")]
use std::process::Command;

use base64::{engine::general_purpose::STANDARD, Engine};
use rusqlite::{params, Connection, OptionalExtension};
use serde::{Deserialize, Serialize};
#[cfg(target_os = "macos")]
use tauri::Manager;
use tauri::{AppHandle, Emitter, State};

use crate::native;

#[cfg(target_os = "macos")]
#[link(name = "CoreGraphics", kind = "framework")]
unsafe extern "C" {
    fn CGPreflightScreenCaptureAccess() -> bool;
    fn CGRequestScreenCaptureAccess() -> bool;
}

const MAX_FRAME_BYTES: u64 = 8 * 1024 * 1024;
const SEARCH_TOKEN_LIMIT: usize = 8;
const SEARCH_QUERY_CHAR_LIMIT: usize = 512;
const SEARCH_RESULT_LIMIT: usize = 500;
const GROUP_WINDOW_MS: i64 = 30_000;
const SETTINGS_CHANGED: &str = "omi://rewind-settings";
#[cfg(target_os = "macos")]
const CAPTURE_ERROR: &str = "omi://rewind-capture-error";

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[cfg_attr(not(test), allow(dead_code))]
enum CapturePlatform {
    Linux,
    Macos,
    Windows,
}

#[derive(Clone, Debug, Serialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase")]
pub struct RewindCaptureCapability {
    pub supported: bool,
    pub reason: String,
}

fn capture_capability_for(platform: CapturePlatform) -> RewindCaptureCapability {
    let reason = match platform {
        CapturePlatform::Linux => {
            "Rewind capture requires a PipeWire portal host on Linux, which is not linked yet"
        }
        CapturePlatform::Macos => "",
        CapturePlatform::Windows => {
            "Rewind capture requires the Windows Graphics Capture host, which is not linked yet"
        }
    };
    RewindCaptureCapability {
        supported: platform == CapturePlatform::Macos,
        reason: reason.to_owned(),
    }
}

fn capture_capability() -> RewindCaptureCapability {
    #[cfg(target_os = "linux")]
    {
        return capture_capability_for(CapturePlatform::Linux);
    }
    #[cfg(target_os = "macos")]
    {
        return macos_capture_capability();
    }
    #[cfg(target_os = "windows")]
    {
        return capture_capability_for(CapturePlatform::Windows);
    }
    #[allow(unreachable_code)]
    RewindCaptureCapability {
        supported: false,
        reason: "Rewind capture is unavailable on this platform".to_owned(),
    }
}

#[cfg(target_os = "macos")]
fn macos_capture_capability() -> RewindCaptureCapability {
    // SAFETY: CoreGraphics exposes this process-local TCC preflight function without pointers.
    if unsafe { CGPreflightScreenCaptureAccess() } {
        capture_capability_for(CapturePlatform::Macos)
    } else {
        RewindCaptureCapability {
            supported: false,
            reason: "Screen Recording permission is required for Rewind capture".to_owned(),
        }
    }
}

pub fn start_capture_scheduler(app: AppHandle) {
    #[cfg(not(target_os = "macos"))]
    let _ = app;
    #[cfg(target_os = "macos")]
    tauri::async_runtime::spawn(async move {
        loop {
            let settings = match app.state::<RewindStore>().settings() {
                Ok(settings) => settings,
                Err(error) => {
                    report_capture_error(&app, error);
                    tokio::time::sleep(std::time::Duration::from_secs(1)).await;
                    continue;
                }
            };
            if settings.capture_enabled && macos_capture_capability().supported {
                let capture_app = app.clone();
                match tauri::async_runtime::spawn_blocking(move || {
                    capture_app.state::<RewindStore>().capture_primary_display()
                })
                .await
                {
                    Ok(Ok(_)) => {}
                    Ok(Err(error)) => report_capture_error(&app, error),
                    Err(error) => report_capture_error(&app, error.to_string()),
                }
            }
            tokio::time::sleep(std::time::Duration::from_millis(
                settings.interval_ms as u64,
            ))
            .await;
        }
    });
}

#[cfg(target_os = "macos")]
fn report_capture_error(app: &AppHandle, error: String) {
    eprintln!("Omi Rewind capture failed: {error}");
    if let Err(emit_error) = app.emit(CAPTURE_ERROR, error) {
        eprintln!("Omi Rewind could not report its capture failure: {emit_error}");
    }
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase")]
pub struct RewindFrame {
    pub id: Option<i64>,
    pub ts: i64,
    pub app: String,
    pub window_title: String,
    pub process_name: String,
    pub ocr_text: String,
    pub image_path: String,
    pub width: i64,
    pub height: i64,
    pub indexed: i64,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase")]
pub struct RewindSearchGroup {
    pub id: String,
    pub app: String,
    pub window_title: String,
    pub start_ts: i64,
    pub end_ts: i64,
    pub frames: Vec<RewindFrame>,
    pub representative: RewindFrame,
    pub match_snippet: String,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase")]
pub struct RewindSettings {
    pub capture_enabled: bool,
    pub interval_ms: i64,
    pub retention_days: i64,
    pub excluded_apps: Vec<String>,
}

impl Default for RewindSettings {
    fn default() -> Self {
        Self {
            capture_enabled: true,
            interval_ms: 1_000,
            retention_days: 14,
            excluded_apps: Vec::new(),
        }
    }
}

pub struct RewindStore {
    connection: Mutex<Connection>,
    root: Mutex<PathBuf>,
    settings_file: Mutex<PathBuf>,
}

impl RewindStore {
    pub fn open(database_file: &Path) -> Result<Self, String> {
        let root = native::data_root().map_err(|error| error.to_string())?;
        Self::open_at(database_file, &root)
    }

    fn open_at(database_file: &Path, root: &Path) -> Result<Self, String> {
        fs::create_dir_all(root).map_err(|error| error.to_string())?;
        let connection = Connection::open(database_file).map_err(|error| error.to_string())?;
        connection
            .execute_batch(
                "PRAGMA journal_mode = WAL;
                 CREATE TABLE IF NOT EXISTS rewind_frames (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   ts INTEGER NOT NULL,
                   app TEXT NOT NULL DEFAULT '',
                   window_title TEXT NOT NULL DEFAULT '',
                   process_name TEXT NOT NULL DEFAULT '',
                   ocr_text TEXT NOT NULL DEFAULT '',
                   image_path TEXT NOT NULL,
                   width INTEGER NOT NULL DEFAULT 0,
                   height INTEGER NOT NULL DEFAULT 0,
                   indexed INTEGER NOT NULL DEFAULT 0
                 );
                 CREATE INDEX IF NOT EXISTS idx_rewind_frames_ts ON rewind_frames(ts);
                 CREATE INDEX IF NOT EXISTS idx_rewind_frames_indexed ON rewind_frames(indexed);",
            )
            .map_err(|error| error.to_string())?;
        Ok(Self {
            connection: Mutex::new(connection),
            root: Mutex::new(root.join("rewind")),
            settings_file: Mutex::new(root.join("rewind-settings.json")),
        })
    }

    pub fn close(&self) -> Result<(), String> {
        let mut guard = self.connection.lock().map_err(|error| error.to_string())?;
        *guard = Connection::open_in_memory().map_err(|error| error.to_string())?;
        Ok(())
    }

    pub fn reroot(&self, database_file: &Path, root: &Path) -> Result<(), String> {
        let rewind_root = root.join("rewind");
        let settings_file = root.join("rewind-settings.json");
        fs::create_dir_all(&rewind_root).map_err(|error| error.to_string())?;
        let connection = Connection::open(database_file).map_err(|error| error.to_string())?;
        connection
            .execute_batch(
                "PRAGMA journal_mode = WAL;
                 CREATE TABLE IF NOT EXISTS rewind_frames (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   ts INTEGER NOT NULL,
                   app TEXT NOT NULL DEFAULT '',
                   window_title TEXT NOT NULL DEFAULT '',
                   process_name TEXT NOT NULL DEFAULT '',
                   ocr_text TEXT NOT NULL DEFAULT '',
                   image_path TEXT NOT NULL,
                   width INTEGER NOT NULL DEFAULT 0,
                   height INTEGER NOT NULL DEFAULT 0,
                   indexed INTEGER NOT NULL DEFAULT 0
                 );
                 CREATE INDEX IF NOT EXISTS idx_rewind_frames_ts ON rewind_frames(ts);
                 CREATE INDEX IF NOT EXISTS idx_rewind_frames_indexed ON rewind_frames(indexed);",
            )
            .map_err(|error| error.to_string())?;
        {
            let mut guard = self.connection.lock().map_err(|error| error.to_string())?;
            *guard = connection;
        }
        *self.root.lock().map_err(|error| error.to_string())? = rewind_root;
        *self
            .settings_file
            .lock()
            .map_err(|error| error.to_string())? = settings_file;
        Ok(())
    }

    fn connection(&self) -> Result<MutexGuard<'_, Connection>, String> {
        self.connection.lock().map_err(|error| error.to_string())
    }

    fn frame(row: &rusqlite::Row<'_>) -> rusqlite::Result<RewindFrame> {
        Ok(RewindFrame {
            id: row.get(0)?,
            ts: row.get(1)?,
            app: row.get(2)?,
            window_title: row.get(3)?,
            process_name: row.get(4)?,
            ocr_text: row.get(5)?,
            image_path: row.get(6)?,
            width: row.get(7)?,
            height: row.get(8)?,
            indexed: row.get(9)?,
        })
    }

    pub(crate) fn list(&self, from: i64, to: i64) -> Result<Vec<RewindFrame>, String> {
        let connection = self.connection()?;
        let mut statement = connection
            .prepare("SELECT id, ts, app, window_title, process_name, ocr_text, image_path, width, height, indexed FROM rewind_frames WHERE ts BETWEEN ?1 AND ?2 ORDER BY ts")
            .map_err(|error| error.to_string())?;
        let frames = statement
            .query_map(params![from, to], Self::frame)
            .map_err(|error| error.to_string())?
            .collect::<Result<Vec<_>, _>>()
            .map_err(|error| error.to_string())?;
        Ok(frames)
    }

    fn bounds(&self) -> Result<Option<RewindBounds>, String> {
        let connection = self.connection()?;
        connection
            .query_row("SELECT MIN(ts), MAX(ts) FROM rewind_frames", [], |row| {
                Ok((row.get::<_, Option<i64>>(0)?, row.get::<_, Option<i64>>(1)?))
            })
            .map(|(min, max)| min.zip(max).map(|(min, max)| RewindBounds { min, max }))
            .map_err(|error| error.to_string())
    }

    fn search(&self, query: &str) -> Result<Vec<RewindSearchGroup>, String> {
        let tokens = search_tokens(query);
        if tokens.is_empty() {
            return Ok(Vec::new());
        }
        let where_clause = std::iter::repeat(
            "(ocr_text LIKE ? ESCAPE '\\' OR window_title LIKE ? ESCAPE '\\' OR app LIKE ? ESCAPE '\\')",
        )
        .take(tokens.len())
        .collect::<Vec<_>>()
        .join(" AND ");
        let mut values = Vec::with_capacity(tokens.len() * 3 + 1);
        for token in &tokens {
            let pattern = format!("%{}%", escape_like(token));
            values.extend([pattern.clone(), pattern.clone(), pattern]);
        }
        let connection = self.connection()?;
        let sql = format!("SELECT id, ts, app, window_title, process_name, ocr_text, image_path, width, height, indexed FROM rewind_frames WHERE {where_clause} ORDER BY ts DESC LIMIT ?");
        let mut statement = connection
            .prepare(&sql)
            .map_err(|error| error.to_string())?;
        let mut parameters = values.iter().map(String::as_str).collect::<Vec<_>>();
        let limit = SEARCH_RESULT_LIMIT.to_string();
        parameters.push(&limit);
        let frames = statement
            .query_map(rusqlite::params_from_iter(parameters), Self::frame)
            .map_err(|error| error.to_string())?
            .collect::<Result<Vec<_>, _>>()
            .map_err(|error| error.to_string())?;
        Ok(group_frames(frames, query))
    }

    fn latest_ocr_text(&self) -> Result<String, String> {
        let connection = self.connection()?;
        connection
            .query_row(
                "SELECT ocr_text FROM rewind_frames WHERE TRIM(ocr_text) <> '' ORDER BY ts DESC LIMIT 1",
                [],
                |row| row.get(0),
            )
            .optional()
            .map(|text| text.unwrap_or_default())
            .map_err(|error| error.to_string())
    }

    fn read_frame(&self, image_path: &str) -> Result<String, String> {
        let root = self.root.lock().map_err(|error| error.to_string())?;
        let root = root
            .canonicalize()
            .map_err(|_| "Rewind frame root is unavailable")?;
        let candidate = Path::new(image_path);
        if !candidate
            .extension()
            .and_then(|extension| extension.to_str())
            .is_some_and(|extension| extension.eq_ignore_ascii_case("jpg"))
        {
            return Err("invalid Rewind frame path".into());
        }
        let path = candidate
            .canonicalize()
            .map_err(|_| "invalid Rewind frame path")?;
        if !path.starts_with(&root) || !path.is_file() {
            return Err("invalid Rewind frame path".into());
        }
        let metadata = fs::metadata(&path).map_err(|error| error.to_string())?;
        if metadata.len() > MAX_FRAME_BYTES {
            return Err("Rewind frame exceeds preview size limit".into());
        }
        let bytes = fs::read(path).map_err(|error| error.to_string())?;
        Ok(format!("data:image/jpeg;base64,{}", STANDARD.encode(bytes)))
    }

    fn settings(&self) -> Result<RewindSettings, String> {
        let settings_file = self
            .settings_file
            .lock()
            .map_err(|error| error.to_string())?;
        match fs::read(&*settings_file) {
            Ok(bytes) => serde_json::from_slice(&bytes)
                .map(sanitize_settings)
                .map_err(|error| format!("invalid Rewind settings: {error}")),
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                Ok(RewindSettings::default())
            }
            Err(error) => Err(format!("could not read Rewind settings: {error}")),
        }
    }

    fn update_settings(&self, settings: RewindSettings) -> Result<RewindSettings, String> {
        let settings = sanitize_settings(settings);
        if settings.capture_enabled {
            let capability = capture_capability();
            if !capability.supported {
                return Err(capability.reason);
            }
        }
        let bytes = serde_json::to_vec(&settings).map_err(|error| error.to_string())?;
        let settings_file = self
            .settings_file
            .lock()
            .map_err(|error| error.to_string())?;
        fs::write(&*settings_file, bytes).map_err(|error| error.to_string())?;
        Ok(settings)
    }

    fn prune(&self) -> Result<usize, String> {
        let retention_ms = self.settings()?.retention_days.saturating_mul(86_400_000);
        let cutoff = now_ms().saturating_sub(retention_ms);
        let mut connection = self.connection()?;
        let transaction = connection
            .transaction()
            .map_err(|error| error.to_string())?;
        let paths = transaction
            .prepare("SELECT image_path FROM rewind_frames WHERE ts < ?1")
            .and_then(|mut statement| {
                statement
                    .query_map([cutoff], |row| row.get::<_, String>(0))?
                    .collect::<Result<Vec<_>, _>>()
            })
            .map_err(|error| error.to_string())?;
        transaction
            .execute("DELETE FROM rewind_frames WHERE ts < ?1", [cutoff])
            .map_err(|error| error.to_string())?;
        transaction.commit().map_err(|error| error.to_string())?;
        let count = paths.len();
        for path in paths {
            self.remove_frame(&path)?;
        }
        Ok(count)
    }

    fn remove_frame(&self, image_path: &str) -> Result<(), String> {
        let root = self.root.lock().map_err(|error| error.to_string())?;
        let root = root
            .canonicalize()
            .map_err(|_| "Rewind frame root is unavailable")?;
        let path = match Path::new(image_path).canonicalize() {
            Ok(path) => path,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(()),
            Err(_) => return Err("invalid Rewind frame path".into()),
        };
        if path.starts_with(root)
            && path
                .extension()
                .and_then(|extension| extension.to_str())
                .is_some_and(|extension| extension.eq_ignore_ascii_case("jpg"))
        {
            fs::remove_file(path).map_err(|error| error.to_string())?;
        }
        Ok(())
    }

    #[cfg(target_os = "macos")]
    fn capture_primary_display(&self) -> Result<Option<RewindFrame>, String> {
        if !self.settings()?.capture_enabled {
            return Ok(None);
        }
        let root = self.root.lock().map_err(|error| error.to_string())?;
        fs::create_dir_all(&*root).map_err(|error| error.to_string())?;
        let ts = now_ms();
        let image_path = root.join(format!("{ts}.jpg"));
        drop(root);
        let status = Command::new("/usr/sbin/screencapture")
            .args(["-x", "-t", "jpg"])
            .arg(&image_path)
            .status()
            .map_err(|error| error.to_string())?;
        if !status.success() {
            return Err("macOS screen capture failed".to_owned());
        }
        let status = Command::new("/usr/bin/sips")
            .args(["-Z", "1280"])
            .arg(&image_path)
            .status()
            .map_err(|error| error.to_string())?;
        if !status.success() {
            let _ = fs::remove_file(&image_path);
            return Err("macOS image resize failed".to_owned());
        }
        let metadata = fs::metadata(&image_path).map_err(|error| error.to_string())?;
        if metadata.len() > MAX_FRAME_BYTES {
            let _ = fs::remove_file(&image_path);
            return Err("Rewind frame exceeds preview size limit".to_owned());
        }
        let connection = self.connection()?;
        let result = connection.execute(
            "INSERT INTO rewind_frames (ts, image_path, width, height) VALUES (?1, ?2, ?3, ?4)",
            params![ts, image_path.to_string_lossy(), 0, 0],
        );
        if let Err(error) = result {
            let _ = fs::remove_file(&image_path);
            return Err(error.to_string());
        }
        Ok(Some(RewindFrame {
            id: Some(connection.last_insert_rowid()),
            ts,
            app: String::new(),
            window_title: String::new(),
            process_name: String::new(),
            ocr_text: String::new(),
            image_path: image_path.to_string_lossy().into_owned(),
            width: 0,
            height: 0,
            indexed: 0,
        }))
    }
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct RewindBounds {
    pub min: i64,
    pub max: i64,
}

fn sanitize_settings(settings: RewindSettings) -> RewindSettings {
    RewindSettings {
        capture_enabled: settings.capture_enabled,
        interval_ms: if settings.interval_ms > 0 {
            settings.interval_ms
        } else {
            1_000
        },
        retention_days: settings.retention_days.max(1),
        excluded_apps: settings
            .excluded_apps
            .into_iter()
            .map(|app| app.trim().to_owned())
            .filter(|app| !app.is_empty())
            .collect(),
    }
}

fn search_tokens(query: &str) -> Vec<&str> {
    let limit = query
        .char_indices()
        .nth(SEARCH_QUERY_CHAR_LIMIT)
        .map_or(query.len(), |(index, _)| index);
    query[..limit]
        .split_whitespace()
        .take(SEARCH_TOKEN_LIMIT)
        .collect()
}

fn escape_like(token: &str) -> String {
    token
        .replace('\\', "\\\\")
        .replace('%', "\\%")
        .replace('_', "\\_")
}

fn group_frames(mut frames: Vec<RewindFrame>, query: &str) -> Vec<RewindSearchGroup> {
    frames.sort_by_key(|frame| frame.ts);
    let mut groups = Vec::new();
    let mut current = Vec::new();
    for frame in frames {
        let starts_new_group = current.first().is_some_and(|first: &RewindFrame| {
            let previous = current.last().expect("non-empty Rewind frame group");
            previous.app != frame.app
                || previous.window_title != frame.window_title
                || frame.ts.saturating_sub(first.ts) > GROUP_WINDOW_MS
        });
        if starts_new_group {
            groups.push(make_group(std::mem::take(&mut current), query));
        }
        current.push(frame);
    }
    if !current.is_empty() {
        groups.push(make_group(current, query));
    }
    groups.sort_by_key(|group| std::cmp::Reverse(group.start_ts));
    groups
}

fn make_group(frames: Vec<RewindFrame>, query: &str) -> RewindSearchGroup {
    let first = &frames[0];
    let representative = frames
        .iter()
        .find(|frame| {
            frame
                .ocr_text
                .to_lowercase()
                .contains(&query.to_lowercase())
        })
        .cloned()
        .unwrap_or_else(|| frames.last().expect("non-empty Rewind frame group").clone());
    RewindSearchGroup {
        id: format!("{}-{}", first.app, first.ts),
        app: first.app.clone(),
        window_title: first.window_title.clone(),
        start_ts: first.ts,
        end_ts: frames.last().expect("non-empty Rewind frame group").ts,
        match_snippet: snippet(&representative.ocr_text, query),
        frames,
        representative,
    }
}

fn snippet(text: &str, query: &str) -> String {
    let lower = text.to_lowercase();
    let query = query.to_lowercase();
    let index = lower
        .find(&query)
        .filter(|index| text.is_char_boundary(*index))
        .unwrap_or(0);
    let start = text[..index]
        .char_indices()
        .rev()
        .nth(30)
        .map_or(0, |(index, _)| index);
    let end = text[index..]
        .char_indices()
        .nth(query.chars().count() + 30)
        .map_or(text.len(), |(offset, _)| index + offset);
    format!(
        "{}{}…",
        if start > 0 { "…" } else { "" },
        text[start..end].trim()
    )
}

fn now_ms() -> i64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map_or(0, |duration| {
            duration.as_millis().try_into().unwrap_or(i64::MAX)
        })
}

#[tauri::command]
pub fn rewind_frames(
    from: i64,
    to: i64,
    store: State<'_, RewindStore>,
) -> Result<Vec<RewindFrame>, String> {
    store.list(from, to)
}

#[tauri::command]
pub fn rewind_day_bounds(store: State<'_, RewindStore>) -> Result<Option<RewindBounds>, String> {
    store.bounds()
}

#[tauri::command]
pub fn rewind_search(
    query: String,
    store: State<'_, RewindStore>,
) -> Result<Vec<RewindSearchGroup>, String> {
    store.search(&query)
}

#[tauri::command]
pub fn rewind_frame_image(
    image_path: String,
    store: State<'_, RewindStore>,
) -> Result<String, String> {
    store.read_frame(&image_path)
}

#[tauri::command]
pub fn rewind_get_settings(store: State<'_, RewindStore>) -> Result<RewindSettings, String> {
    store.settings()
}

#[tauri::command]
pub fn rewind_capture_capability() -> RewindCaptureCapability {
    capture_capability()
}

#[tauri::command]
pub fn rewind_request_capture_permission(
    app: AppHandle,
) -> Result<RewindCaptureCapability, String> {
    #[cfg(target_os = "macos")]
    {
        if macos_capture_capability().supported {
            return Ok(capture_capability());
        }
        let (sender, receiver) = std::sync::mpsc::sync_channel(1);
        let app_handle = app.clone();
        app.run_on_main_thread(move || {
            if let Some(window) = app_handle.get_webview_window("main") {
                let _ = window.set_focus();
            }
            // SAFETY: CoreGraphics presents a process-local TCC request and takes no pointers.
            let _ = sender.send(unsafe { CGRequestScreenCaptureAccess() });
        })
        .map_err(|error| error.to_string())?;
        let _ = receiver.recv().map_err(|error| error.to_string())?;
        Ok(macos_capture_capability())
    }
    #[cfg(not(target_os = "macos"))]
    {
        let _ = app;
        Ok(capture_capability())
    }
}

#[tauri::command]
pub fn rewind_capture_now(store: State<'_, RewindStore>) -> Result<Option<RewindFrame>, String> {
    #[cfg(target_os = "macos")]
    {
        store.capture_primary_display()
    }
    #[cfg(not(target_os = "macos"))]
    {
        let _ = store;
        Err(capture_capability().reason)
    }
}

#[tauri::command]
pub fn rewind_set_settings(
    app: AppHandle,
    settings: RewindSettings,
    store: State<'_, RewindStore>,
) -> Result<RewindSettings, String> {
    let settings = store.update_settings(settings)?;
    app.emit(SETTINGS_CHANGED, &settings)
        .map_err(|error| error.to_string())?;
    Ok(settings)
}

#[tauri::command]
pub fn rewind_prune_now(store: State<'_, RewindStore>) -> Result<usize, String> {
    store.prune()
}

#[tauri::command]
pub fn screen_read_text(store: State<'_, RewindStore>) -> Result<String, String> {
    store.latest_ocr_text()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicU64, Ordering};

    static STORE_ID: AtomicU64 = AtomicU64::new(0);

    fn store() -> RewindStore {
        let root = std::env::temp_dir().join(format!(
            "omi-rewind-{}-{}",
            now_ms(),
            STORE_ID.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir_all(&root).unwrap();
        RewindStore::open_at(&root.join("omi.db"), &root).unwrap()
    }

    #[test]
    fn reads_the_electron_rewind_schema() {
        let store = store();
        store
            .connection()
            .unwrap()
            .execute(
                "INSERT INTO rewind_frames (ts, image_path) VALUES (?1, ?2)",
                params![42, "/missing.jpg"],
            )
            .unwrap();
        let frames = store.list(0, 100).unwrap();
        assert_eq!(frames[0].ts, 42);
        assert_eq!(frames[0].app, "");
        assert_eq!(
            store.bounds().unwrap(),
            Some(RewindBounds { min: 42, max: 42 })
        );
    }

    #[test]
    fn search_escapes_like_tokens_and_groups_matching_frames() {
        let store = store();
        let connection = store.connection().unwrap();
        connection
            .execute_batch(
                "INSERT INTO rewind_frames (ts, app, window_title, ocr_text, image_path) VALUES
                 (1, 'Browser', 'Docs', '100% match', '/one.jpg'),
                 (2, 'Browser', 'Docs', '100% match again', '/two.jpg'),
                 (3, 'Browser', 'Docs', '100x match', '/three.jpg');",
            )
            .unwrap();
        drop(connection);
        let results = store.search("100%").unwrap();
        assert_eq!(results.len(), 1);
        assert_eq!(results[0].frames.len(), 2);
    }

    #[test]
    fn sanitizes_persisted_settings() {
        let settings = sanitize_settings(RewindSettings {
            capture_enabled: false,
            interval_ms: 0,
            retention_days: 0,
            excluded_apps: vec!["  Browser  ".into(), " ".into()],
        });
        assert_eq!(settings.interval_ms, 1_000);
        assert_eq!(settings.retention_days, 1);
        assert_eq!(settings.excluded_apps, vec!["Browser".to_owned()]);
    }

    #[test]
    fn rejects_corrupt_persisted_settings() {
        let store = store();
        fs::write(&*store.settings_file.lock().unwrap(), b"not json").unwrap();

        assert!(store
            .settings()
            .unwrap_err()
            .contains("invalid Rewind settings"));
    }

    #[test]
    fn declares_only_the_linked_macos_capture_host_supported() {
        for platform in [
            CapturePlatform::Linux,
            CapturePlatform::Macos,
            CapturePlatform::Windows,
        ] {
            let capability = capture_capability_for(platform);
            assert_eq!(capability.supported, platform == CapturePlatform::Macos);
            if capability.supported {
                assert!(capability.reason.is_empty());
            } else {
                assert!(!capability.reason.is_empty());
            }
        }
    }

    #[test]
    fn capture_settings_require_the_current_platform_capability() {
        let store = store();
        let result = store.update_settings(RewindSettings {
            capture_enabled: true,
            ..RewindSettings::default()
        });
        let capability = capture_capability();
        if capability.supported {
            assert!(result.is_ok());
        } else {
            assert_eq!(result, Err(capability.reason));
        }
    }

    #[test]
    fn reads_only_bounded_jpegs_under_the_rewind_root() {
        let store = store();
        let root = store.root.lock().unwrap().clone();
        fs::create_dir_all(&root).unwrap();
        let frame = root.join("1.JPG");
        fs::write(&frame, b"jpeg").unwrap();
        assert_eq!(
            store.read_frame(&frame.to_string_lossy()).unwrap(),
            "data:image/jpeg;base64,anBlZw=="
        );
        assert!(store.read_frame("/tmp/1.jpg").is_err());
    }

    #[test]
    fn returns_the_latest_nonempty_ocr_text() {
        let store = store();
        let connection = store.connection().unwrap();
        connection
            .execute_batch(
                "INSERT INTO rewind_frames (ts, ocr_text, image_path) VALUES
                 (1, '', '/one.jpg'),
                 (2, 'older', '/two.jpg'),
                 (3, 'latest', '/three.jpg');",
            )
            .unwrap();
        drop(connection);
        assert_eq!(store.latest_ocr_text().unwrap(), "latest");
    }
}
