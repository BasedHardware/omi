// Best-effort Windows notifications. A notification is always a nicety, never
// load-bearing: an unsupported platform or a throwing constructor must never
// break the flow that fired it. (insight/notification.ts is a separate,
// richer notification path and deliberately not routed through here.)
import { Notification } from 'electron'

export interface BestEffortNotificationOptions {
  silent?: boolean
  onClick?: () => void
}

export function showBestEffortNotification(
  title: string,
  body: string,
  options?: BestEffortNotificationOptions
): void {
  try {
    if (!Notification.isSupported()) return
    const n = new Notification({ title, body, silent: options?.silent === true })
    if (typeof options?.onClick === 'function') {
      n.on('click', () => {
        try {
          options.onClick?.()
        } catch (err) {
          console.warn('[notify] notification click handler failed:', err)
        }
      })
    }
    n.show()
  } catch (e) {
    console.warn('[notify] notification failed:', e)
  }
}
