import { sendWindowsNativeNotification } from '../notifications/native'
import type { InsightPayload } from '../../shared/types'

/** Show an insight as a native Windows notification (also kept in the Action
 *  Center). Used when the user picks the "Windows notification" style.
 *  Best-effort; no-op if unsupported. */
export function fireNativeInsight(p: InsightPayload): void {
  const result = sendWindowsNativeNotification('insights', {
    title: p.headline || 'Omi insight',
    body: p.advice
  })
  if (!result.ok && result.code !== 'disabled') {
    console.warn('[insight] native notification skipped:', result.reason)
  }
}
