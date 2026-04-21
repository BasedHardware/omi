use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};

use serde::{Deserialize, Serialize};

pub const DEFAULT_RETENTION_DAYS: u32 = 7;
pub const MIN_RETENTION_DAYS: u32 = 1;
pub const MAX_RETENTION_DAYS: u32 = 365;
const CONFIG_FILE_NAME: &str = "retention_config.json";

#[derive(Debug, Clone, Serialize, Deserialize)]
struct RetentionFile {
    retention_days: u32,
}

/// In-memory retention state shared between commands and the cleanup task.
/// The `config_path` is held so the Tauri commands can persist updates
/// without re-resolving the app data dir.
pub struct RetentionConfig {
    pub days: Mutex<u32>,
    pub config_path: PathBuf,
}

impl RetentionConfig {
    pub fn load(data_dir: &Path) -> Arc<Self> {
        let config_path = data_dir.join(CONFIG_FILE_NAME);
        let days = read_days(&config_path).unwrap_or(DEFAULT_RETENTION_DAYS);
        Arc::new(Self {
            days: Mutex::new(clamp_days(days)),
            config_path,
        })
    }

    pub fn current_days(&self) -> u32 {
        *self.days.lock().expect("retention mutex poisoned")
    }

    /// Update in-memory state and persist to disk. Disk failures are logged
    /// but do not roll back the in-memory change.
    pub fn update(&self, days: u32) -> Result<(), String> {
        if !(MIN_RETENTION_DAYS..=MAX_RETENTION_DAYS).contains(&days) {
            return Err(format!(
                "retention_days must be between {} and {}",
                MIN_RETENTION_DAYS, MAX_RETENTION_DAYS
            ));
        }
        {
            let mut guard = self.days.lock().expect("retention mutex poisoned");
            *guard = days;
        }
        if let Err(e) = write_days(&self.config_path, days) {
            tracing::warn!("Failed to persist retention config: {}", e);
        }
        Ok(())
    }
}

fn clamp_days(days: u32) -> u32 {
    days.clamp(MIN_RETENTION_DAYS, MAX_RETENTION_DAYS)
}

fn read_days(path: &Path) -> Option<u32> {
    let bytes = std::fs::read(path).ok()?;
    let parsed: RetentionFile = serde_json::from_slice(&bytes).ok()?;
    Some(parsed.retention_days)
}

fn write_days(path: &Path, days: u32) -> std::io::Result<()> {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    let contents = serde_json::to_vec_pretty(&RetentionFile { retention_days: days })
        .map_err(|e| std::io::Error::new(std::io::ErrorKind::Other, e))?;
    std::fs::write(path, contents)
}
