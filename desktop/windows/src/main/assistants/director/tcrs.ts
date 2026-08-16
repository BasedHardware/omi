/**
 * Task contextual resurfacing service (TCRS) — Windows port of macOS
 * TaskContextualResurfacingService: the legacy, context-buckets-OFF path that
 * turns local context events into a privacy-hashed snapshot, asks the backend
 * to re-evaluate What Matters Now, and fans the projection out to the
 * dashboard store.
 *
 * Privacy invariant: raw window titles, app names, and references never leave
 * the constructor — events carry only `sha256:<hex64>` hashes, and the wire
 * snapshot carries only canonical subject ids + signal enums. The reference
 * hash itself is never sent.
 */

import { createHash } from 'node:crypto'
import { randomUUID } from 'node:crypto'
import { normalizeTitleForIdentity } from './titleNormalizer'

export const TCRS_EVENT_LIFETIME_MS = 5 * 60 * 1000
export const TCRS_ACCUMULATOR_CAP = 16
export const TCRS_DEBOUNCE_MS = 2_000
export const TCRS_MATERIAL_DEDUPE_WINDOW_MS = 5 * 60 * 1000
export const TCRS_SNAPSHOT_TTL_MS = 5 * 60 * 1000
export const TCRS_SCHEMA_VERSION = 1

export type TaskContextEventKind =
  | 'person'
  | 'app_window'
  | 'document'
  | 'meeting'
  | 'free_time'
  | 'dependency'
  | 'agent'

/** Event kind -> backend ContextMatchSignal (note the app_window -> app rename). */
export const KIND_TO_SIGNAL: Record<TaskContextEventKind, string> = {
  person: 'person',
  app_window: 'app',
  document: 'document',
  meeting: 'meeting',
  free_time: 'free_time',
  dependency: 'dependency',
  agent: 'agent'
}

export type TaskContextUrgency = 'can_wait' | 'time_sensitive'

export interface TaskContextSubject {
  kind: string
  id: string
  workstreamID: string | null
}

/** Subject equality uses (kind, id) only — workstreamID is excluded. */
export function subjectKey(subject: TaskContextSubject): string {
  return `${subject.kind}${subject.id}`
}

export interface TaskLocalContextEvent {
  kind: TaskContextEventKind
  referenceHash: string
  subject: TaskContextSubject | null
  urgency: TaskContextUrgency
  occurredAt: number
  expiresAt: number
}

export function sha256Hex(value: string): string {
  return createHash('sha256').update(value, 'utf8').digest('hex')
}

/** Normalize a raw reference into an event: trim, lowercase, hash. */
export function normalizedEvent(args: {
  kind: TaskContextEventKind
  rawReference: string
  subject?: TaskContextSubject | null
  urgency?: TaskContextUrgency
  occurredAt: number
  lifetimeMs?: number
}): TaskLocalContextEvent | null {
  const lifetime = args.lifetimeMs ?? TCRS_EVENT_LIFETIME_MS
  if (lifetime <= 0) return null
  const normalized = args.rawReference.trim().toLowerCase()
  if (normalized.length === 0) return null
  return {
    kind: args.kind,
    referenceHash: 'sha256:' + sha256Hex(normalized),
    subject: args.subject ?? null,
    urgency: args.urgency ?? 'can_wait',
    occurredAt: args.occurredAt,
    expiresAt: args.occurredAt + lifetime
  }
}

/** app_window events hash `appName\n<normalizedTitle ?? "untitled">`. */
export function appWindowEvent(args: {
  appName: string
  windowTitle: string | null
  subject?: TaskContextSubject | null
  occurredAt: number
}): TaskLocalContextEvent | null {
  const normalizedTitle = normalizeTitleForIdentity(args.windowTitle, args.appName) ?? 'untitled'
  return normalizedEvent({
    kind: 'app_window',
    rawReference: `${args.appName}\n${normalizedTitle}`,
    subject: args.subject,
    occurredAt: args.occurredAt
  })
}

function coalescingKey(event: TaskLocalContextEvent): string {
  return event.subject?.workstreamID ?? event.subject?.id ?? 'local-context'
}

/** Per-coalescing-key accumulator: replace-in-place on (kind, hash, subject)
 *  match (refreshing expiry), else append; capped to the newest 16 per key. */
export class TaskContextEventAccumulator {
  private buckets = new Map<string, TaskLocalContextEvent[]>()

  insert(event: TaskLocalContextEvent, now: number): void {
    if (event.expiresAt <= now) return
    const key = coalescingKey(event)
    const bucket = (this.buckets.get(key) ?? []).filter((e) => e.expiresAt > now)
    const matchIndex = bucket.findIndex(
      (e) =>
        e.kind === event.kind &&
        e.referenceHash === event.referenceHash &&
        (e.subject === null) === (event.subject === null) &&
        (e.subject === null ||
          subjectKey(e.subject) === subjectKey(event.subject as TaskContextSubject))
    )
    if (matchIndex >= 0) bucket[matchIndex] = event
    else bucket.push(event)
    this.buckets.set(key, bucket.slice(-TCRS_ACCUMULATOR_CAP))
  }

  drain(now: number): TaskLocalContextEvent[] {
    const out: TaskLocalContextEvent[] = []
    for (const bucket of this.buckets.values()) {
      for (const event of bucket) if (event.expiresAt > now) out.push(event)
    }
    this.buckets.clear()
    return out
  }

  pendingKeyCount(): number {
    return this.buckets.size
  }

  clear(): void {
    this.buckets.clear()
  }
}

export interface NormalizedContextMatch {
  subject_kind: string
  subject_id: string
  signals: string[]
}

/** Group subject-bearing events into wire matches: signals deduped and sorted
 *  ascending; matches sorted by (subject_kind, subject_id); cap 32. */
export function contextMatches(events: readonly TaskLocalContextEvent[]): NormalizedContextMatch[] {
  const bySubject = new Map<string, { subject: TaskContextSubject; signals: Set<string> }>()
  for (const event of events) {
    if (event.subject === null) continue
    const signal = KIND_TO_SIGNAL[event.kind]
    const key = subjectKey(event.subject)
    const entry = bySubject.get(key) ?? { subject: event.subject, signals: new Set<string>() }
    entry.signals.add(signal)
    bySubject.set(key, entry)
  }
  return [...bySubject.values()]
    .map((entry) => ({
      subject_kind: entry.subject.kind,
      subject_id: entry.subject.id,
      signals: [...entry.signals].sort().slice(0, 4)
    }))
    .sort((a, b) =>
      a.subject_kind !== b.subject_kind
        ? a.subject_kind.localeCompare(b.subject_kind)
        : a.subject_id.localeCompare(b.subject_id)
    )
    .slice(0, 32)
}

/** `ctx:` + first 32 hex of sha256 over the semantic fingerprint plus the
 *  urgency suffix; time_sensitive anywhere flips the suffix so an unchanged
 *  snapshot still re-evaluates. */
export function materialHint(
  matches: readonly NormalizedContextMatch[],
  anyTimeSensitive: boolean
): string {
  const semantic = matches
    .map((m) => [m.subject_kind, m.subject_id, [...m.signals].sort().join(',')].join('|'))
    .join('||')
  const material = `${semantic}||urgency:${anyTimeSensitive ? 'time_sensitive' : 'can_wait'}`
  return 'ctx:' + sha256Hex(material).slice(0, 32)
}

export interface TcrsClient {
  getControl(): Promise<{ workflowMode: string; accountGeneration: number | null }>
  putContextSnapshot(
    snapshot: {
      schema_version: number
      device_id: string
      snapshot_id: string
      matches: NormalizedContextMatch[]
      generated_at: string
      expires_at: string
    },
    headers: { idempotencyKey: string; accountGeneration: number }
  ): Promise<void>
  evaluate(body: { device_id: string; material_hint: string }): Promise<unknown>
}

export interface TcrsDeps {
  bucketsEnabled(): boolean
  ownerId(): string | null
  sessionEpoch(): number
  deviceId(): string | null
  client: TcrsClient
  /** Receives the raw wire projection for the renderer seam. */
  publishProjection(raw: unknown, urgentSubjects: TaskContextSubject[]): void
  now(): number
  setDebounce(fn: () => void, ms: number): unknown
  clearDebounce(handle: unknown): void
  log?(message: string): void
}

export class TaskContextualResurfacingService {
  private readonly deps: TcrsDeps
  private readonly accumulator = new TaskContextEventAccumulator()
  private debounceHandle: unknown = null
  private lease: { ownerId: string; epoch: number } | null = null
  private lastMaterialHint: string | null = null
  private lastEvaluationAt = 0

  constructor(deps: TcrsDeps) {
    this.deps = deps
  }

  /** Observe a context event: reset when the buckets engine owns the world,
   *  adopt/refresh the owner lease, accumulate, restart the 2s debounce. */
  observe(event: TaskLocalContextEvent): void {
    if (this.deps.bucketsEnabled()) {
      this.resetOwnerState()
      return
    }
    const ownerId = this.deps.ownerId()
    if (ownerId === null) {
      this.resetOwnerState()
      return
    }
    const epoch = this.deps.sessionEpoch()
    if (this.lease === null || this.lease.ownerId !== ownerId || this.lease.epoch !== epoch) {
      this.resetOwnerState()
      this.lease = { ownerId, epoch }
    }
    this.accumulator.insert(event, this.deps.now())
    if (this.debounceHandle !== null) this.deps.clearDebounce(this.debounceHandle)
    this.debounceHandle = this.deps.setDebounce(() => {
      this.debounceHandle = null
      void this.flush()
    }, TCRS_DEBOUNCE_MS)
  }

  resetOwnerState(): void {
    if (this.debounceHandle !== null) {
      this.deps.clearDebounce(this.debounceHandle)
      this.debounceHandle = null
    }
    this.accumulator.clear()
    this.lease = null
    this.lastMaterialHint = null
    this.lastEvaluationAt = 0
  }

  private leaseCurrent(lease: { ownerId: string; epoch: number }): boolean {
    return (
      this.lease !== null &&
      this.lease.ownerId === lease.ownerId &&
      this.lease.epoch === lease.epoch &&
      this.deps.ownerId() === lease.ownerId &&
      this.deps.sessionEpoch() === lease.epoch
    )
  }

  /** The flush pipeline, owner-fenced after every await. Errors log once and
   *  end the cycle; the dedupe memory advances only on full success so the
   *  next event retries naturally. */
  async flush(): Promise<void> {
    const lease = this.lease
    if (lease === null) return
    try {
      if (this.deps.bucketsEnabled()) {
        this.resetOwnerState()
        return
      }
      const now = this.deps.now()
      const events = this.accumulator.drain(now)
      if (events.length === 0) return

      const matches = contextMatches(events)
      const anyTimeSensitive = events.some((e) => e.urgency === 'time_sensitive')
      const hint = materialHint(matches, anyTimeSensitive)
      if (
        this.lastMaterialHint === hint &&
        now - this.lastEvaluationAt < TCRS_MATERIAL_DEDUPE_WINDOW_MS
      ) {
        return
      }

      const deviceId = this.deps.deviceId()
      if (deviceId === null) return

      const control = await this.deps.client.getControl()
      if (!this.leaseCurrent(lease)) return
      if (control.workflowMode !== 'read' || control.accountGeneration === null) return

      const snapshotId = 'ctx-' + randomUUID().toLowerCase()
      const generatedAt = this.deps.now()
      await this.deps.client.putContextSnapshot(
        {
          schema_version: TCRS_SCHEMA_VERSION,
          device_id: deviceId,
          snapshot_id: snapshotId,
          matches,
          generated_at: new Date(generatedAt).toISOString(),
          expires_at: new Date(generatedAt + TCRS_SNAPSHOT_TTL_MS).toISOString()
        },
        { idempotencyKey: snapshotId, accountGeneration: control.accountGeneration }
      )
      if (!this.leaseCurrent(lease)) return

      const projection = await this.deps.client.evaluate({
        device_id: deviceId,
        material_hint: hint
      })
      if (!this.leaseCurrent(lease)) return

      this.lastMaterialHint = hint
      this.lastEvaluationAt = this.deps.now()

      const urgentSubjects = events
        .filter((e) => e.urgency === 'time_sensitive' && e.subject !== null)
        .map((e) => e.subject as TaskContextSubject)
      this.deps.publishProjection(projection, urgentSubjects)
    } catch (err) {
      if (this.leaseCurrent(lease)) {
        this.deps.log?.(`TaskContextualResurfacing: context re-evaluation failed: ${String(err)}`)
      }
    }
  }

  pendingKeyCount(): number {
    return this.accumulator.pendingKeyCount()
  }
}

// --- interruption gate (pure) ----------------------------------------------

export interface InterruptionCandidate {
  recommendationID: string
  interventionID: string
  dedupeKey: string
  headline: string
  whyNow: string
  recommendedAction: string
  expiresAt: number
  canWait: boolean
}

export interface InterruptionConfiguration {
  userOptedIn: boolean
  shippedCohortsEnabled: boolean
  dailyLimit: number
  minimumSpacingMs: number
}

/** All-off safe default (mac ProactiveTaskInterruptionConfiguration.safeDefault). */
export const INTERRUPTION_SAFE_DEFAULT: InterruptionConfiguration = {
  userOptedIn: false,
  shippedCohortsEnabled: false,
  dailyLimit: 2,
  minimumSpacingMs: 90 * 60 * 1000
}

export interface InterruptionLedger {
  sentAt: number[]
  dedupeExpirations: Record<string, number>
}

export interface InterruptionEnvironment {
  cohort: 'dogfood' | 'beta' | 'production'
  masterNotificationsEnabled: boolean
  frequencyEnabled: boolean
  ambientFrequencyEligible: boolean
  taskNotificationsEnabled: boolean
  focusSuppressed: boolean
  now: number
  /** Same-calendar-day check for the daily budget. */
  sameDay(a: number, b: number): boolean
}

export type InterruptionGateReason =
  | 'not_enrolled'
  | 'master_disabled'
  | 'frequency_disabled'
  | 'task_disabled'
  | 'focus_suppressed'
  | 'expired'
  | 'can_wait'
  | 'duplicate'
  | 'frequency_budget'
  | 'daily_budget'
  | 'minimum_spacing'
  | 'allowed'

function isEnrolled(
  config: InterruptionConfiguration,
  cohort: InterruptionEnvironment['cohort']
): boolean {
  if (!config.userOptedIn) return false
  if (cohort === 'dogfood') return true
  return config.shippedCohortsEnabled
}

/** First matching reason wins, in the exact mac order; on `allowed` the
 *  returned ledger records the send and the dedupe expiry. */
export function evaluateInterruptionGate(
  candidate: InterruptionCandidate,
  config: InterruptionConfiguration,
  env: InterruptionEnvironment,
  ledger: InterruptionLedger
): { reason: InterruptionGateReason; ledger: InterruptionLedger } {
  const retention = Math.max(48 * 60 * 60 * 1000, config.minimumSpacingMs)
  const sentAt = ledger.sentAt.filter((at) => env.now - at < retention)
  const dedupeExpirations: Record<string, number> = {}
  for (const [key, expiry] of Object.entries(ledger.dedupeExpirations)) {
    if (expiry > env.now) dedupeExpirations[key] = expiry
  }
  const pruned: InterruptionLedger = { sentAt, dedupeExpirations }

  const decide = (
    reason: InterruptionGateReason
  ): { reason: InterruptionGateReason; ledger: InterruptionLedger } => ({
    reason,
    ledger: pruned
  })

  if (!isEnrolled(config, env.cohort)) return decide('not_enrolled')
  if (!env.masterNotificationsEnabled) return decide('master_disabled')
  if (!env.frequencyEnabled) return decide('frequency_disabled')
  if (!env.taskNotificationsEnabled) return decide('task_disabled')
  if (env.focusSuppressed) return decide('focus_suppressed')
  if (candidate.expiresAt <= env.now) return decide('expired')
  if (candidate.canWait) return decide('can_wait')
  if (pruned.dedupeExpirations[candidate.dedupeKey] !== undefined) return decide('duplicate')
  if (!env.ambientFrequencyEligible) return decide('frequency_budget')
  const sentToday = sentAt.filter((at) => env.sameDay(at, env.now)).length
  if (sentToday >= config.dailyLimit) return decide('daily_budget')
  const lastSent = sentAt.length > 0 ? Math.max(...sentAt) : null
  if (lastSent !== null && env.now - lastSent < config.minimumSpacingMs)
    return decide('minimum_spacing')

  return {
    reason: 'allowed',
    ledger: {
      sentAt: [...sentAt, env.now],
      dedupeExpirations: { ...dedupeExpirations, [candidate.dedupeKey]: candidate.expiresAt }
    }
  }
}
