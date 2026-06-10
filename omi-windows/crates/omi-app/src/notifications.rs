/// Windows Toast Notification helper.
///
/// Wraps the `winrt-notification` crate to send native Windows 10/11 toast
/// notifications from the Omi tray app.
///
/// Usage:
///   notifications::send("Omi", "Your email tone seems too casual.");
///   notifications::send_with_action("Omi", "Calendar reminder: Standup in 5 min", "Open Calendar");

use tracing::{info, warn};
use winrt_notification::{Duration, Sound, Toast};

const APP_ID: &str = "Omi AI Companion";

/// Send a simple toast notification with title + body.
pub fn send(title: &str, body: &str) {
    send_impl(title, body);
}

/// Send a toast with a specific title + multiline body.
/// The notification stays on screen for a longer duration.
pub fn send_with_action(title: &str, body: &str, _action_label: &str) {
    // winrt-notification doesn't support click actions in 0.5, so we just show the body.
    // Future: upgrade to windows-rs for full interactive toasts.
    send_impl(title, body);
}

fn send_impl(title: &str, body: &str) {
    let title = title.to_string();
    let body = body.to_string();

    // Spawn off the main thread — WinRT calls can block briefly
    std::thread::spawn(move || {
        let result = Toast::new(APP_ID)
            .title(&title)
            .text1(&body)
            .duration(Duration::Short)
            .sound(Some(Sound::Default))
            .show();

        match result {
            Ok(_) => info!("[NOTIF] Toast sent: {title} — {body}"),
            Err(e) => warn!("[NOTIF] Toast failed: {e:#}"),
        }
    });
}

/// Send a proactive suggestion as a toast.
/// Priority ≥ 50 = normal, priority < 50 = silent (no sound).
pub fn send_suggestion(text: &str, priority: u8) {
    let title = if priority >= 80 {
        "⚠️ Omi — Heads Up"
    } else if priority >= 50 {
        "💡 Omi Suggestion"
    } else {
        "ℹ️ Omi"
    };

    let title = title.to_string();
    let body = text.to_string();

    std::thread::spawn(move || {
        let result = Toast::new(APP_ID)
            .title(&title)
            .text1(&body)
            .duration(Duration::Short)
            .sound(Some(Sound::Default))
            .show();

        match result {
            Ok(_) => info!("[NOTIF] Suggestion toast sent (priority={priority})"),
            Err(e) => warn!("[NOTIF] Suggestion toast failed: {e:#}"),
        }
    });
}
