use std::{
    collections::BTreeMap,
    fs,
    path::{Path, PathBuf},
    time::{Instant, SystemTime, UNIX_EPOCH},
};

use rusqlite::{params, params_from_iter, Connection};
use serde::{Deserialize, Serialize};
use tauri::State;

use super::KnowledgeStore;

const MAX_DEPTH: usize = 3;
const MAX_FILE_SIZE: u64 = 500 * 1024 * 1024;

#[derive(Default)]
pub struct FileIndexRuntime {
    last_run_at: Option<i64>,
    last_duration_ms: Option<i64>,
    running: bool,
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct IndexedFileRecord {
    path: String,
    filename: String,
    extension: String,
    file_type: String,
    size_bytes: i64,
    folder: String,
    depth: i64,
    created_at: i64,
    modified_at: i64,
    target_path: Option<String>,
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct IndexedAppRecord {
    name: String,
    path: String,
    modified_at: i64,
    target_path: Option<String>,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct FileIndexStatus {
    files_indexed: i64,
    by_type: BTreeMap<String, i64>,
    last_run_at: Option<i64>,
    last_duration_ms: Option<i64>,
    running: bool,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Capability {
    supported: bool,
    reason: Option<&'static str>,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct FileIndexCapabilities {
    start_menu_shortcuts: Capability,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct FileIndexDigest {
    total_files: i64,
    by_type: BTreeMap<String, i64>,
    by_extension: BTreeMap<String, i64>,
    top_folders: Vec<FolderCount>,
    active_folders: Vec<ActiveFolder>,
    apps: Vec<String>,
    sample_files: Vec<String>,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct FolderCount {
    folder: String,
    count: i64,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct ActiveFolder {
    folder: String,
    recent_count: i64,
    last_modified: i64,
}

pub(crate) fn initialize(connection: &Connection) -> Result<(), String> {
    connection
        .execute_batch(
            "CREATE TABLE IF NOT EXISTS indexed_files (
               path TEXT PRIMARY KEY,
               filename TEXT NOT NULL,
               extension TEXT NOT NULL,
               file_type TEXT NOT NULL,
               size_bytes INTEGER NOT NULL,
               folder TEXT NOT NULL,
               depth INTEGER NOT NULL,
               created_at INTEGER NOT NULL,
               modified_at INTEGER NOT NULL,
               indexed_at INTEGER NOT NULL,
               target_path TEXT
             );
             CREATE INDEX IF NOT EXISTS idx_indexed_files_type ON indexed_files(file_type);",
        )
        .map_err(|error| error.to_string())?;
    if !has_column(connection, "indexed_files", "target_path")? {
        connection
            .execute_batch("ALTER TABLE indexed_files ADD COLUMN target_path TEXT")
            .map_err(|error| error.to_string())?;
    }
    Ok(())
}

impl KnowledgeStore {
    pub(crate) fn status(&self) -> Result<FileIndexStatus, String> {
        let connection = self.connection()?;
        let files_indexed = connection
            .query_row("SELECT COUNT(*) FROM indexed_files", [], |row| row.get(0))
            .map_err(|error| error.to_string())?;
        let by_type = grouped(
            &connection,
            "SELECT file_type, COUNT(*) FROM indexed_files GROUP BY file_type",
        )?;
        let runtime = self.file_index.lock().map_err(|error| error.to_string())?;
        Ok(FileIndexStatus {
            files_indexed,
            by_type,
            last_run_at: runtime.last_run_at,
            last_duration_ms: runtime.last_duration_ms,
            running: runtime.running,
        })
    }

    pub(crate) fn scan(&self) -> Result<FileIndexStatus, String> {
        {
            let mut runtime = self.file_index.lock().map_err(|error| error.to_string())?;
            if runtime.running {
                drop(runtime);
                return self.status();
            }
            runtime.running = true;
        }
        let started = Instant::now();
        let result = (|| {
            let mut records = Vec::new();
            for root in scan_roots() {
                walk_files(&root, &mut records)?;
            }
            #[cfg(target_os = "windows")]
            for root in start_menu_roots() {
                walk_start_menu(&root, &mut records)?;
            }
            let mut connection = self.connection()?;
            let transaction = connection
                .transaction()
                .map_err(|error| error.to_string())?;
            transaction
                .execute("DELETE FROM indexed_files", [])
                .map_err(|error| error.to_string())?;
            let mut insert = transaction
                .prepare("INSERT OR REPLACE INTO indexed_files (path, filename, extension, file_type, size_bytes, folder, depth, created_at, modified_at, target_path, indexed_at) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11)")
                .map_err(|error| error.to_string())?;
            let indexed_at = now_ms();
            for record in records {
                insert
                    .execute(params![
                        record.path,
                        record.filename,
                        record.extension,
                        record.file_type,
                        record.size_bytes,
                        record.folder,
                        record.depth,
                        record.created_at,
                        record.modified_at,
                        record.target_path,
                        indexed_at
                    ])
                    .map_err(|error| error.to_string())?;
            }
            drop(insert);
            transaction.commit().map_err(|error| error.to_string())
        })();
        let mut runtime = self.file_index.lock().map_err(|error| error.to_string())?;
        runtime.running = false;
        if result.is_ok() {
            runtime.last_run_at = Some(now_ms());
            runtime.last_duration_ms = Some(started.elapsed().as_millis() as i64);
        }
        drop(runtime);
        result?;
        self.status()
    }

    pub(crate) fn apps(&self, limit: i64) -> Result<Vec<IndexedAppRecord>, String> {
        if !cfg!(target_os = "windows") {
            return Ok(Vec::new());
        }
        self.connection()?
            .prepare("SELECT filename, path, modified_at, target_path FROM indexed_files WHERE file_type = 'application' AND extension = 'lnk' ORDER BY modified_at DESC LIMIT ?1")
            .map_err(|error| error.to_string())?
            .query_map([limit.clamp(1, 200)], |row| Ok(IndexedAppRecord { name: row.get(0)?, path: row.get(1)?, modified_at: row.get(2)?, target_path: row.get(3)? }))
            .map_err(|error| error.to_string())?
            .collect::<Result<Vec<_>, _>>()
            .map_err(|error| error.to_string())
    }

    pub(crate) fn search_files(
        &self,
        query: &str,
        file_type: Option<&str>,
        limit: i64,
    ) -> Result<Vec<IndexedFileRecord>, String> {
        let connection = self.connection()?;
        let like = format!("%{query}%");
        let cap = limit.clamp(1, 200);
        let (sql, values) = if let Some(file_type) = file_type {
            ("SELECT path, filename, extension, file_type, size_bytes, folder, depth, created_at, modified_at, target_path FROM indexed_files WHERE (filename LIKE ? OR folder LIKE ?) AND file_type = ? ORDER BY modified_at DESC LIMIT ?", vec![rusqlite::types::Value::Text(like.clone()), rusqlite::types::Value::Text(like), rusqlite::types::Value::Text(file_type.to_owned()), rusqlite::types::Value::Integer(cap)])
        } else {
            ("SELECT path, filename, extension, file_type, size_bytes, folder, depth, created_at, modified_at, target_path FROM indexed_files WHERE (filename LIKE ? OR folder LIKE ?) AND file_type != 'application' ORDER BY modified_at DESC LIMIT ?", vec![rusqlite::types::Value::Text(like.clone()), rusqlite::types::Value::Text(like), rusqlite::types::Value::Integer(cap)])
        };
        let records = connection
            .prepare(sql)
            .map_err(|error| error.to_string())?
            .query_map(params_from_iter(values), indexed_file)
            .map_err(|error| error.to_string())?
            .collect::<Result<Vec<_>, _>>()
            .map_err(|error| error.to_string())?;
        Ok(records)
    }

    pub(crate) fn digest(&self) -> Result<FileIndexDigest, String> {
        let connection = self.connection()?;
        let total_files = connection
            .query_row(
                "SELECT COUNT(*) FROM indexed_files WHERE file_type != 'application'",
                [],
                |row| row.get(0),
            )
            .map_err(|error| error.to_string())?;
        let by_type = grouped(&connection, "SELECT file_type, COUNT(*) FROM indexed_files WHERE file_type != 'application' GROUP BY file_type")?;
        let by_extension = grouped(&connection, "SELECT extension, COUNT(*) FROM indexed_files WHERE file_type != 'application' AND extension != '' GROUP BY extension")?;
        let top_folders = connection.prepare("SELECT folder, COUNT(*) FROM indexed_files WHERE file_type != 'application' GROUP BY folder ORDER BY COUNT(*) DESC LIMIT 15").map_err(|error| error.to_string())?.query_map([], |row| Ok(FolderCount { folder: row.get(0)?, count: row.get(1)? })).map_err(|error| error.to_string())?.collect::<Result<Vec<_>, _>>().map_err(|error| error.to_string())?;
        let now = now_ms();
        let active_folders = connection.prepare("SELECT folder, COUNT(*), MAX(modified_at) FROM indexed_files WHERE file_type IN ('code', 'document') AND modified_at <= ?1 AND modified_at > ?2 GROUP BY folder ORDER BY COUNT(*) DESC, MAX(modified_at) DESC LIMIT 15").map_err(|error| error.to_string())?.query_map(params![now, now - 30 * 86_400_000], |row| Ok(ActiveFolder { folder: row.get(0)?, recent_count: row.get(1)?, last_modified: row.get(2)? })).map_err(|error| error.to_string())?.collect::<Result<Vec<_>, _>>().map_err(|error| error.to_string())?;
        let sample_files = connection.prepare("SELECT filename FROM indexed_files WHERE file_type != 'application' ORDER BY modified_at DESC LIMIT 20").map_err(|error| error.to_string())?.query_map([], |row| row.get(0)).map_err(|error| error.to_string())?.collect::<Result<Vec<String>, _>>().map_err(|error| error.to_string())?;
        drop(connection);
        Ok(FileIndexDigest {
            total_files,
            by_type,
            by_extension,
            top_folders,
            active_folders,
            apps: self.apps(100)?.into_iter().map(|app| app.name).collect(),
            sample_files,
        })
    }
}

fn has_column(connection: &Connection, table: &str, column: &str) -> Result<bool, String> {
    connection
        .prepare(&format!("PRAGMA table_info({table})"))
        .map_err(|error| error.to_string())?
        .query_map([], |row| row.get::<_, String>(1))
        .map_err(|error| error.to_string())?
        .collect::<Result<Vec<_>, _>>()
        .map_err(|error| error.to_string())
        .map(|columns| columns.iter().any(|name| name == column))
}

fn indexed_file(row: &rusqlite::Row<'_>) -> rusqlite::Result<IndexedFileRecord> {
    Ok(IndexedFileRecord {
        path: row.get(0)?,
        filename: row.get(1)?,
        extension: row.get(2)?,
        file_type: row.get(3)?,
        size_bytes: row.get(4)?,
        folder: row.get(5)?,
        depth: row.get(6)?,
        created_at: row.get(7)?,
        modified_at: row.get(8)?,
        target_path: row.get(9)?,
    })
}

fn grouped(connection: &Connection, sql: &str) -> Result<BTreeMap<String, i64>, String> {
    connection
        .prepare(sql)
        .map_err(|error| error.to_string())?
        .query_map([], |row| {
            Ok((row.get::<_, String>(0)?, row.get::<_, i64>(1)?))
        })
        .map_err(|error| error.to_string())?
        .collect::<Result<BTreeMap<_, _>, _>>()
        .map_err(|error| error.to_string())
}

fn now_ms() -> i64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis() as i64
}
fn system_time_ms(value: Result<SystemTime, std::io::Error>) -> i64 {
    value
        .ok()
        .and_then(|value| value.duration_since(UNIX_EPOCH).ok())
        .map(|value| value.as_millis() as i64)
        .unwrap_or_default()
}
fn scan_roots() -> Vec<PathBuf> {
    let Some(home) = std::env::var_os(if cfg!(target_os = "windows") {
        "USERPROFILE"
    } else {
        "HOME"
    })
    .map(PathBuf::from) else {
        return Vec::new();
    };
    let mut paths = [
        "Downloads",
        "Documents",
        "Desktop",
        "Developer",
        "Projects",
        "Code",
        "src",
        "repos",
        "Sites",
    ]
    .into_iter()
    .map(|name| home.join(name))
    .collect::<Vec<_>>();
    paths.push(home.join("source").join("repos"));
    paths.into_iter().filter(|path| path.is_dir()).collect()
}
#[cfg(target_os = "windows")]
fn start_menu_roots() -> Vec<PathBuf> {
    ["ProgramData", "APPDATA"]
        .into_iter()
        .filter_map(|name| std::env::var_os(name).map(PathBuf::from))
        .map(|path| {
            path.join("Microsoft")
                .join("Windows")
                .join("Start Menu")
                .join("Programs")
        })
        .filter(|path| path.is_dir())
        .collect()
}
fn walk_files(root: &Path, out: &mut Vec<IndexedFileRecord>) -> Result<(), String> {
    walk(root, 0, out, false)
}
#[cfg(target_os = "windows")]
fn walk_start_menu(root: &Path, out: &mut Vec<IndexedFileRecord>) -> Result<(), String> {
    walk(root, 0, out, true)
}
fn walk(
    directory: &Path,
    depth: usize,
    out: &mut Vec<IndexedFileRecord>,
    apps_only: bool,
) -> Result<(), String> {
    let entries = match fs::read_dir(directory) {
        Ok(entries) => entries,
        Err(_) => return Ok(()),
    };
    for entry in entries.flatten() {
        let path = entry.path();
        let Ok(kind) = entry.file_type() else {
            continue;
        };
        if kind.is_symlink() {
            continue;
        }
        if kind.is_dir() {
            if depth < MAX_DEPTH && !skip_directory(entry.file_name().to_string_lossy().as_ref()) {
                walk(&path, depth + 1, out, apps_only)?;
            }
            continue;
        }
        if !kind.is_file() {
            continue;
        }
        let extension = path
            .extension()
            .and_then(|value| value.to_str())
            .unwrap_or_default()
            .to_ascii_lowercase();
        if apps_only && extension != "lnk" {
            continue;
        }
        let Ok(metadata) = entry.metadata() else {
            continue;
        };
        if metadata.len() > MAX_FILE_SIZE {
            continue;
        }
        let filename = path
            .file_name()
            .and_then(|value| value.to_str())
            .unwrap_or_default()
            .to_owned();
        let name = if apps_only {
            filename
                .strip_suffix(".lnk")
                .or_else(|| filename.strip_suffix(".LNK"))
                .unwrap_or(&filename)
                .to_owned()
        } else {
            filename
        };
        out.push(IndexedFileRecord {
            path: path.to_string_lossy().into_owned(),
            filename: name,
            extension: extension.clone(),
            file_type: if apps_only {
                "application".into()
            } else {
                categorize_extension(&extension).into()
            },
            size_bytes: metadata.len() as i64,
            folder: directory.to_string_lossy().into_owned(),
            depth: depth as i64,
            created_at: system_time_ms(metadata.created()),
            modified_at: system_time_ms(metadata.modified()),
            target_path: None,
        });
    }
    Ok(())
}
fn skip_directory(name: &str) -> bool {
    [
        ".trash",
        "node_modules",
        ".git",
        "__pycache__",
        ".venv",
        "venv",
        ".cache",
        ".npm",
        ".yarn",
        "pods",
        "deriveddata",
        ".build",
        "build",
        "dist",
        ".next",
        ".nuxt",
        "target",
        "vendor",
        "library",
        ".local",
        ".cargo",
        ".rustup",
    ]
    .contains(&name.to_ascii_lowercase().as_str())
}
fn categorize_extension(extension: &str) -> &'static str {
    match extension {
        "pdf" | "doc" | "docx" | "txt" | "md" | "rtf" | "odt" | "xls" | "xlsx" | "csv" | "ppt"
        | "pptx" => "document",
        "ts" | "tsx" | "js" | "jsx" | "py" | "rs" | "go" | "java" | "c" | "h" | "cpp" | "cs"
        | "rb" | "php" | "swift" | "kt" | "sh" | "ps1" | "json" | "yaml" | "yml" | "toml"
        | "html" | "css" | "sql" => "code",
        "png" | "jpg" | "jpeg" | "gif" | "webp" | "svg" | "bmp" | "tiff" | "heic" | "ico" => {
            "image"
        }
        "mp4" | "mov" | "avi" | "mkv" | "webm" | "mp3" | "wav" | "flac" | "m4a" | "aac" => "media",
        "zip" | "rar" | "7z" | "tar" | "gz" => "archive",
        "exe" | "msi" | "lnk" | "appx" => "application",
        _ => "other",
    }
}

#[tauri::command]
pub fn file_index_scan(store: State<'_, KnowledgeStore>) -> Result<FileIndexStatus, String> {
    store.scan()
}
#[tauri::command]
pub fn file_index_status(store: State<'_, KnowledgeStore>) -> Result<FileIndexStatus, String> {
    store.status()
}
#[tauri::command]
pub fn file_index_apps(
    limit: Option<i64>,
    store: State<'_, KnowledgeStore>,
) -> Result<Vec<IndexedAppRecord>, String> {
    store.apps(limit.unwrap_or(200))
}
#[tauri::command]
pub fn file_index_capabilities() -> FileIndexCapabilities {
    FileIndexCapabilities {
        start_menu_shortcuts: Capability {
            supported: cfg!(target_os = "windows"),
            reason: (!cfg!(target_os = "windows"))
                .then_some("Windows Start Menu shortcuts are unavailable on this platform"),
        },
    }
}
#[tauri::command]
pub fn kg_file_index_digest(store: State<'_, KnowledgeStore>) -> Result<FileIndexDigest, String> {
    store.digest()
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn app_index_capability_is_honest_off_windows() {
        let capability = file_index_capabilities().start_menu_shortcuts;
        if cfg!(target_os = "windows") {
            assert!(capability.supported);
        } else {
            assert!(!capability.supported);
            assert!(capability.reason.is_some());
        }
    }
}
