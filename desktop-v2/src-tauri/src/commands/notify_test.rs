use tauri::command;

/// Fire a desktop notification directly via notify-rust (D-Bus on Linux,
/// NSUserNotification on macOS, WinRT on Windows). Bypasses the
/// tauri-plugin-notification entirely so we can isolate the failure path.
#[command]
pub async fn fire_test_notification() -> Result<String, String> {
    tracing::info!("[notify_test] fire_test_notification called");
    eprintln!("[notify_test] fire_test_notification called");

    let result = notify_rust::Notification::new()
        .summary("Nooto — Test")
        .body("If you see this, native notifications work.")
        .appname("Nooto")
        .timeout(notify_rust::Timeout::Milliseconds(5000))
        .show();

    match result {
        Ok(handle) => {
            let id = handle.id();
            tracing::info!("[notify_test] notification dispatched, id={}", id);
            eprintln!("[notify_test] notification dispatched, id={}", id);
            Ok(format!("dispatched id={}", id))
        }
        Err(e) => {
            tracing::error!("[notify_test] notify-rust failed: {}", e);
            eprintln!("[notify_test] notify-rust failed: {}", e);
            Err(format!("notify-rust failed: {}", e))
        }
    }
}
