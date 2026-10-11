import { afterEach, describe, expect, it } from 'vitest'
import { mkdtempSync, rmSync, existsSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { ProactivityReceiptStore, notificationDeadline } from './receiptStore'
import type { ProactivityOutcomeRequest } from '../../renderer/src/lib/omiApi.generated'
const dirs: string[] = []
const path = (): string => {
  const dir = mkdtempSync(join(tmpdir(), 'pv2-test-'))
  dirs.push(dir)
  return join(dir, 'state.json')
}
const event = (action: ProactivityOutcomeRequest['action']): ProactivityOutcomeRequest => ({
  action,
  channel: 'feed',
  surface: 'windows',
  event_id: `event-${action}`
})
afterEach(() => dirs.splice(0).forEach((dir) => rmSync(dir, { recursive: true, force: true })))
describe('durable proactivity receipts', () => {
  it('deduplicates shown across feed, push and relaunch while retaining its outbox', () => {
    const file = path(),
      store = new ProactivityReceiptStore(file, 'a')
    expect(store.hasShown('item')).toBe(false)
    store.record('item', event('shown'))
    const restarted = new ProactivityReceiptStore(file, 'a')
    restarted.record('item', { ...event('shown'), channel: 'push' })
    expect(restarted.pending).toHaveLength(1)
    restarted.acknowledge('event-shown')
    expect(new ProactivityReceiptStore(file, 'a').hasShown('item')).toBe(true)
    expect(restarted.pending).toEqual([])
  })
  it('keeps failed outcomes until an acknowledgement and retries the identical event ID', () => {
    const file = path(),
      store = new ProactivityReceiptStore(file, 'a')
    store.record('item', event('opened'))
    expect(new ProactivityReceiptStore(file, 'a').pending[0].request.event_id).toBe('event-opened')
    store.acknowledge('event-opened')
    expect(new ProactivityReceiptStore(file, 'a').pending).toEqual([])
  })
  it('purges foreign owner receipts and deletes the journal on sign-out', () => {
    const file = path(),
      a = new ProactivityReceiptStore(file, 'a')
    a.record('item', event('shown'))
    const b = new ProactivityReceiptStore(file, 'b')
    expect(b.pending).toEqual([])
    expect(b.hasShown('item')).toBe(false)
    writeFileSync(`${file}.tmp`, 'synthetic interrupted atomic write')
    b.purge()
    expect(existsSync(file)).toBe(false)
    expect(existsSync(`${file}.tmp`)).toBe(false)
  })
  it('does not count timeout as shown or as an outcome', () => {
    const store = new ProactivityReceiptStore(path(), 'a')
    store.record('item', event('timeout'))
    expect(store.pending).toEqual([])
    expect(store.hasShown('item')).toBe(false)
  })
  it('uses the server clock for notification expiry', () => {
    expect(notificationDeadline('2026-10-03T12:00:00Z', '2026-10-04T12:00:00Z', 1000)).toBe(1000)
    expect(notificationDeadline('bad', 'bad')).toBe(0)
  })
})
