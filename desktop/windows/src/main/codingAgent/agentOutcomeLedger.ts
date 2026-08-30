// Small main-process record of how each coding agent has actually done, kept
// so agentConcierge.ts can rank the unnamed fallback order by more than a
// hardcoded list. Same JSON-in-userData shape as appSettings.ts — this is
// deliberately not a database or an analytics pipeline, just a short recent
// history that answers one question: "the last few times we handed this kind
// of task to this agent, did it work?"
//
// Per-machine, not per-account — it lives next to the launch commands the
// user configured on this box, so it only ever reflects agents that were
// actually runnable here. A fresh install (or a wiped userData dir) starts
// with an empty ledger, which reads as "no opinion yet", not as a penalty.

import { app } from 'electron'
import { join } from 'path'
import { readFileSync, writeFileSync } from 'fs'
import type { CodingAgentAdapterId } from './interface'

/** Coarse shape of the delegated task, guessed from the prompt text. Coarser
 *  than it sounds — this only has to separate "this benefits from resuming
 *  after a restart" from "this is a quick one-shot", not understand the task. */
export type TaskTag = 'long_running' | 'bulk_refactor' | 'research' | 'quick_script' | 'general'

export type AgentOutcome = 'success' | 'failure'

export type AgentOutcomeEntry = {
  adapterId: CodingAgentAdapterId
  tag: TaskTag
  outcome: AgentOutcome
  /** Epoch ms. */
  ts: number
}

type LedgerFile = { entries: AgentOutcomeEntry[] }

// Two independent caps, for two independent reasons:
//  - MAX_ENTRIES bounds the file on disk (a chatty user delegating agent tasks
//    all day must never grow this file without limit).
//  - the per-(adapter, tag) recency window used at read time (see
//    agentConcierge.ts's RECENCY_WINDOW) bounds how far back a ranking
//    decision looks, so an agent's one bad afternoon a month ago doesn't
//    permanently outweigh three good runs since.
const MAX_ENTRIES = 500

const TASK_TAGS: readonly TaskTag[] = [
  'long_running',
  'bulk_refactor',
  'research',
  'quick_script',
  'general'
]

function isTaskTag(value: unknown): value is TaskTag {
  return typeof value === 'string' && (TASK_TAGS as readonly string[]).includes(value)
}

function isAdapterId(value: unknown): value is CodingAgentAdapterId {
  return value === 'acp' || value === 'openclaw' || value === 'hermes' || value === 'codex'
}

// Same defensive posture as appSettings.sanitizeAppSettings: a corrupt or
// hand-edited file degrades to "no history" one bad row at a time, never a
// thrown exception that takes ranking down with it.
function sanitizeEntries(raw: unknown): AgentOutcomeEntry[] {
  if (!Array.isArray(raw)) return []
  const out: AgentOutcomeEntry[] = []
  for (const value of raw) {
    if (out.length >= MAX_ENTRIES) break
    const entry = value as Partial<AgentOutcomeEntry> | null
    const ts = typeof entry?.ts === 'number' && Number.isFinite(entry.ts) ? entry.ts : NaN
    if (
      isAdapterId(entry?.adapterId) &&
      isTaskTag(entry?.tag) &&
      (entry?.outcome === 'success' || entry?.outcome === 'failure') &&
      Number.isFinite(ts)
    ) {
      out.push({ adapterId: entry.adapterId, tag: entry.tag, outcome: entry.outcome, ts })
    }
  }
  return out
}

function file(): string {
  return join(app.getPath('userData'), 'agent-outcome-ledger.json')
}

function readFromDisk(): LedgerFile {
  try {
    const parsed = JSON.parse(readFileSync(file(), 'utf-8')) as Partial<LedgerFile> | null
    return { entries: sanitizeEntries(parsed?.entries) }
  } catch {
    return { entries: [] }
  }
}

// Cached after the first read per process, same rationale as appSettings.ts:
// this is read on every delegated-task dispatch, and a task is dispatched far
// more often than the ledger changes shape underneath a running process.
let cache: LedgerFile | null = null

/** Every retained outcome, oldest first. Read-only snapshot for ranking. */
export function readOutcomeLedger(): readonly AgentOutcomeEntry[] {
  if (!cache) cache = readFromDisk()
  return cache.entries
}

/** Append one real outcome and persist it. Never throws — a failed write here
 *  must not take the coding-agent task down with it, it just means ranking
 *  stays a little more static than it could have been. */
export function recordAgentOutcome(entry: Omit<AgentOutcomeEntry, 'ts'>): void {
  const current = readOutcomeLedger()
  const next = { entries: [...current, { ...entry, ts: Date.now() }].slice(-MAX_ENTRIES) }
  cache = next
  try {
    writeFileSync(file(), JSON.stringify(next), 'utf-8')
  } catch (e) {
    console.warn('[agent-outcome-ledger] failed to persist:', e)
  }
}

/** Test-only: drop the in-memory cache so the next read comes from disk. */
export function _resetForTests(): void {
  cache = null
}
