import { existsSync, mkdirSync, readFileSync, renameSync, rmSync, writeFileSync } from 'node:fs'
import { dirname } from 'node:path'
import type { ProactivityOutcomeRequest } from '../../renderer/src/lib/omiApi.generated'

export type PendingOutcome = { itemID: string; request: ProactivityOutcomeRequest }
type State = { ownerID: string; shown: string[]; outbox: PendingOutcome[] }

/** Atomic ID-only journal: a shown receipt and its outbox event commit together. */
export class ProactivityReceiptStore {
  private state: State
  constructor(
    private readonly path: string,
    ownerID: string
  ) {
    const decoded: State | null = existsSync(path) ? JSON.parse(readFileSync(path, 'utf8')) : null
    this.state = decoded?.ownerID === ownerID ? decoded : { ownerID, shown: [], outbox: [] }
    this.save(this.state)
  }
  hasShown(id: string): boolean {
    return this.state.shown.includes(id)
  }
  get pending(): PendingOutcome[] {
    return [...this.state.outbox]
  }
  record(itemID: string, request: ProactivityOutcomeRequest): void {
    if (request.action === 'timeout' || (request.action === 'shown' && this.hasShown(itemID)))
      return
    if (this.state.outbox.some((e) => e.request.event_id === request.event_id)) return
    this.commit({
      ...this.state,
      shown: request.action === 'shown' ? [...this.state.shown, itemID] : this.state.shown,
      outbox: [...this.state.outbox, { itemID, request }]
    })
  }
  acknowledge(eventID: string): void {
    this.commit({
      ...this.state,
      outbox: this.state.outbox.filter((e) => e.request.event_id !== eventID)
    })
  }
  purge(): void {
    this.state = { ownerID: this.state.ownerID, shown: [], outbox: [] }
    rmSync(this.path, { force: true })
    rmSync(`${this.path}.tmp`, { force: true })
  }
  private commit(next: State): void {
    this.save(next)
    this.state = next
  }
  private save(next: State): void {
    mkdirSync(dirname(this.path), { recursive: true })
    writeFileSync(`${this.path}.tmp`, JSON.stringify(next), { mode: 0o600 })
    renameSync(`${this.path}.tmp`, this.path)
  }
}

export function notificationDeadline(
  createdAt: string,
  serverTime: string,
  now = Date.now()
): number {
  const created = Date.parse(createdAt),
    server = Date.parse(serverTime)
  if (!Number.isFinite(created) || !Number.isFinite(server) || created > server) return 0
  return now + created + 86_400_000 - server
}
