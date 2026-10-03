import { createHash } from 'node:crypto'
import type {
  ProactivityFeedItem,
  ProactivityOutcomeRequest,
  ProactivityTarget
} from '../../renderer/src/lib/omiApi.generated'
import type { InsightPayload } from '../../shared/types'
import { notifyProactive } from '../assistants/core/notify'
import { getSessionEpoch } from '../assistants/core/session'

export type ProactivityNotificationContext = {
  ownerID: string
  epoch: number
  isOwnerCurrent: () => boolean
  /** Durable owner-scoped receipt lookup, supplied by the feed consumer. */
  hasBeenPresented: (itemID: string) => boolean
  onOutcome: (itemID: string, request: ProactivityOutcomeRequest) => void
  openTarget: (target: ProactivityTarget) => void
}

export function proactivityEventID(ownerID: string, itemID: string, action: string): string {
  const hex = createHash('sha256')
    .update(JSON.stringify(['proactivity-v2', ownerID, itemID, action]))
    .digest('hex')
    .slice(0, 32)
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}

/** Typed seam for the feed consumer; no inference, polling or secondary ledger. */
export function presentProactivityNotification(
  item: ProactivityFeedItem,
  context: ProactivityNotificationContext
): boolean {
  const isCurrent = (): boolean => context.isOwnerCurrent() && context.epoch === getSessionEpoch()
  if (
    !context.ownerID ||
    !isCurrent() ||
    item.acted ||
    item.dismissed ||
    !item.id.trim() ||
    !item.title.trim() ||
    !item.body.trim() ||
    !item.target.id.trim() ||
    !['conversation', 'action_item'].includes(item.target.kind) ||
    context.hasBeenPresented(item.id)
  )
    return false
  const emitted = new Set<string>()
  const emit = (action: 'shown' | 'opened' | 'dismissed' | 'timeout'): void => {
    if (!isCurrent() || emitted.has(action)) return
    emitted.add(action)
    context.onOutcome(item.id, {
      action,
      channel: 'push',
      surface: 'windows',
      event_id: proactivityEventID(context.ownerID, item.id, action)
    })
  }
  const payload: InsightPayload = {
    headline: item.title,
    advice: item.body,
    reasoning: '',
    category: 'other',
    sourceApp: 'Omi',
    confidence: 1,
    proactivityItemID: item.id
  }
  return notifyProactive('proactivity_v2', payload, {
    deliveryHooks: {
      isCurrent,
      onPresented: () => emit('shown'),
      onOpened: () => {
        if (isCurrent()) {
          emit('opened')
          context.openTarget(item.target)
        }
      },
      onDismissed: emit
    }
  })
}
