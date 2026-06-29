use std::collections::HashMap;
use std::sync::Arc;
use std::time::Duration;

use tokio::sync::RwLock;
use tokio::time::interval;
use tracing::info;

use crate::config::AppConfig;

#[derive(Debug, Clone)]
pub struct AppUsageEntry {
    pub app_name: String,
    pub total_seconds: u64,
}

#[derive(Debug, Clone)]
pub struct AppTracker {
    inner: Arc<RwLock<HashMap<String, u64>>>,
}

impl AppTracker {
    pub fn new() -> Self {
        Self {
            inner: Arc::new(RwLock::new(HashMap::new())),
        }
    }

    pub async fn get_usage(&self) -> Vec<AppUsageEntry> {
        let map = self.inner.read().await;
        let mut entries: Vec<AppUsageEntry> = map
            .iter()
            .map(|(name, secs)| AppUsageEntry {
                app_name: name.clone(),
                total_seconds: *secs,
            })
            .collect();
        entries.sort_by(|a, b| b.total_seconds.cmp(&a.total_seconds));
        entries
    }

    pub async fn get_app_count(&self) -> usize {
        self.inner.read().await.len()
    }

    async fn record(&self, app_name: &str, seconds: u64) {
        let mut map = self.inner.write().await;
        *map.entry(app_name.to_string()).or_insert(0) += seconds;
    }
}

pub async fn run_app_tracker(
    tracker: AppTracker,
    cfg_provider: impl Fn() -> AppConfig + Send + 'static,
) {
    info!("[TRACK] App usage tracker started");

    let poll_secs = 10u64;
    let mut tick = interval(Duration::from_secs(poll_secs));

    tokio::time::sleep(Duration::from_secs(3)).await;

    loop {
        tick.tick().await;

        let cfg = cfg_provider();
        if !cfg.app_usage_tracking_enabled {
            continue;
        }

        if let Some(title) = get_foreground_window_title() {
            let app_name = extract_app_name(&title);
            if !app_name.is_empty() {
                tracker.record(&app_name, poll_secs).await;
            }
        }
    }
}

pub async fn run_app_tracker_with_db(
    db: omi_db::Database,
    cfg_provider: impl Fn() -> AppConfig + Send + 'static,
) {
    info!("[TRACK] App usage tracker (DB) started");

    let poll_secs = 10i64;
    let mut tick = interval(Duration::from_secs(poll_secs as u64));

    tokio::time::sleep(Duration::from_secs(3)).await;

    loop {
        tick.tick().await;

        let cfg = cfg_provider();
        if !cfg.app_usage_tracking_enabled {
            continue;
        }

        if let Some(title) = get_foreground_window_title() {
            let app_name = extract_app_name(&title);
            if !app_name.is_empty() {
                if let Err(e) = db.record_app_usage(&app_name, poll_secs) {
                    tracing::warn!("[TRACK] DB record error: {e:#}");
                }
            }
        }
    }
}

fn get_foreground_window_title() -> Option<String> {
    #[cfg(target_os = "windows")]
    {
        use std::ffi::OsString;
        use std::os::windows::ffi::OsStringExt;

        extern "system" {
            fn GetForegroundWindow() -> isize;
            fn GetWindowTextW(hwnd: isize, text: *mut u16, max: i32) -> i32;
        }

        unsafe {
            let hwnd = GetForegroundWindow();
            if hwnd == 0 {
                return None;
            }
            let mut buf = [0u16; 512];
            let len = GetWindowTextW(hwnd, buf.as_mut_ptr(), buf.len() as i32);
            if len <= 0 {
                return None;
            }
            let title = OsString::from_wide(&buf[..len as usize])
                .to_string_lossy()
                .to_string();
            if title.is_empty() {
                None
            } else {
                Some(title)
            }
        }
    }
    #[cfg(not(target_os = "windows"))]
    {
        None
    }
}

fn extract_app_name(window_title: &str) -> String {
    let title = window_title.trim();

    // Common patterns: "Title - AppName", "Title — AppName"
    if let Some(pos) = title.rfind(" - ") {
        let suffix = title[pos + 3..].trim();
        if !suffix.is_empty() {
            return normalize_app(suffix);
        }
    }
    if let Some(pos) = title.rfind(" — ") {
        let after = pos + " — ".len();
        let suffix = title[after..].trim();
        if !suffix.is_empty() {
            return normalize_app(suffix);
        }
    }

    // "AppName: details" pattern
    if let Some(pos) = title.find(": ") {
        let prefix = title[..pos].trim();
        if !prefix.is_empty() && prefix.len() < 30 {
            return normalize_app(prefix);
        }
    }

    // Fallback: use whole title but cap length
    let capped = if title.len() > 40 { &title[..40] } else { title };
    normalize_app(capped)
}

fn normalize_app(raw: &str) -> String {
    let s = raw.trim();
    // Known app name normalizations
    let lower = s.to_lowercase();
    if lower.contains("visual studio code") || lower.contains("vs code") {
        return "VS Code".to_string();
    }
    if lower.contains("google chrome") || lower == "chrome" {
        return "Chrome".to_string();
    }
    if lower.contains("firefox") {
        return "Firefox".to_string();
    }
    if lower.contains("microsoft edge") {
        return "Edge".to_string();
    }
    if lower.contains("explorer") && lower.contains("file") {
        return "File Explorer".to_string();
    }
    if lower.contains("discord") {
        return "Discord".to_string();
    }
    if lower.contains("slack") {
        return "Slack".to_string();
    }
    if lower.contains("spotify") {
        return "Spotify".to_string();
    }
    if lower.contains("notepad") {
        return "Notepad".to_string();
    }
    if lower.contains("terminal") || lower.contains("powershell") || lower.contains("cmd") {
        return "Terminal".to_string();
    }
    s.to_string()
}
