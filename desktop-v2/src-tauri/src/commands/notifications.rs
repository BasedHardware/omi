//! OS-native notification delivery.
//!
//! Platform strategy:
//!   - **macOS**: try `notify-rust` bound to Nooto's bundle identifier first —
//!     if a `Nooto.app` is installed on the system (e.g. from a previous
//!     `pnpm tauri build`), this delivers with Nooto's icon even in dev mode.
//!     If no bundle is registered, fall back to `osascript` which always works
//!     but gets attributed to Script Editor's icon.
//!   - **Linux / Windows**: `notify-rust`, which routes to
//!     `org.freedesktop.Notifications` or WinRT toast respectively.

use std::sync::Mutex;
use tauri::command;

#[cfg(target_os = "macos")]
const NOOTO_BUNDLE_ID: &str = "com.togodynamics.nooto";

/// Last-delivered notification, captured so the frontend can pick it up when
/// the user clicks the banner. The stub `/Applications/Nooto.app` triggers a
/// `nooto://notification-click` deep link on click; the deep-link handler in
/// `main.rs` emits a `notification:click` event to the renderer, which reads
/// this value via `take_last_notification` and routes to chat.
static LAST_NOTIFICATION: Mutex<Option<(String, String)>> = Mutex::new(None);

fn remember_last_notification(title: &str, body: &str) {
    if let Ok(mut guard) = LAST_NOTIFICATION.lock() {
        *guard = Some((title.to_string(), body.to_string()));
    }
}

/// Retrieve and clear the most recent notification's title + body. Returns
/// `None` if no notification is pending or if it's already been consumed.
#[command]
pub fn take_last_notification() -> Option<(String, String)> {
    LAST_NOTIFICATION.lock().ok().and_then(|mut g| g.take())
}

/// Result of the one-shot `notify_rust::set_application` attempt. `mac-notification-sys`
/// wraps `setApplication` in `Once::call_once`, so after the first call every subsequent
/// call returns `Err(AlreadySet)` regardless of actual state. We run it once, cache the
/// verdict, and route every notification the same way — no more flicker between the
/// Nooto icon and Script Editor's.
#[cfg(target_os = "macos")]
static NOOTO_APP_READY: std::sync::OnceLock<bool> = std::sync::OnceLock::new();

#[cfg(target_os = "macos")]
fn ensure_nooto_application() -> bool {
    *NOOTO_APP_READY.get_or_init(|| {
        let ok = notify_rust::set_application(NOOTO_BUNDLE_ID).is_ok();
        eprintln!(
            "[notifications] set_application({}) -> {}",
            NOOTO_BUNDLE_ID,
            if ok { "ok (Nooto.app found)" } else { "err (bundle not installed)" }
        );
        ok
    })
}

#[command]
pub async fn show_notification_alert(
    title: String,
    body: String,
    #[allow(unused_variables)] auto_hide_ms: Option<u64>,
) -> Result<(), String> {
    eprintln!(
        "[notifications] show_notification_alert: title={:?} body_len={}",
        title,
        body.len()
    );
    remember_last_notification(&title, &body);

    #[cfg(target_os = "macos")]
    {
        // Preferred path: route through an installed Nooto.app so the Nooto
        // icon appears. Uses a cached OnceLock result because the underlying
        // `set_application` can only succeed once per process.
        if ensure_nooto_application() {
            let result = notify_rust::Notification::new()
                .summary(&title)
                .body(&body)
                .show();
            if result.is_ok() {
                eprintln!("[notifications] delivered via Nooto.app bundle");
                return Ok(());
            }
            eprintln!(
                "[notifications] notify-rust path failed, falling back to osascript: {:?}",
                result.err()
            );
        }

        // Fallback: shell out to osascript. Notifications appear under Script
        // Editor's icon but always deliver.
        let esc = |s: &str| s.replace('\\', "\\\\").replace('"', "\\\"");
        let script = format!(
            r#"display notification "{}" with title "{}""#,
            esc(&body),
            esc(&title)
        );
        let output = std::process::Command::new("osascript")
            .arg("-e")
            .arg(&script)
            .output()
            .map_err(|e| format!("osascript spawn failed: {}", e))?;

        if !output.status.success() {
            let stderr = String::from_utf8_lossy(&output.stderr);
            eprintln!("[notifications] osascript failed: {}", stderr);
            return Err(format!("osascript failed: {}", stderr));
        }
        eprintln!("[notifications] delivered via osascript");
        return Ok(());
    }

    #[cfg(not(target_os = "macos"))]
    {
        match notify_rust::Notification::new()
            .summary(&title)
            .body(&body)
            .auto_icon()
            .show()
        {
            Ok(_) => {
                eprintln!("[notifications] notify-rust delivered");
                Ok(())
            }
            Err(e) => {
                eprintln!("[notifications] notify-rust failed: {}", e);
                Err(e.to_string())
            }
        }
    }
}
