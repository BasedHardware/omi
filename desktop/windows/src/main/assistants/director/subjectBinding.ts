/**
 * Subject binding service — Windows port of macOS ContextSubjectBindingService:
 * the database-backed hash->subject matcher shared by the buckets-ON and
 * buckets-OFF paths. Learns person/app_window/document context as "recent",
 * binds it to a subject when the user opens a recommendation within 90
 * seconds, and attaches stored subjects to events on resolve.
 */

import type { ContextBucketDb } from '../../ipc/contextBucketStore'
import { lookupBindingOn, upsertExplicitBindingOn } from '../../ipc/contextBucketStore'
import type { TaskContextSubject, TaskLocalContextEvent } from './tcrs'

export const BIND_RECENT_CONTEXT_WINDOW_MS = 90 * 1000

const LEARNABLE_KINDS = new Set(['person', 'app_window', 'document'])

/** Subject kinds the wire understands; anything else never attaches. */
const KNOWN_SUBJECT_KINDS = new Set([
  'candidate',
  'task',
  'workstream',
  'artifact',
  'decision',
  'agent_open_loop'
])

export interface SubjectBindingDeps {
  db(): ContextBucketDb
  sessionEpoch(): number
  now(): number
}

export class ContextSubjectBindingService {
  private readonly deps: SubjectBindingDeps
  private recent: { referenceHash: string; occurredAt: number; epoch: number } | null = null

  constructor(deps: SubjectBindingDeps) {
    this.deps = deps
  }

  /** Resolve an event: remember learnable kinds as recent context; upsert
   *  subject-carrying events as explicit bindings; else attach a stored,
   *  fresh (30-day) binding when its kind is known. */
  resolve(event: TaskLocalContextEvent): TaskLocalContextEvent {
    if (LEARNABLE_KINDS.has(event.kind)) {
      this.recent = {
        referenceHash: event.referenceHash,
        occurredAt: event.occurredAt,
        epoch: this.deps.sessionEpoch()
      }
    }
    if (event.subject !== null) {
      upsertExplicitBindingOn(
        this.deps.db(),
        {
          referenceHash: event.referenceHash,
          subjectKind: event.subject.kind,
          subjectID: event.subject.id,
          workstreamID: event.subject.workstreamID
        },
        this.deps.now()
      )
      return event
    }
    const stored = lookupBindingOn(this.deps.db(), event.referenceHash, this.deps.now())
    if (stored === null || !KNOWN_SUBJECT_KINDS.has(stored.subjectKind)) return event
    return {
      ...event,
      subject: { kind: stored.subjectKind, id: stored.subjectID, workstreamID: stored.workstreamID }
    }
  }

  /** Bind the most recent learnable context to an explicitly chosen subject —
   *  only within 90 seconds and under the same session epoch; the remembered
   *  context is consumed either way. */
  bindRecentContext(subject: TaskContextSubject): boolean {
    const recent = this.recent
    this.recent = null
    if (recent === null) return false
    if (this.deps.now() - recent.occurredAt > BIND_RECENT_CONTEXT_WINDOW_MS) return false
    if (recent.epoch !== this.deps.sessionEpoch()) return false
    return upsertExplicitBindingOn(
      this.deps.db(),
      {
        referenceHash: recent.referenceHash,
        subjectKind: subject.kind,
        subjectID: subject.id,
        workstreamID: subject.workstreamID
      },
      this.deps.now()
    )
  }

  reset(): void {
    this.recent = null
  }
}
