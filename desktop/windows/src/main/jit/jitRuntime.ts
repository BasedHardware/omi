import type { RewindFrame } from '../../shared/types'
import {
  evaluateJitWatchlist,
  JIT_RUNTIME_DEFAULT_AUTHORITY,
  type JitCompiledTrigger,
  type JitEmbeddingContract,
  type JitRolloutDecision,
  type JitRuntimePolicy,
  type JitRuntimeAuthority,
  type JitTriggerObservation,
  type JitCalendarEvent
} from '../../shared/jitTriggerRuntime'
import { createJitAuthorityClient, type JitAuthorityClient } from './jitAuthorityClient'
import {
  beginJitWakeup,
  cancelJitWakeup,
  claimJitWakeup,
  completeJitWakeup,
  readCompiledJitTriggers,
  reconcileJitTriggerSnapshot,
  reconcileJitLedgerMirror,
  persistJitProactivityReservation,
  pinJitConversationKeyframe,
  markJitTemporaryFrame,
  claimJitAmbientContext,
  deriveJitOpaqueId,
  jitInstallationDeviceId,
  type JitMirrorDb,
  type JitLedgerMirrorPage,
  type JitLedgerMirrorReceipt,
  type JitMirrorReceipt,
  type JitWakeupClaim
} from './jitTriggerMirror'

export type JitAdmission =
  | { kind: 'legacy_fallback'; reason: string }
  | { kind: 'suppressed'; reason: string }
  | {
      kind: 'planned'
      triggerId: string
      triggerRevision: number
      continuityKey: string
      prompt: string
      claim: JitWakeupClaim
      receipt: JitMirrorReceipt
    }
  | {
      kind: 'ambient_candidate'
      continuityKey: string
      candidateId: string
      claim: JitWakeupClaim
      receipt: JitMirrorReceipt
    }

export type JitRuntimeDeps = {
  client: JitAuthorityClient
  db: JitMirrorDb
  ownerId: () => string | null
  accountGeneration: () => number | null
  authorizationCurrent: () => boolean
  now?: () => number
  embeddingContract?: () => JitEmbeddingContract | null
  deviceId?: () => string
  /** Already-authorized local/account calendar source. It must not prompt. */
  calendarObservation?: () => Promise<{ authorized: boolean; events: JitCalendarEvent[] }>
  /** Existence check against the real Rewind frame table before a permanent pin. */
  frameExists?: (frameId: number) => boolean
}

export type JitNanoTriageDecision = 'approved' | 'rejected' | 'unknown'

const ROLLOUT_CACHE_MS = 30_000
const SNAPSHOT_CACHE_MS = 30_000
// A failed rollout decision used to reset the cache stamp, so an offline machine
// or a 5xx re-asked on every analyzed frame — roughly one authenticated request
// per second, forever. Failures are cached too, with a backoff that doubles from
// the normal cache window up to ten minutes and resets on the first success.
const ROLLOUT_FAILURE_BACKOFF_MIN_MS = ROLLOUT_CACHE_MS
const ROLLOUT_FAILURE_BACKOFF_MAX_MS = 600_000

function hasAttestedEmbedding(
  trigger: JitCompiledTrigger,
  observation: JitTriggerObservation,
  contract: JitEmbeddingContract | null
): boolean {
  const embedding = trigger.embedding
  if (!embedding || !contract) return false
  const score = observation.embeddingScores?.[embedding.prototypeId]
  return Boolean(
    score &&
    score.modelId === contract.modelId &&
    score.modelVersion === contract.modelVersion &&
    score.language === contract.language &&
    score.prototypeRevision === embedding.prototypeRevision &&
    Number.isFinite(score.score) &&
    score.score >= 0 &&
    score.score <= 1
  )
}

function authorityFromDecision(
  decision: JitRolloutDecision,
  ownerId: string | null,
  generation: number | null,
  snapshot: JitMirrorReceipt | null,
  current: boolean
): JitRuntimeAuthority {
  return {
    mode:
      decision.rollout === 'enabled' &&
      decision.killSwitch === 'disabled' &&
      decision.effective === 'enabled'
        ? 'enabled'
        : 'compatibility_rollback',
    killSwitchEnabled: decision.killSwitch === 'enabled',
    ownerId,
    accountGeneration: generation,
    snapshotOwnerId: snapshot?.ownerId ?? null,
    snapshotAccountGeneration: snapshot?.accountGeneration ?? null,
    snapshotIsAuthoritative: snapshot !== null,
    authorizationIsCurrent: current
  }
}

export class WindowsJitRuntime {
  private rollout: JitRolloutDecision | null = null
  private rolloutAt = 0
  private rolloutFailureAt = 0
  private rolloutFailures = 0
  private snapshotReceipt: JitMirrorReceipt | null = null
  private snapshotAt = 0
  private ledgerReceipt: JitLedgerMirrorReceipt | null = null
  private policy: JitRuntimePolicy | null = null
  private calendarCacheAt = 0
  private calendarCache: { authorized: boolean; events: JitCalendarEvent[] } | null = null
  private readonly pending = new Map<string, { claim: JitWakeupClaim; receipt: JitMirrorReceipt }>()

  constructor(private readonly deps: JitRuntimeDeps) {}

  /** Opaque local identity for metadata and durable dedupe only. */
  opaqueContextId(contextId: string): string {
    return deriveJitOpaqueId(this.deps.db, 'context', contextId)
  }

  private opaqueId(namespace: string, seed: string): string {
    return deriveJitOpaqueId(this.deps.db, namespace, seed)
  }

  private deviceId(): string {
    const supplied = this.deps.deviceId?.()
    return supplied ? this.opaqueId('device', supplied) : jitInstallationDeviceId(this.deps.db)
  }

  static withDefaultDb(
    db: JitMirrorDb,
    ownerId: () => string | null,
    accountGeneration: () => number | null,
    authorizationCurrent: () => boolean
  ): WindowsJitRuntime {
    return new WindowsJitRuntime({
      client: createJitAuthorityClient(),
      db,
      ownerId,
      accountGeneration,
      authorizationCurrent,
      calendarObservation: async () => {
        const { isConnected } = await import('../integrations/oauth')
        if (!isConnected()) return { authorized: false, events: [] }
        const { fetchCalendar } = await import('../integrations/google')
        const events = await fetchCalendar()
        return {
          authorized: true,
          events: events
            .slice(0, 32)
            .map((event) => ({ title: event.title, eventType: 'calendar_event' }))
        }
      },
      frameExists: (frameId) =>
        Boolean(db.prepare('SELECT id FROM rewind_frames WHERE id = ?').get(frameId))
    })
  }

  private now(): number {
    return this.deps.now?.() ?? Date.now()
  }

  private clearAuthorityCaches(): void {
    try {
      this.cancelAll()
    } catch {
      // Authority must fail closed even if the local lease database is
      // unavailable while signing out or processing a kill-switch response.
      this.pending.clear()
    }
    this.snapshotReceipt = null
    this.snapshotAt = 0
    this.ledgerReceipt = null
    this.policy = null
  }

  /** Exponential from the ordinary cache window to ten minutes. */
  private rolloutBackoffMs(): number {
    return Math.min(
      ROLLOUT_FAILURE_BACKOFF_MAX_MS,
      ROLLOUT_FAILURE_BACKOFF_MIN_MS * 2 ** (this.rolloutFailures - 1)
    )
  }

  private async authority(): Promise<JitRuntimeAuthority> {
    const ownerId = this.deps.ownerId()
    const generation = this.deps.accountGeneration()
    // Account generation is not part of the Firebase token on Windows. The
    // first authoritative snapshot supplies it; the durable receipt then fences
    // subsequent snapshots. Richer session providers may still supply it here.
    if (!ownerId || !this.deps.authorizationCurrent()) {
      this.rollout = null
      this.rolloutAt = 0
      this.rolloutFailures = 0
      this.rolloutFailureAt = 0
      this.clearAuthorityCaches()
      return { ...JIT_RUNTIME_DEFAULT_AUTHORITY }
    }
    const now = this.now()
    if (!this.rollout || now - this.rolloutAt >= ROLLOUT_CACHE_MS) {
      // An error is NOT enabled, and it is also not a licence to retry on every
      // analyzed frame: honour the failure backoff before asking again.
      if (this.rolloutFailures > 0 && now - this.rolloutFailureAt < this.rolloutBackoffMs())
        return { ...JIT_RUNTIME_DEFAULT_AUTHORITY, ownerId, accountGeneration: generation }
      try {
        this.rollout = await this.deps.client.rolloutDecision()
        this.rolloutAt = now
        this.rolloutFailures = 0
        this.rolloutFailureAt = 0
      } catch {
        this.rollout = null
        this.rolloutAt = 0
        this.rolloutFailures += 1
        this.rolloutFailureAt = now
        this.clearAuthorityCaches()
      }
    }
    if (!this.rollout)
      return { ...JIT_RUNTIME_DEFAULT_AUTHORITY, ownerId, accountGeneration: generation }
    const authority = authorityFromDecision(
      this.rollout,
      ownerId,
      generation,
      this.snapshotReceipt,
      this.deps.authorizationCurrent()
    )
    if (authority.mode !== 'enabled') this.clearAuthorityCaches()
    return authority
  }

  private async refreshSnapshot(): Promise<{
    authority: JitRuntimeAuthority
    triggers: JitCompiledTrigger[]
    receipt: JitMirrorReceipt
    ledger: JitLedgerMirrorReceipt | null
    policy: JitRuntimePolicy
  } | null> {
    const ownerId = this.deps.ownerId()
    if (!ownerId || !this.deps.authorizationCurrent()) {
      this.clearAuthorityCaches()
      return null
    }
    const authority = await this.authority()
    if (authority.mode !== 'enabled') return null
    if (
      this.snapshotReceipt &&
      this.snapshotAt > 0 &&
      this.now() - this.snapshotAt < SNAPSHOT_CACHE_MS &&
      this.policy
    ) {
      try {
        return {
          authority: {
            ...authority,
            accountGeneration: this.snapshotReceipt.accountGeneration,
            snapshotOwnerId: this.snapshotReceipt.ownerId,
            snapshotAccountGeneration: this.snapshotReceipt.accountGeneration,
            snapshotIsAuthoritative: true
          },
          triggers: readCompiledJitTriggers(this.deps.db, this.snapshotReceipt),
          receipt: this.snapshotReceipt,
          ledger: this.ledgerReceipt,
          policy: this.policy
        }
      } catch {
        this.snapshotReceipt = null
        this.policy = null
      }
    }
    try {
      try {
        const ledgerPages: JitLedgerMirrorPage[] = []
        let cursor: string | null = null
        const cursors = new Set<string>()
        let previousPage: JitLedgerMirrorPage | null = null
        // The backend cursor is signed and bounded by its authoritative scan. Do
        // not impose a client page-count ceiling: a large legacy ledger must
        // converge instead of silently rolling back after page 32. The repeated
        // cursor guard remains the termination fence for a malformed server.
        while (true) {
          const page = await this.deps.client.ledgerMirrorPage(cursor)
          if (
            page.failureReason ||
            page.schemaVersion !== 'knowledge_ledger_mirror.v1' ||
            page.ownerId !== ownerId ||
            page.rows.length > 500 ||
            !page.chainRevision ||
            page.scannedCount < page.rows.length ||
            page.projectedCount < page.rows.length ||
            page.projectedCount > page.scannedCount ||
            page.terminalCount < 0 ||
            page.terminalCount > page.scannedCount
          )
            throw new Error('incomplete ledger mirror page')
          if (previousPage) {
            const first = ledgerPages[0]
            if (
              page.accountGeneration !== first.accountGeneration ||
              page.sourceGeneration !== first.sourceGeneration ||
              page.writerEpoch !== first.writerEpoch ||
              page.headCommitId !== first.headCommitId ||
              page.commitSequence !== first.commitSequence ||
              page.epochId !== first.epochId
            )
              throw new Error('ledger mirror fence changed')
            if (
              page.scannedCount <= previousPage.scannedCount ||
              page.projectedCount < previousPage.projectedCount ||
              page.chainRevision === previousPage.chainRevision ||
              (page.terminalCountFromServer === true &&
                previousPage.terminalCountFromServer === true &&
                page.terminalCount < previousPage.terminalCount)
            )
              throw new Error('ledger mirror chain transition invalid')
          }
          ledgerPages.push(page)
          previousPage = page
          if (page.finalPage) break
          if (!page.nextCursor || cursors.has(page.nextCursor))
            throw new Error('ledger mirror cursor incomplete')
          cursors.add(page.nextCursor)
          cursor = page.nextCursor
        }
        const lastPage = ledgerPages.at(-1)
        if (!lastPage?.finalPage) throw new Error('ledger mirror final page missing')
        const firstPage = ledgerPages[0]
        const accumulatedRows = ledgerPages.flatMap((page) => page.rows)
        if (!firstPage || firstPage.projectedCount !== firstPage.rows.length)
          throw new Error('ledger mirror first projected count mismatch')
        for (let index = 1; index < ledgerPages.length; index++) {
          const previous = ledgerPages[index - 1]
          const current = ledgerPages[index]
          if (current.projectedCount - previous.projectedCount !== current.rows.length)
            throw new Error('ledger mirror projected count omitted or torn')
          if (
            (current.terminalCountFromServer === true) !==
            (previous.terminalCountFromServer === true)
          )
            throw new Error('ledger mirror terminal fence changed')
          if (
            current.terminalCountFromServer === true &&
            current.terminalCount - previous.terminalCount !==
              current.rows.filter((row) => row.status !== 'active').length
          )
            throw new Error('ledger mirror terminal count omitted or torn')
        }
        if (lastPage.projectedCount !== accumulatedRows.length)
          throw new Error('ledger mirror cumulative projected count mismatch')
        const accumulatedTerminalCount = accumulatedRows.filter(
          (row) => row.status !== 'active'
        ).length
        if (
          lastPage.terminalCountFromServer === true &&
          lastPage.terminalCount !== accumulatedTerminalCount
        )
          throw new Error('ledger mirror cumulative terminal count mismatch')
        const terminalCount = lastPage.terminalCountFromServer
          ? lastPage.terminalCount
          : accumulatedTerminalCount
        this.ledgerReceipt = reconcileJitLedgerMirror(
          this.deps.db,
          {
            fence: {
              ownerId: lastPage.ownerId,
              accountGeneration: lastPage.accountGeneration,
              sourceGeneration: lastPage.sourceGeneration,
              writerEpoch: lastPage.writerEpoch,
              headCommitId: lastPage.headCommitId,
              commitSequence: lastPage.commitSequence,
              epochId: lastPage.epochId,
              pageRevision: lastPage.pageRevision,
              schemaVersion: lastPage.schemaVersion,
              chainRevision: lastPage.chainRevision,
              scannedCount: lastPage.scannedCount,
              projectedCount: lastPage.projectedCount,
              terminalCount
            },
            rows: accumulatedRows,
            aliases: ledgerPages.flatMap((page) => page.aliases)
          },
          ownerId,
          this.now()
        )
      } catch {
        // Fail closed for the mirror only. A torn or incomplete ledger must not
        // discard a complete trigger snapshot or reopen the Insight pipeline.
      }
      const snapshot = await this.deps.client.triggerSnapshot()
      if (!snapshot.complete || Boolean(snapshot.failureReason))
        throw new Error('incomplete trigger snapshot')
      const receipt = reconcileJitTriggerSnapshot(this.deps.db, snapshot, ownerId, this.now())
      const triggers = readCompiledJitTriggers(this.deps.db, receipt)
      if (
        snapshot.policy.embedding.enabled &&
        triggers.some(
          (trigger) =>
            trigger.embedding !== null &&
            trigger.embedding.minSimilarity !== snapshot.policy.embedding.matchSimilarity
        )
      )
        throw new Error('embedding trigger threshold disagrees with policy')
      this.snapshotReceipt = receipt
      this.snapshotAt = this.now()
      this.policy = snapshot.policy
      return {
        authority: {
          ...authority,
          accountGeneration: receipt.accountGeneration,
          snapshotOwnerId: receipt.ownerId,
          snapshotAccountGeneration: receipt.accountGeneration,
          snapshotIsAuthoritative: true
        },
        triggers,
        receipt,
        ledger: this.ledgerReceipt,
        policy: snapshot.policy
      }
    } catch {
      this.snapshotReceipt = null
      this.snapshotAt = 0
      this.policy = null
      return null
    }
  }

  /** Evaluate one local context observation. No observation text is persisted or logged. */
  async admit(observation: JitTriggerObservation, budgetDay: string): Promise<JitAdmission> {
    const loaded = await this.refreshSnapshot()
    if (!loaded) {
      const authority = await this.authority()
      return authority.mode === 'enabled'
        ? { kind: 'suppressed', reason: 'authoritative_snapshot_unavailable' }
        : {
            kind: 'legacy_fallback',
            reason: authority.killSwitchEnabled ? 'kill_switch' : 'rollout_disabled_or_unknown'
          }
    }
    const localEmbedding = this.deps.embeddingContract?.() ?? null
    const policyEmbedding = loaded.policy.embedding
    const embeddingContract =
      policyEmbedding.enabled &&
      localEmbedding &&
      policyEmbedding.modelId === localEmbedding.modelId &&
      policyEmbedding.modelVersion === localEmbedding.modelVersion &&
      policyEmbedding.language === localEmbedding.language
        ? localEmbedding
        : null
    const evaluation = evaluateJitWatchlist(
      loaded.authority,
      loaded.triggers,
      observation,
      budgetDay,
      {},
      embeddingContract,
      loaded.policy.embedding.triageSimilarity
    )
    const winner = evaluation.matches[0]
    if (winner) {
      if (winner.trigger.wakeupBudgetPerDay !== loaded.policy.plannedNotificationsPerTriggerPerDay)
        return { kind: 'suppressed', reason: 'planned_policy_budget_mismatch' }
      const observationFingerprint = this.opaqueId(
        'observation',
        winner.decision.observationFingerprint
      )
      const continuityKey = this.opaqueId(
        'continuity',
        `jit:${winner.trigger.id}:${loaded.receipt.snapshotRevision}:${budgetDay}:${winner.decision.observationFingerprint}`
      )
      const claim = claimJitWakeup(this.deps.db, {
        continuityKey,
        triggerId: winner.trigger.id,
        lane: 'planned',
        budgetDay,
        snapshotRevision: loaded.receipt.snapshotRevision,
        observationFingerprint,
        budget: winner.trigger.wakeupBudgetPerDay,
        globalDailyBudget: loaded.policy.totalProactiveNotificationsPerDay,
        now: this.now()
      })
      if (!claim) return { kind: 'suppressed', reason: 'planned_budget_or_duplicate' }
      this.pending.set(continuityKey, { claim, receipt: loaded.receipt })
      return {
        kind: 'planned',
        triggerId: winner.trigger.id,
        triggerRevision: winner.trigger.revision,
        continuityKey,
        prompt: winner.trigger.action.prompt,
        claim,
        receipt: loaded.receipt
      }
    }
    if (evaluation.nextLane === 'bounded_planned_triage')
      return { kind: 'suppressed', reason: 'planned_match_ambiguous' }
    if (evaluation.nextLane === 'none') {
      return loaded.triggers.length === 0
        ? { kind: 'suppressed', reason: 'empty_watchlist' }
        : { kind: 'suppressed', reason: 'planned_runtime_rejected' }
    }
    return { kind: 'suppressed', reason: 'no_eligible_planned_trigger' }
  }

  /**
   * Resolve an ambiguous planned trigger through the bounded nano lane. The
   * server reservation is made before the classifier call, and the resulting
   * planned admission still has to reserve its notification and full turn at
   * the later paid/display boundary.
   */
  async admitAmbiguousPlanned(
    observation: JitTriggerObservation,
    budgetDay: string,
    nanoTriage?: (input: {
      triggerId: string
      triggerRevision: number
      observationFingerprint: string
    }) => Promise<JitNanoTriageDecision>
  ): Promise<JitAdmission> {
    const loaded = await this.refreshSnapshot()
    if (!loaded) return { kind: 'suppressed', reason: 'authoritative_snapshot_unavailable' }
    if (!nanoTriage) return { kind: 'suppressed', reason: 'planned_nano_unavailable' }
    const localEmbedding = this.deps.embeddingContract?.() ?? null
    const policyEmbedding = loaded.policy.embedding
    const embeddingContract =
      policyEmbedding.enabled &&
      localEmbedding &&
      policyEmbedding.modelId === localEmbedding.modelId &&
      policyEmbedding.modelVersion === localEmbedding.modelVersion &&
      policyEmbedding.language === localEmbedding.language
        ? localEmbedding
        : null
    const evaluation = evaluateJitWatchlist(
      loaded.authority,
      loaded.triggers,
      observation,
      budgetDay,
      {},
      embeddingContract,
      loaded.policy.embedding.triageSimilarity
    )
    if (evaluation.nextLane !== 'bounded_planned_triage' || evaluation.ambiguous.length === 0)
      return { kind: 'suppressed', reason: 'no_ambiguous_planned_trigger' }
    const candidate = evaluation.ambiguous.find(({ trigger, decision }) => {
      const embeddingMissing = trigger.embedding
        ? decision.missingConditions.includes(`embedding:${trigger.embedding.prototypeId}`)
        : false
      return !embeddingMissing || hasAttestedEmbedding(trigger, observation, embeddingContract)
    })
    if (!candidate) return { kind: 'suppressed', reason: 'embedding_not_attested' }
    // A missing trigger cap is never an implicit permission to buy a nano call.
    if (candidate.trigger.wakeupBudgetPerDay === null)
      return { kind: 'suppressed', reason: 'planned_budget_missing' }
    const fingerprint = this.opaqueId('observation', candidate.decision.observationFingerprint)
    const nanoKey = this.opaqueId(
      'continuity',
      `planned-nano:${candidate.trigger.id}:${candidate.trigger.revision}:${candidate.decision.observationFingerprint}:${budgetDay}`
    )
    const nanoClaim = claimJitWakeup(this.deps.db, {
      continuityKey: nanoKey,
      triggerId: candidate.trigger.id,
      lane: 'ambient_nano',
      budgetDay,
      snapshotRevision: loaded.receipt.snapshotRevision,
      observationFingerprint: fingerprint,
      budget: null,
      now: this.now()
    })
    if (!nanoClaim) return { kind: 'suppressed', reason: 'planned_nano_duplicate' }
    const reserve = this.deps.client.reserveProactivity
    if (!reserve) {
      completeJitWakeup(this.deps.db, nanoClaim, this.now())
      return { kind: 'suppressed', reason: 'reservation_client_unavailable' }
    }
    const deviceId = this.deviceId()
    const nanoEventId = this.opaqueId('event', nanoKey)
    const nanoCandidateId = this.opaqueId(
      'candidate',
      `planned-nano:${candidate.trigger.id}:${candidate.trigger.revision}:${candidate.decision.observationFingerprint}`
    )
    try {
      const reservation = await reserve({
        eventId: nanoEventId,
        candidateId: nanoCandidateId,
        operation: 'nano_triage',
        accountGeneration: loaded.receipt.accountGeneration,
        deviceId,
        triggerMemoryId: candidate.trigger.id,
        triggerRevision: candidate.trigger.revision
      })
      persistJitProactivityReservation(this.deps.db, {
        eventId: reservation.receipt.eventId,
        ownerId: reservation.receipt.uid,
        accountGeneration: reservation.receipt.accountGeneration,
        candidateId: reservation.receipt.candidateId,
        operation: reservation.receipt.operation,
        requestHash: reservation.receipt.requestHash,
        serverReceiptJson: JSON.stringify(reservation.receipt),
        createdAt: this.now()
      })
      if (!reservation.reserved) {
        completeJitWakeup(this.deps.db, nanoClaim, this.now())
        return { kind: 'suppressed', reason: 'planned_nano_already_consumed' }
      }
    } catch {
      completeJitWakeup(this.deps.db, nanoClaim, this.now())
      return { kind: 'suppressed', reason: 'planned_nano_reservation_failed' }
    }
    let verdict: JitNanoTriageDecision
    try {
      verdict = await nanoTriage({
        triggerId: candidate.trigger.id,
        triggerRevision: candidate.trigger.revision,
        observationFingerprint: fingerprint
      })
    } catch {
      verdict = 'unknown'
    }
    completeJitWakeup(this.deps.db, nanoClaim, this.now())
    if (verdict !== 'approved') return { kind: 'suppressed', reason: 'planned_nano_rejected' }
    const continuityKey = this.opaqueId(
      'continuity',
      `jit:${candidate.trigger.id}:${loaded.receipt.snapshotRevision}:${budgetDay}:${candidate.decision.observationFingerprint}`
    )
    const claim = claimJitWakeup(this.deps.db, {
      continuityKey,
      triggerId: candidate.trigger.id,
      lane: 'planned',
      budgetDay,
      snapshotRevision: loaded.receipt.snapshotRevision,
      observationFingerprint: fingerprint,
      budget: candidate.trigger.wakeupBudgetPerDay,
      now: this.now()
    })
    if (!claim) return { kind: 'suppressed', reason: 'planned_budget_or_duplicate' }
    this.pending.set(continuityKey, { claim, receipt: loaded.receipt })
    return {
      kind: 'planned',
      triggerId: candidate.trigger.id,
      triggerRevision: candidate.trigger.revision,
      continuityKey,
      prompt: candidate.trigger.action.prompt,
      claim,
      receipt: loaded.receipt
    }
  }

  /**
   * Ambient is intentionally a caller-controlled second lane. Windows does not
   * invent semantic novelty from raw text; the existing context framework must
   * supply a bounded fingerprint and a local relevance decision. The installed
   * nano-triage adapter is invoked only after the server reservation; absent an
   * adapter, no call is purchased and the legacy framework remains the rollback
   * path.
   */
  async admitAmbient(input: {
    contextId: string
    semanticFingerprint: string
    locallyRelevant: boolean
    budgetDay: string
    nanoTriage?: (input: {
      contextId: string
      semanticFingerprint: string
    }) => Promise<'approved' | 'rejected' | 'unknown'>
  }): Promise<JitAdmission> {
    const loaded = await this.refreshSnapshot()
    if (!loaded) return { kind: 'suppressed', reason: 'authoritative_snapshot_unavailable' }
    if (
      !input.contextId ||
      !/^[0-9a-f]{8,128}$/i.test(input.semanticFingerprint) ||
      !input.locallyRelevant ||
      !input.nanoTriage
    )
      return { kind: 'suppressed', reason: 'ambient_local_gate' }
    const contextId = this.opaqueContextId(input.contextId)
    const semanticFingerprint = this.opaqueId('semantic', input.semanticFingerprint)
    if (
      !claimJitAmbientContext(this.deps.db, {
        contextId,
        semanticFingerprint,
        now: this.now()
      })
    )
      return { kind: 'suppressed', reason: 'ambient_context_cooldown' }
    const nanoKey = this.opaqueId(
      'continuity',
      `ambient-nano:${input.contextId}:${input.semanticFingerprint}:${input.budgetDay}`
    )
    const nanoClaim = claimJitWakeup(this.deps.db, {
      continuityKey: nanoKey,
      triggerId: `ambient:${contextId}`,
      lane: 'ambient_nano',
      budgetDay: input.budgetDay,
      snapshotRevision: loaded.receipt.snapshotRevision,
      observationFingerprint: semanticFingerprint,
      // The local row is a dedupe lease only. The eight-per-user/day authority
      // lives in the backend reservation below, never in this context bucket.
      budget: null,
      globalDailyBudget: undefined,
      now: this.now()
    })
    if (!nanoClaim) return { kind: 'suppressed', reason: 'ambient_nano_budget' }
    if (!this.deps.client.reserveProactivity) {
      completeJitWakeup(this.deps.db, nanoClaim, this.now())
      return { kind: 'suppressed', reason: 'reservation_client_unavailable' }
    }
    const nanoEventId = this.opaqueId(
      'event',
      `ambient-nano:${input.contextId}:${input.semanticFingerprint}:${input.budgetDay}`
    )
    let reservation
    try {
      reservation = await this.deps.client.reserveProactivity({
        eventId: nanoEventId,
        candidateId: this.opaqueId('candidate', input.semanticFingerprint),
        operation: 'nano_triage',
        accountGeneration: loaded.receipt.accountGeneration,
        deviceId: this.deviceId(),
        triggerMemoryId: null,
        triggerRevision: null
      })
      persistJitProactivityReservation(this.deps.db, {
        eventId: reservation.receipt.eventId,
        ownerId: reservation.receipt.uid,
        accountGeneration: reservation.receipt.accountGeneration,
        candidateId: reservation.receipt.candidateId,
        operation: reservation.receipt.operation,
        requestHash: reservation.receipt.requestHash,
        serverReceiptJson: JSON.stringify(reservation.receipt),
        createdAt: this.now()
      })
    } catch {
      completeJitWakeup(this.deps.db, nanoClaim, this.now())
      return { kind: 'suppressed', reason: 'reservation_failed' }
    }
    if (!reservation.reserved) {
      completeJitWakeup(this.deps.db, nanoClaim, this.now())
      return { kind: 'suppressed', reason: 'reservation_already_consumed' }
    }
    let verdict: 'approved' | 'rejected' | 'unknown'
    try {
      verdict = await input.nanoTriage({ contextId, semanticFingerprint })
    } catch {
      verdict = 'unknown'
    }
    completeJitWakeup(this.deps.db, nanoClaim, this.now())
    if (verdict !== 'approved') return { kind: 'suppressed', reason: 'ambient_nano_rejected' }
    const continuityKey = this.opaqueId(
      'continuity',
      `ambient:${input.contextId}:${input.semanticFingerprint}:${input.budgetDay}`
    )
    const claim = claimJitWakeup(this.deps.db, {
      continuityKey,
      triggerId: `ambient:${contextId}`,
      lane: 'ambient',
      budgetDay: input.budgetDay,
      snapshotRevision: loaded.receipt.snapshotRevision,
      observationFingerprint: semanticFingerprint,
      budget: 1,
      globalDailyBudget: loaded.policy.totalProactiveNotificationsPerDay,
      now: this.now()
    })
    if (!claim) return { kind: 'suppressed', reason: 'ambient_budget_or_duplicate' }
    this.pending.set(continuityKey, { claim, receipt: loaded.receipt })
    return {
      kind: 'ambient_candidate',
      continuityKey,
      candidateId: this.opaqueId('candidate', continuityKey),
      claim,
      receipt: loaded.receipt
    }
  }

  /** Server authority at a paid or display boundary. Local claims are only
   * dedupe/lease state and cannot substitute for this call. */
  async reserveOperation(
    admission: Extract<JitAdmission, { kind: 'planned' | 'ambient_candidate' }>,
    operation: 'full_turn' | 'planned_notification' | 'ambient_notification',
    parentEventId: string | null = null
  ): Promise<import('./jitAuthorityClient').JitProactivityReservation | null> {
    const receipt = admission.receipt
    const reserve = this.deps.client.reserveProactivity
    const triggerId = admission.kind === 'planned' ? admission.triggerId : null
    const triggerRevision = admission.kind === 'planned' ? admission.triggerRevision : null
    const seed = admission.continuityKey
    const candidateId = this.opaqueId(
      'candidate',
      admission.kind === 'planned'
        ? `planned:${triggerId}:${triggerRevision}`
        : `ambient:${admission.candidateId}`
    )
    if (!reserve) return null
    try {
      const result = await reserve({
        eventId: this.opaqueId('event', `${operation}:${seed}`),
        candidateId,
        operation,
        accountGeneration: receipt.accountGeneration,
        deviceId: this.deviceId(),
        triggerMemoryId: triggerId,
        triggerRevision,
        parentEventId
      })
      persistJitProactivityReservation(this.deps.db, {
        eventId: result.receipt.eventId,
        ownerId: result.receipt.uid,
        accountGeneration: result.receipt.accountGeneration,
        candidateId: result.receipt.candidateId,
        operation: result.receipt.operation,
        requestHash: result.receipt.requestHash,
        serverReceiptJson: JSON.stringify(result.receipt),
        createdAt: this.now()
      })
      return result.reserved ? result : null
    } catch {
      return null
    }
  }

  begin(continuityKey: string): boolean {
    const pending = this.pending.get(continuityKey)
    if (!pending || !this.deps.authorizationCurrent()) return false
    return beginJitWakeup(this.deps.db, pending.claim, this.now())
  }

  complete(continuityKey: string): boolean {
    const pending = this.pending.get(continuityKey)
    if (!pending) return false
    this.pending.delete(continuityKey)
    return completeJitWakeup(this.deps.db, pending.claim, this.now())
  }

  cancel(continuityKey: string): boolean {
    const pending = this.pending.get(continuityKey)
    if (!pending) return false
    this.pending.delete(continuityKey)
    return cancelJitWakeup(this.deps.db, pending.claim, this.now())
  }

  clearForSignOut(): void {
    this.clearAuthorityCaches()
    this.pending.clear()
    this.rollout = null
    this.rolloutAt = 0
    this.rolloutFailures = 0
    this.rolloutFailureAt = 0
  }

  cancelAll(): void {
    for (const continuityKey of [...this.pending.keys()]) this.cancel(continuityKey)
  }

  pinConversationKeyframe(
    frameId: number,
    conversationId: string,
    imagePath = '',
    rendererDeletionKey?: string
  ): boolean {
    const ownerId = this.deps.ownerId()
    if (!ownerId || !Number.isInteger(frameId) || frameId < 0 || !this.deps.frameExists?.(frameId))
      return false
    try {
      pinJitConversationKeyframe(this.deps.db, {
        frameId,
        ownerId,
        conversationId,
        imagePath,
        rendererDeletionKey,
        pinnedAt: this.now()
      })
      return true
    } catch {
      return false
    }
  }

  markAmbientFrameTemporary(frameId: number): boolean {
    const ownerId = this.deps.ownerId()
    if (!ownerId || !Number.isInteger(frameId) || frameId < 0) return false
    const createdAt = this.now()
    try {
      markJitTemporaryFrame(this.deps.db, {
        frameId,
        ownerId,
        createdAt,
        expiresAt: createdAt + 7 * 24 * 60 * 60_000
      })
      return true
    } catch {
      return false
    }
  }

  /**
   * Read-only view of the cached rollout + snapshot authority. Unlike
   * `isAuthoritativeEnabled()` it never clears caches or cancels leases, so it is
   * safe to consult from evidence-gathering paths that run BEFORE admission.
   */
  cachedAuthoritativeEnabled(): boolean {
    const ownerId = this.deps.ownerId()
    const effective =
      ownerId !== null &&
      this.deps.authorizationCurrent() &&
      this.rollout !== null &&
      this.now() - this.rolloutAt < ROLLOUT_CACHE_MS &&
      this.rollout.rollout === 'enabled' &&
      this.rollout.killSwitch === 'disabled' &&
      this.rollout.effective === 'enabled'
    return effective && this.policy !== null && this.snapshotReceipt?.ownerId === ownerId
  }

  /**
   * Insight pipeline gate. Effective rollout consumes the visit even when the
   * trigger snapshot is incomplete or the ledger mirror failed — those are
   * suppress, not a licence to run the legacy Gemini path.
   */
  shouldSuppressLegacyInsight(): boolean {
    const ownerId = this.deps.ownerId()
    return (
      ownerId !== null &&
      this.deps.authorizationCurrent() &&
      this.rollout !== null &&
      this.now() - this.rolloutAt < ROLLOUT_CACHE_MS &&
      this.rollout.rollout === 'enabled' &&
      this.rollout.killSwitch === 'disabled' &&
      this.rollout.effective === 'enabled'
    )
  }

  isAuthoritativeEnabled(): boolean {
    if (!this.cachedAuthoritativeEnabled()) {
      this.clearAuthorityCaches()
      return false
    }
    return true
  }

  /** Frame adapter for the existing Windows proactive framework. */
  observationFromFrame(frame: RewindFrame): JitTriggerObservation {
    // The coordinator's privacy gate runs before this adapter. Keep the OCR
    // bounded and in-memory; it is never persisted in the JIT mirror or logs.
    const text = typeof frame.ocrText === 'string' ? frame.ocrText.slice(0, 8_000) : ''
    return {
      eventId: frame.id == null ? null : String(frame.id),
      text,
      entityLabels: [frame.app, frame.windowTitle].filter(Boolean),
      appName: frame.app,
      windowTitle: frame.windowTitle,
      occurredAt: new Date(frame.ts)
    }
  }

  /** Add calendar evidence only from an already-authorized source. The cache
   * bounds account reads to one refresh per minute; no prompt or hot-loop retry
   * is introduced when the source is absent or unavailable.
   *
   * The provider is a LIVE account read (Google Calendar). It is therefore gated
   * on the cached authority: a user the server has not admitted to the JIT lane
   * must pay zero calendar requests for it, so until the rollout and snapshot
   * caches say enabled the observation stays purely local. The first frame after
   * a cold start is evaluated without calendar evidence by design; admission
   * populates the caches and later frames carry it. */
  async observationForFrame(frame: RewindFrame): Promise<JitTriggerObservation> {
    const observation = this.observationFromFrame(frame)
    const provider = this.deps.calendarObservation
    if (!provider || !this.cachedAuthoritativeEnabled()) return observation
    const now = this.now()
    if (!this.calendarCache || now - this.calendarCacheAt >= 60_000) {
      try {
        const next = await provider()
        this.calendarCache = {
          authorized: next.authorized === true,
          events: next.events.slice(0, 32)
        }
        this.calendarCacheAt = now
      } catch {
        this.calendarCache = { authorized: false, events: [] }
        this.calendarCacheAt = now
      }
    }
    return {
      ...observation,
      calendarAuthorized: this.calendarCache.authorized,
      calendarEvents: this.calendarCache.events.slice(0, 32)
    }
  }
}
