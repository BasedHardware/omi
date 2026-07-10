// Best-effort Windows notifications. A notification is always a nicety, never
// load-bearing: an unsupported platform or a throwing constructor must never
// break the flow that fired it. (insight/notification.ts is a separate,
// richer notification path and deliberately not routed through here.)
import { Notification } from 'electron'

export function showBestEffortNotification(title: string, body: string): void {
  try {
    if (!Notification.isSupported()) return
    new Notification({ title, body }).show()
  } catch (e) {
    console.warn('[notify] notification failed:', e)
  }
}
