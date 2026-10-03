import { rmSync } from 'node:fs'
import {
  get_proactivity_feed,
  record_proactivity_outcome,
  OmiApiError
} from '../../renderer/src/lib/omiApi.generated'
import type { ProactivityTarget } from '../../renderer/src/lib/omiApi.generated'
import {
  getBackendSession,
  getSessionEpoch,
  isSessionExpired,
  pullFreshSession,
  tokenUid
} from '../assistants/core/session'
import { presentProactivityNotification } from './notificationAdapter'
import { ProactivityReceiptStore, notificationDeadline } from './receiptStore'

export class ProactivityFeedConsumer {
  private store: ProactivityReceiptStore | null = null
  private owner: string | null = null
  private busy: number | null = null
  private lastAttempt = 0
  private retryTimer: ReturnType<typeof setTimeout> | null = null
  private retryDelay = 30_000
  constructor(
    private path: string,
    private openTarget: (target: ProactivityTarget) => Promise<boolean>
  ) {}

  sessionChanged(): void {
    if (this.retryTimer) clearTimeout(this.retryTimer)
    this.retryTimer = null
    const session = getBackendSession()
    const owner = session ? tokenUid(session.token) : null
    if (owner !== this.owner || !owner) {
      this.store?.purge()
      if (!owner) {
        rmSync(this.path, { force: true })
        rmSync(`${this.path}.tmp`, { force: true })
      }
      this.store = null
      this.owner = owner
      this.lastAttempt = 0
    }
    this.busy = null
    void this.refresh()
  }

  private scheduleOutboxRetry(): void {
    if (this.retryTimer || !this.store?.pending.length) return
    this.retryTimer = setTimeout(() => {
      this.retryTimer = null
      void this.refresh(true)
    }, this.retryDelay)
    this.retryTimer.unref()
  }

  async refresh(outcomesOnly = false): Promise<void> {
    const epoch = getSessionEpoch()
    if (this.busy !== null) {
      if (outcomesOnly) this.scheduleOutboxRetry()
      return
    }
    if (!outcomesOnly && Date.now() - this.lastAttempt < 30_000) return
    const original = getBackendSession()
    const owner = original && tokenUid(original.token)
    if (!owner) return
    this.busy = epoch
    if (!outcomesOnly) this.lastAttempt = Date.now()
    const current = (): boolean =>
      getSessionEpoch() === epoch && tokenUid(getBackendSession()?.token ?? '') === owner
    try {
      if (isSessionExpired()) await pullFreshSession()
      if (!current()) return
      const session = getBackendSession()!
      if (this.owner !== owner || !this.store) {
        this.store?.purge()
        this.store = new ProactivityReceiptStore(this.path, owner)
        this.owner = owner
      }
      const store = this.store
      const init = { baseURL: session.apiBase.replace(/\/$/, ''), token: session.token }
      for (const entry of store.pending) {
        if (!current()) return
        try {
          await record_proactivity_outcome(
            { item_id: entry.itemID },
            { X_App_Platform: 'windows' },
            entry.request,
            init
          )
        } catch (error) {
          if (!(error instanceof OmiApiError && error.status === 404)) throw error
        }
        if (!current()) return
        store.acknowledge(entry.request.event_id)
      }
      this.retryDelay = 30_000
      if (outcomesOnly) return
      const feed = await get_proactivity_feed({ limit: 50 }, { X_App_Platform: 'windows' }, init)
      if (!current() || !feed.enabled) return
      for (const item of feed.items) {
        const expiresAt = notificationDeadline(item.created_at, feed.server_time)
        if (expiresAt <= Date.now() || store.hasShown(item.id)) continue
        const admitted = presentProactivityNotification(item, {
          ownerID: owner,
          epoch,
          channel: 'feed',
          expiresAt,
          isOwnerCurrent: current,
          hasBeenPresented: (id) => store.hasShown(id),
          onOutcome: (id, request) => {
            if (!current()) return
            try {
              store.record(id, request)
              this.scheduleOutboxRetry()
            } catch {
              console.warn('[proactivity] outcome persistence failed')
            }
          },
          openTarget: this.openTarget
        })
        // The shared toast is one slot. Never overwrite it with a burst of feed items.
        if (admitted) break
      }
    } catch (error) {
      if (error instanceof OmiApiError) {
        const seconds = Number(error.response?.headers.get('Retry-After'))
        if (Number.isFinite(seconds) && seconds > 0)
          this.retryDelay = Math.max(30_000, seconds * 1000)
        if (error.status === 401 && current()) await pullFreshSession()
      }
      console.warn('[proactivity] request deferred for retry')
    } finally {
      if (this.busy === epoch) this.busy = null
      if (current()) this.scheduleOutboxRetry()
    }
  }
}
