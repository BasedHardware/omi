import { getBackendSession, getSessionEpoch } from '../assistants/core/session'
import { hasKnownControlPlaneOwner } from '../agentKernel/controlPlane'
import type { ProactiveAssistant, AssistantResult } from '../assistants/core/coordinator'
import { createJitAuthorityClient, type JitAuthorityClient } from './jitAuthorityClient'
import { reconcileJitLedgerMirror, type JitMirrorDb, type JitLedgerMirrorPage, type JitLedgerMirrorReceipt } from './jitTriggerMirror'
import type { JitRolloutDecision } from '../../shared/jitRollout'

/** Canonical mirror projection survives retirement of trigger matching and delivery. */
export async function syncKnowledgeLedgerMirror(
  db: JitMirrorDb,
  client: JitAuthorityClient,
  ownerId: string,
  isCurrent: () => boolean,
  now = Date.now()
): Promise<JitLedgerMirrorReceipt> {
  const ledgerPages: JitLedgerMirrorPage[] = []
  let cursor: string | null = null
  const cursors = new Set<string>()
  let previousPage: JitLedgerMirrorPage | null = null
  // The backend cursor is signed and bounded by its authoritative scan. Do
  // not impose a client page-count ceiling: a large legacy ledger must
  // converge instead of silently rolling back after page 32. The repeated
  // cursor guard remains the termination fence for a malformed server.
  while (true) {
    if (!isCurrent()) throw new Error('ledger mirror owner changed')
    const page = await client.ledgerMirrorPage(cursor)
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
  if (!isCurrent()) throw new Error('ledger mirror owner changed')
  return reconcileJitLedgerMirror(
    db,
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
    now
  )
}

/** Reuses the existing capture coordinator; no model calls or notifications. */
export class KnowledgeLedgerMirrorSync implements ProactiveAssistant {
  readonly identifier = 'knowledge-ledger-mirror'
  readonly displayName = 'Knowledge ledger synchronization'
  private readonly client = createJitAuthorityClient()
  private owner: string | null = null
  private decision: JitRolloutDecision | null = null
  private checkedAt = 0
  private failedAt = 0
  private failures = 0
  private syncedAt = 0

  constructor(private readonly db: JitMirrorDb, private readonly ownerId: () => string | null) {}

  isEnabled(): boolean {
    return getBackendSession() !== null && hasKnownControlPlaneOwner()
  }

  async analyze(): Promise<AssistantResult | null> {
    const owner = this.ownerId()
    if (!owner || owner !== this.owner) {
      this.stop()
      this.owner = owner
    }
    if (!owner) return null
    const epoch = getSessionEpoch()
    const current = (): boolean => getSessionEpoch() === epoch && this.ownerId() === owner
    const now = Date.now()
    if (!this.decision || now - this.checkedAt >= 30_000) {
      if (this.failures && now - this.failedAt < Math.min(600_000, 30_000 * 2 ** (this.failures - 1))) return null
      try {
        const decision = await this.client.rolloutDecision()
        if (!current()) return null
        this.decision = decision
        this.checkedAt = now
        this.failures = 0
      } catch {
        this.decision = null
        this.failedAt = now
        this.failures++
        return null
      }
    }
    if (this.decision.rollout !== 'enabled' || this.decision.killSwitch !== 'disabled' || this.decision.effective !== 'enabled') return null
    if (now - this.syncedAt < 30_000) return null
    this.syncedAt = now
    try {
      await syncKnowledgeLedgerMirror(this.db, this.client, owner, current, now)
    } catch {
      // Leave the previous canonical projection intact; retry on a later capture.
    }
    return null
  }

  handleResult(): void {
    return
  }

  stop(): void {
    this.owner = null
    this.decision = null
    this.checkedAt = this.failedAt = this.failures = this.syncedAt = 0
  }
}
