// src/main/insight/notification.ts
import { Notification } from 'electron'
import type { InsightPayload } from '../../shared/types'
import { showInsightToast } from './toastWindow'

/** Show an insight as a native Windows notification (also kept in the Action
 *  Center). Used when the user picks the "Windows notification" style.
 *  Best-effort; no-op if unsupported. */
export function fireNativeInsight(p: InsightPayload): void {
  try {
    if (!Notification.isSupported()) return
    const n = new Notification({ title: p.headline || 'Omi insight', body: p.advice })
    // Windows notifications have no portable action-button API in Electron.
    // Clicking a native card reopens the actionable in-app surface so JIT
    // feedback and exact Rewind controls remain reachable instead of becoming
    // a one-way, dismiss-only notification.
    n.on('click', () => showInsightToast(p))
    n.on('failed', (_e, e) => console.warn('[insight] native notification failed:', e))
    n.show()
  } catch {
    /* best-effort */
  }
}
