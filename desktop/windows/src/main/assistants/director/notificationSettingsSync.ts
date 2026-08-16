/**
 * Notification-settings sync — Windows port of macOS
 * NotificationSettingsSyncCoordinator: mirrors the local notification master
 * toggle and frequency level to the backend
 * (GET/PATCH /v1/users/notification-settings) with a local-authoritative
 * revision journal.
 *
 * Conflict rules carried from mac:
 * - Local settings are authoritative for the delivery gate at all times; the
 *   server is a mirror.
 * - Every local mutation bumps the revision and sets the pending flag; the
 *   PATCH pushes the complete locally-desired pair; completion clears pending
 *   only when the revision still matches.
 * - Hydrate from GET only when nothing is pending and the revision did not
 *   move during the GET.
 * - `enabled` is omitted from the PATCH when the master key was never locally
 *   written, so a first-launch push cannot clobber another client's toggle.
 * - Retry pending pushes on a 1s -> 15min capped doubling backoff.
 */

export const SYNC_BACKOFF_INITIAL_MS = 1_000
export const SYNC_BACKOFF_MAX_MS = 900_000
export const SYNC_BACKOFF_SHIFT_CLAMP = 10

export function backoffDelayMs(attempt: number): number {
  const shift = Math.min(SYNC_BACKOFF_SHIFT_CLAMP, Math.max(0, attempt))
  return Math.min(SYNC_BACKOFF_MAX_MS, SYNC_BACKOFF_INITIAL_MS * 2 ** shift)
}

export interface NotificationSettingsPair {
  /** null = the master key was never locally written (omit from the PATCH). */
  enabled: boolean | null
  frequency: number
}

export interface SyncJournal {
  revision(): number
  pending(): boolean
  /** Bump the revision, set pending, return the new revision. */
  begin(): number
  /** Clear pending only when the stored revision still equals `revision`. */
  complete(revision: number): void
}

export interface NotificationSettingsSyncDeps {
  signedIn(): boolean
  readLocal(): NotificationSettingsPair
  writeLocal(pair: { enabled: boolean; frequency: number }): void
  journal: SyncJournal
  http: {
    get(): Promise<{ enabled: boolean; frequency: number }>
    patch(body: {
      enabled?: boolean
      frequency: number
    }): Promise<{ enabled: boolean; frequency: number }>
  }
  setRetryTimer(fn: () => void, ms: number): unknown
  clearRetryTimer(handle: unknown): void
  log?(message: string): void
}

export class NotificationSettingsSyncCoordinator {
  private readonly deps: NotificationSettingsSyncDeps
  private reconcileTail: Promise<void> = Promise.resolve()
  private pushTail: Promise<void> = Promise.resolve()
  private retryHandle: unknown = null
  private retryAttempt = 0

  constructor(deps: NotificationSettingsSyncDeps) {
    this.deps = deps
  }

  /** Serialize a reconcile (GET + decide) onto the reconcile tail. */
  reconcile(): Promise<void> {
    this.reconcileTail = this.reconcileTail.then(() => this.reconcileOnce()).catch(() => undefined)
    return this.reconcileTail
  }

  /** A local mutation: the caller already wrote the local pair; push it. */
  enqueue(pair: NotificationSettingsPair, revision: number): Promise<void> {
    this.pushTail = this.pushTail.then(() => this.pushOnce(pair, revision)).catch(() => undefined)
    return this.pushTail
  }

  private async reconcileOnce(): Promise<void> {
    if (!this.deps.signedIn()) return
    const revisionAtStart = this.deps.journal.revision()
    const pendingAtStart = this.deps.journal.pending()
    let server: { enabled: boolean; frequency: number }
    try {
      server = await this.deps.http.get()
    } catch {
      if (this.deps.journal.pending()) this.scheduleRetry()
      return
    }
    // Synchronous decide-and-write: no awaits below this line.
    const revisionNow = this.deps.journal.revision()
    const pendingNow = this.deps.journal.pending()
    const preserveLocal = pendingAtStart || pendingNow || revisionNow !== revisionAtStart
    if (preserveLocal) {
      if (pendingNow) {
        const local = this.deps.readLocal()
        void this.enqueue(local, revisionNow)
      }
      return
    }
    this.deps.writeLocal({ enabled: server.enabled, frequency: server.frequency })
  }

  private async pushOnce(pair: NotificationSettingsPair, revision: number): Promise<void> {
    if (!this.deps.signedIn()) {
      this.scheduleRetry()
      return
    }
    try {
      const body: { enabled?: boolean; frequency: number } = { frequency: pair.frequency }
      if (pair.enabled !== null) body.enabled = pair.enabled
      await this.deps.http.patch(body)
      this.deps.journal.complete(revision)
      if (!this.deps.journal.pending()) {
        this.retryAttempt = 0
        if (this.retryHandle !== null) {
          this.deps.clearRetryTimer(this.retryHandle)
          this.retryHandle = null
        }
      } else {
        this.scheduleRetry()
      }
    } catch {
      this.scheduleRetry()
    }
  }

  private scheduleRetry(): void {
    if (this.retryHandle !== null) return
    const delay = backoffDelayMs(this.retryAttempt)
    this.retryAttempt = Math.min(this.retryAttempt + 1, SYNC_BACKOFF_SHIFT_CLAMP)
    this.retryHandle = this.deps.setRetryTimer(() => {
      this.retryHandle = null
      if (!this.deps.journal.pending()) return
      const local = this.deps.readLocal()
      void this.enqueue(local, this.deps.journal.revision())
    }, delay)
  }
}
