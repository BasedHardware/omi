import { describe, it, expect, beforeEach } from 'vitest'
import { DatabaseSync } from 'node:sqlite'
import { CONTEXT_BUCKET_SCHEMA } from '../../ipc/contextBucketSchema'
import type { ContextBucketDb } from '../../ipc/contextBucketStore'
import { ContextSubjectBindingService } from './subjectBinding'
import { appWindowEvent, normalizedEvent, type TaskLocalContextEvent } from './tcrs'

const T0 = 1_760_000_000_000

let db: ContextBucketDb
let nowMs: number
let epoch: number
let service: ContextSubjectBindingService

beforeEach(() => {
  db = new DatabaseSync(':memory:') as unknown as ContextBucketDb
  db.exec(CONTEXT_BUCKET_SCHEMA)
  nowMs = T0
  epoch = 1
  service = new ContextSubjectBindingService({
    db: () => db,
    sessionEpoch: () => epoch,
    now: () => nowMs
  })
})

const windowEvent = (): TaskLocalContextEvent =>
  appWindowEvent({
    appName: 'Code',
    windowTitle: 'main.ts',
    occurredAt: nowMs
  }) as TaskLocalContextEvent

describe('ContextSubjectBindingService', () => {
  it('upserts subject-carrying events as explicit bindings and passes them through', () => {
    const withSubject = {
      ...windowEvent(),
      subject: { kind: 'task', id: 't-1', workstreamID: null }
    }
    const resolved = service.resolve(withSubject)
    expect(resolved).toEqual(withSubject)
    const row = db
      .prepare(
        `SELECT subjectKind, subjectID, source FROM subject_bindings WHERE referenceHash = ?`
      )
      .get(withSubject.referenceHash) as Record<string, string>
    expect(row).toEqual({ subjectKind: 'task', subjectID: 't-1', source: 'explicit_open' })
  })

  it('attaches a stored fresh binding on resolve, but never unknown subject kinds', () => {
    const bare = windowEvent()
    service.resolve({ ...bare, subject: { kind: 'workstream', id: 'w-1', workstreamID: 'w-1' } })
    const attached = service.resolve(bare)
    expect(attached.subject).toEqual({ kind: 'workstream', id: 'w-1', workstreamID: 'w-1' })

    const strange = normalizedEvent({
      kind: 'document',
      rawReference: 'doc-x',
      occurredAt: nowMs
    }) as TaskLocalContextEvent
    service.resolve({ ...strange, subject: { kind: 'mystery_kind', id: 'x', workstreamID: null } })
    expect(service.resolve(strange).subject).toBeNull()
  })

  it('binds the recent learnable context within 90 seconds and consumes it', () => {
    service.resolve(windowEvent())
    nowMs += 30_000
    expect(service.bindRecentContext({ kind: 'candidate', id: 'c-1', workstreamID: null })).toBe(
      true
    )
    // Consumed: a second bind has nothing to attach to.
    expect(service.bindRecentContext({ kind: 'candidate', id: 'c-2', workstreamID: null })).toBe(
      false
    )
  })

  it('refuses binds past the window or across a session epoch change', () => {
    service.resolve(windowEvent())
    nowMs += 91_000
    expect(service.bindRecentContext({ kind: 'candidate', id: 'c-1', workstreamID: null })).toBe(
      false
    )

    service.resolve(windowEvent())
    epoch = 2
    expect(service.bindRecentContext({ kind: 'candidate', id: 'c-1', workstreamID: null })).toBe(
      false
    )
  })

  it('meeting events are not learnable as recent context', () => {
    const meeting = normalizedEvent({
      kind: 'meeting',
      rawReference: 'meeting-active',
      occurredAt: nowMs
    })
    service.resolve(meeting as TaskLocalContextEvent)
    expect(service.bindRecentContext({ kind: 'task', id: 't', workstreamID: null })).toBe(false)
  })
})
