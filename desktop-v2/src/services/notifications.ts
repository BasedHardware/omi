import { invoke } from "@tauri-apps/api/core";

/** Fires an OS-native notification via the Rust command, which uses the
 *  installed Nooto.app bundle when available and falls back to `osascript`
 *  on macOS. No separate in-app window — see
 *  `src-tauri/src/commands/notifications.rs`. */
async function deliver(title: string, body: string): Promise<void> {
  try {
    await invoke("show_notification_alert", { title, body });
  } catch (err) {
    console.error("[notifications] show_notification_alert failed", err);
  }
}

export async function notify(title: string, body: string): Promise<void> {
  await deliver(title, body);
}

export async function sendFocusNotification(title: string, body: string): Promise<void> {
  await deliver(title, body);
}

export async function sendDistractionAlert(appOrSite: string, message: string): Promise<void> {
  await deliver("Focus", message || `You seem distracted on ${appOrSite}`);
}
