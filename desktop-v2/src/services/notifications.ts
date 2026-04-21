import { invoke } from "@tauri-apps/api/core";
import { isPermissionGranted, requestPermission, sendNotification } from "@tauri-apps/plugin-notification";

export async function ensureNotificationPermission(): Promise<boolean> {
  let granted = await isPermissionGranted();
  if (!granted) {
    const permission = await requestPermission();
    granted = permission === "granted";
  }
  return granted;
}

/** Fires the in-app dedicated notification window. Separate from the chat
 *  floating bar — never uses that surface. */
async function showInAppNotification(title: string, body: string): Promise<void> {
  try {
    await invoke("show_notification_alert", { title, body });
  } catch (err) {
    console.error("[notifications] show_notification_alert failed", err);
  }
}

/** Generic notifier. Shows the dedicated in-app bar and, if the OS has
 *  granted permission, also posts an OS-level notification as a backup
 *  (some desktop environments suppress when the app is focused anyway). */
export async function notify(title: string, body: string): Promise<void> {
  await showInAppNotification(title, body);
  const granted = await ensureNotificationPermission();
  if (granted) {
    sendNotification({ title, body });
  }
}

export async function sendFocusNotification(title: string, body: string): Promise<void> {
  await showInAppNotification(title, body);
  const granted = await ensureNotificationPermission();
  if (!granted) return;
  sendNotification({ title, body });
}

export async function sendDistractionAlert(appOrSite: string, message: string): Promise<void> {
  await sendFocusNotification("Focus", message || `You seem distracted on ${appOrSite}`);
}
