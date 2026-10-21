// src/main/insight/notification.ts
import { Notification } from 'electron'
import type { InsightPayload } from '../../shared/types'
import type { ToastDeliveryHooks } from './deliveryHooks'
import { showInsightToast } from './toastWindow'

/** Show an insight as a native Windows notification (also kept in the Action
 *  Center). Used when the user picks the "Windows notification" style.
 *  Best-effort; no-op if unsupported. */
export function fireNativeInsight(p: InsightPayload, hooks?: ToastDeliveryHooks): void {
  if (hooks && !hooks.isCurrent()) return
  try {
    if (!Notification.isSupported()) return
    const n = new Notification({ title: p.headline || 'Omi insight', body: p.advice })
    n.on('click', () => {
      if (hooks) {
        if (hooks.isCurrent()) hooks.onOpened()
      } else showInsightToast(p)
    })
    n.on('show', () => {
      if (hooks?.isCurrent()) hooks.onPresented()
    })
    n.on('failed', (_e, e) => console.warn('[insight] native notification failed:', e))
    n.show()
  } catch {
    /* best-effort */
  }
}
