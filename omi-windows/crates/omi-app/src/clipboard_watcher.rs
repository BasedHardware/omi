use std::time::Duration;

use clipboard_win::{formats, get_clipboard};
use tokio::time::interval;
use tracing::{info, warn};

use crate::config::AppConfig;

pub async fn run_clipboard_watcher(
    db: omi_db::Database,
    cfg_provider: impl Fn() -> AppConfig + Send + 'static,
) {
    info!("[CLIP] Clipboard watcher started");

    let mut last_content = String::new();
    let mut tick = interval(Duration::from_secs(2));

    // Let the app settle before first check
    tokio::time::sleep(Duration::from_secs(5)).await;

    loop {
        tick.tick().await;

        let cfg = cfg_provider();
        if !cfg.clipboard_monitoring_enabled {
            continue;
        }

        let text = match get_clipboard_text() {
            Some(t) if !t.is_empty() => t,
            _ => continue,
        };

        // Deduplicate consecutive identical copies
        if text == last_content {
            continue;
        }
        last_content = text.clone();

        let content_type = classify_content(&text);
        let source_app = get_foreground_window_title();

        match db.insert_clipboard_entry(&text, &content_type, source_app.as_deref()) {
            Ok(_) => {
                let preview = if text.len() > 60 {
                    format!("{}…", &text[..60])
                } else {
                    text.clone()
                };
                info!(
                    "[CLIP] Captured {} from {:?}: {preview}",
                    content_type,
                    source_app.as_deref().unwrap_or("unknown")
                );
            }
            Err(e) => warn!("[CLIP] DB insert error: {e:#}"),
        }
    }
}

fn get_clipboard_text() -> Option<String> {
    let text: String = get_clipboard(formats::Unicode).ok()?;
    let trimmed = text.trim().to_string();
    if trimmed.is_empty() {
        None
    } else {
        Some(trimmed)
    }
}

fn classify_content(text: &str) -> String {
    if text.starts_with("http://") || text.starts_with("https://") {
        "url".to_string()
    } else if text.contains('\\') && (text.contains(':') || text.starts_with("\\\\")) {
        "file_path".to_string()
    } else if text.contains('@') && text.contains('.') && !text.contains(' ') {
        "email".to_string()
    } else {
        "text".to_string()
    }
}

fn get_foreground_window_title() -> Option<String> {
    #[cfg(target_os = "windows")]
    {
        use std::ffi::OsString;
        use std::os::windows::ffi::OsStringExt;

        unsafe {
            let hwnd = GetForegroundWindow();
            if hwnd.is_null() {
                return None;
            }
            let len = GetWindowTextLengthW(hwnd);
            if len == 0 {
                return None;
            }
            let mut buf = vec![0u16; (len + 1) as usize];
            let written = GetWindowTextW(hwnd, buf.as_mut_ptr(), buf.len() as i32);
            if written == 0 {
                return None;
            }
            buf.truncate(written as usize);
            Some(OsString::from_wide(&buf).to_string_lossy().to_string())
        }
    }
    #[cfg(not(target_os = "windows"))]
    {
        None
    }
}

#[cfg(target_os = "windows")]
extern "system" {
    fn GetForegroundWindow() -> *mut std::ffi::c_void;
    fn GetWindowTextW(hwnd: *mut std::ffi::c_void, lpstring: *mut u16, nmaxcount: i32) -> i32;
    fn GetWindowTextLengthW(hwnd: *mut std::ffi::c_void) -> i32;
}
