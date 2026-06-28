use std::path::{Path, PathBuf};
use std::time::Duration;

use chrono::Utc;
use tokio::time::interval;
use tracing::{info, warn};
use walkdir::WalkDir;

use crate::config::AppConfig;

const SKIP_DIRS: &[&str] = &[
    ".git",
    "node_modules",
    "target",
    "__pycache__",
    ".cache",
    ".venv",
    "venv",
    ".next",
    "dist",
    "build",
    ".cargo",
];

const MAX_FILE_SIZE: u64 = 500 * 1024 * 1024; // 500 MB
const MAX_DEPTH: usize = 4;

pub async fn run_file_indexer(
    db: omi_db::Database,
    cfg_provider: impl Fn() -> AppConfig + Send + 'static,
) {
    info!("[IDX] File indexer started");

    // Wait for the app to settle
    tokio::time::sleep(Duration::from_secs(15)).await;

    let mut tick = interval(Duration::from_secs(600)); // 10 minutes

    loop {
        let cfg = cfg_provider();
        if !cfg.file_indexing_enabled {
            tick.tick().await;
            continue;
        }

        let dirs = resolve_index_dirs(&cfg);
        if dirs.is_empty() {
            info!("[IDX] No directories configured for indexing");
            tick.tick().await;
            continue;
        }

        let scan_start = Utc::now().to_rfc3339();
        let mut indexed = 0u64;

        for dir in &dirs {
            if !dir.exists() {
                info!("[IDX] Skipping non-existent dir: {}", dir.display());
                continue;
            }

            let walker = WalkDir::new(dir)
                .max_depth(MAX_DEPTH)
                .follow_links(false)
                .into_iter()
                .filter_entry(|e| {
                    if e.file_type().is_dir() {
                        let name = e.file_name().to_string_lossy();
                        !SKIP_DIRS.iter().any(|s| name == *s)
                    } else {
                        true
                    }
                });

            for entry in walker.filter_map(|e| e.ok()) {
                if !entry.file_type().is_file() {
                    continue;
                }
                let path = entry.path();
                let metadata = match entry.metadata() {
                    Ok(m) => m,
                    Err(_) => continue,
                };

                if metadata.len() > MAX_FILE_SIZE {
                    continue;
                }

                let file_name = path
                    .file_name()
                    .map(|n| n.to_string_lossy().to_string())
                    .unwrap_or_default();

                if file_name.starts_with('.') {
                    continue;
                }

                let extension = path
                    .extension()
                    .map(|e| e.to_string_lossy().to_string());

                let modified_at = metadata
                    .modified()
                    .ok()
                    .map(|t| {
                        let dt: chrono::DateTime<Utc> = t.into();
                        dt.to_rfc3339()
                    })
                    .unwrap_or_else(|| Utc::now().to_rfc3339());

                let file_path_str = path.to_string_lossy().to_string();
                match db.upsert_indexed_file(
                    &file_path_str,
                    &file_name,
                    extension.as_deref(),
                    metadata.len() as i64,
                    &modified_at,
                ) {
                    Ok(_) => indexed += 1,
                    Err(e) => {
                        warn!("[IDX] Failed to index {}: {e:#}", path.display());
                    }
                }
            }
        }

        // Clean up files that no longer exist (indexed before this scan)
        if let Err(e) = db.delete_stale_files(&scan_start) {
            warn!("[IDX] Failed to clean stale entries: {e:#}");
        }

        let total = db.count_indexed_files().unwrap_or(0);
        info!("[IDX] Scan complete: {indexed} files processed, {total} total in index");

        tick.tick().await;
    }
}

fn resolve_index_dirs(cfg: &AppConfig) -> Vec<PathBuf> {
    if !cfg.file_index_paths.is_empty() {
        return cfg
            .file_index_paths
            .iter()
            .map(PathBuf::from)
            .collect();
    }

    let home = std::env::var("USERPROFILE")
        .or_else(|_| std::env::var("HOME"))
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("C:\\Users\\Default"));

    let mut dirs = Vec::new();
    for name in &["Desktop", "Documents", "Downloads"] {
        let p = home.join(name);
        if p.exists() {
            dirs.push(p);
        }
    }

    // Also check for common project directories
    let projects = home.join("Projects");
    if projects.exists() {
        dirs.push(projects);
    }
    let dev = home.join("dev");
    if dev.exists() {
        dirs.push(dev);
    }

    dirs
}

pub fn format_recent_files(db: &omi_db::Database, limit: usize) -> String {
    match db.list_recent_files(limit) {
        Ok(files) => files
            .iter()
            .map(|f| {
                let size = format_size(f.size_bytes);
                let ext = f.extension.as_deref().unwrap_or("");
                format!(
                    "- {} ({}, {}) — {}",
                    f.file_name, ext, size, f.file_path
                )
            })
            .collect::<Vec<_>>()
            .join("\n"),
        Err(_) => String::new(),
    }
}

fn format_size(bytes: i64) -> String {
    if bytes < 1024 {
        format!("{bytes}B")
    } else if bytes < 1024 * 1024 {
        format!("{:.0}KB", bytes as f64 / 1024.0)
    } else {
        format!("{:.1}MB", bytes as f64 / (1024.0 * 1024.0))
    }
}
