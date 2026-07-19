// The bar's live floating-agent-pill feed (B3). Faithful port of macOS'
// AgentPillsManager projection + per-run polling (upstream
// FloatingControlBar/AgentPill.swift): it reads the SAME canonical source the
// LLM does — `list_agent_sessions` filtered to `surfaceKind: 'floating_bar'` —
// merges rows through the pure B2 model (agentPills.ts), polls each active run's
// `get_agent_run` to refresh status + synthesize its own transcript, and applies
// the post-completion lifecycle (viewed-TTL expiry, soft-cap eviction).
//
// Two doors, both via the trusted-direct-control channel window.omi.agentControlCall:
//   - list_agent_sessions({ surfaceKind:'floating_bar', limit:50 }) → .floating_agent_pills
//   - get_agent_run({ runId }) → { run, session }   (per active pill)
//
// Fail-open everywhere: a rejected or unparseable door call keeps the current
// pills — it never throws into render. All timers are cleared on unmount.
import { useCallback, useEffect, useRef, useState } from 'react'
import {
  expireViewedFinished,
  isFinished,
  markViewed as markViewedPure,
  mergeProjectedPills,
  trimForSoftCap,
  VIEWED_FINISHED_TTL_MS,
  type AgentPill,
  type PillProjectionRow
} from '../components/bar/agentPills'
import {
  retainTextForPills,
  runDetailFinalText,
  runDetailToProjectionRow,
  synthesizePillTranscript,
  type AgentRunDetail
} from '../components/bar/agentPillTranscript'
import type { ChatMsg } from './useChat'

// Both poll cadences mirror Mac's 2s canonical-run poll (AgentPill.swift:1775).
const LIST_POLL_MS = 2000
const RUN_POLL_MS = 2000

export type AgentPillsApi = {
  /** The live pills, projection-merged + lifecycle-trimmed. */
  pills: AgentPill[]
  /** Stamp a finished pill viewed (arms its 10-min TTL). No-op while active. */
  markViewed: (id: string) => void
  /** Manually remove a pill from the bar (Mac dismiss → cleanup). */
  dismiss: (id: string) => void
  /** The client-synthesized transcript for a pill — its OWN messages, never the
   *  shared Omi thread (INV-CHAT-1). Empty when the pill is unknown. */
  transcriptFor: (id: string) => { messages: ChatMsg[]; sending: boolean }
}

/** A cheap structural signature of the render-affecting pill fields, so a poll
 *  that changed nothing does not churn a new array into state every 2s. */
function pillSig(p: AgentPill): string {
  return [
    p.id,
    p.displayStatus,
    p.title,
    p.latestActivity,
    p.completedAtMs,
    p.viewedAtMs,
    p.errorMessage
  ].join('')
}

function samePills(a: AgentPill[], b: AgentPill[]): boolean {
  if (a === b) return true
  if (a.length !== b.length) return false
  for (let i = 0; i < a.length; i += 1) {
    if (pillSig(a[i]) !== pillSig(b[i])) return false
  }
  return true
}

async function callList(): Promise<PillProjectionRow[] | null> {
  try {
    const raw = await window.omi?.agentControlCall('list_agent_sessions', {
      surfaceKind: 'floating_bar',
      limit: 50
    })
    if (typeof raw !== 'string') return null
    const parsed = JSON.parse(raw) as { floating_agent_pills?: unknown }
    const rows = parsed.floating_agent_pills
    return Array.isArray(rows) ? (rows as PillProjectionRow[]) : null
  } catch {
    // Fail-open: a rejected/parse-failed list keeps the current pills.
    return null
  }
}

async function callRun(runId: string): Promise<AgentRunDetail | null> {
  try {
    const raw = await window.omi?.agentControlCall('get_agent_run', { runId })
    if (typeof raw !== 'string') return null
    const parsed = JSON.parse(raw) as AgentRunDetail & { ok?: boolean }
    if (parsed.ok === false) return null
    return parsed
  } catch {
    return null
  }
}

/**
 * Durably mark a pill's underlying run/session dismissed in the kernel — Mac's
 * "attention overrides" mechanism. `serializeAgentSessionsList` (controlTools.ts)
 * excludes dismissed `run:<id>` / `session:<id>` subjects from
 * `floating_agent_pills`, so once this commits the list poll never re-projects
 * the pill, and it stays gone across app restarts AND other windows (the override
 * lives in the kernel's SQLite `desktop_attention_overrides` table, a
 * main-process singleton). Without this, dismiss only mutated the renderer's
 * in-memory array and the very next 2s poll resurrected the pill.
 */
async function callDismissOverride(
  subjectKind: 'run' | 'session',
  subjectId: string
): Promise<void> {
  try {
    await window.omi?.agentControlCall('set_desktop_attention_override', {
      subjectKind,
      subjectId,
      dismissed: true
    })
  } catch {
    // Fail-open: the in-memory dismissed-set guard still hides the pill for this
    // session, and a later dismissal or poll reconciles. A failed durable write
    // only risks the pill reappearing after a restart — never a crash into render.
  }
}

// Upper bound on the in-memory dismissed-subject guard (below). It resets every
// session — the kernel override is the durable record — so this only caps a
// pathological single-session dismissal spree. Set iteration is insertion order,
// so evicting the first entry is FIFO.
const DISMISSED_GUARD_CAP = 500

function rememberDismissed(set: Set<string>, id: string): void {
  if (set.has(id)) return
  if (set.size >= DISMISSED_GUARD_CAP) {
    const oldest = set.values().next().value
    if (oldest !== undefined) set.delete(oldest)
  }
  set.add(id)
}

/** True when a freshly projected row was dismissed this session (by run or
 *  session id) before the kernel override took effect — used to drop it from an
 *  in-flight poll snapshot so a stale fetch can't re-create a just-dismissed pill. */
function isRowDismissed(dismissed: Set<string>, row: PillProjectionRow): boolean {
  return (
    (typeof row.runId === 'string' && dismissed.has(row.runId)) ||
    (typeof row.sessionId === 'string' && dismissed.has(row.sessionId))
  )
}

/**
 * @param activePillId The pill whose transcript is currently open (or null).
 *   It is protected from viewed-TTL expiry and soft-cap eviction while open.
 */
export function useAgentPills(activePillId: string | null): AgentPillsApi {
  const [pills, setPills] = useState<AgentPill[]>([])
  const [finalTextByPillId, setFinalTextByPillId] = useState<Record<string, string>>({})

  // Latest-refs so the once-registered interval closures read current values
  // without re-subscribing (which would restart the poll cadence).
  const pillsRef = useRef(pills)
  // eslint-disable-next-line react-hooks/refs -- latest-ref for interval closures
  pillsRef.current = pills
  const activePillIdRef = useRef(activePillId)
  // eslint-disable-next-line react-hooks/refs -- latest-ref for interval closures
  activePillIdRef.current = activePillId

  // Run/session ids the user dismissed this session. The kernel override
  // (callDismissOverride) is the durable, restart-proof record; this in-memory
  // set is only a race guard, consulted synchronously by the list poll so a
  // snapshot fetched BEFORE the override committed can't re-create the pill.
  const dismissedRef = useRef<Set<string>>(new Set())

  useEffect(() => {
    let cancelled = false

    // List poll → merge + lifecycle. mergeProjectedPills keeps pills absent from
    // the rows; expire/trim are the only removers.
    const runListPoll = async (): Promise<void> => {
      const rows = await callList()
      if (cancelled || rows === null) return
      // Drop rows for pills dismissed this session but not yet filtered by the
      // kernel (its override may not have committed before this snapshot was
      // fetched) — closes the in-flight-poll resurrection race.
      const visibleRows = rows.filter((row) => !isRowDismissed(dismissedRef.current, row))
      const now = Date.now()
      const merged = mergeProjectedPills(pillsRef.current, visibleRows, now).pills
      const expired = expireViewedFinished(
        merged,
        now,
        VIEWED_FINISHED_TTL_MS,
        activePillIdRef.current
      )
      const trimmed = trimForSoftCap(expired, activePillIdRef.current)
      setPills((prev) => (samePills(prev, trimmed) ? prev : trimmed))
      // Drop cached assistant text for pills the lifecycle just evicted (soft-cap /
      // viewed-TTL), so the text map can't grow unbounded across a long session.
      setFinalTextByPillId((prev) => retainTextForPills(prev, trimmed))
    }

    // Per-run poll → refresh status + transcript for each active pill with a
    // runId. A finished pill is skipped, so it is never polled again (Mac stops
    // its per-run timer at terminal); the B2 merge also guards resurrection.
    const runRunPoll = async (): Promise<void> => {
      const targets = pillsRef.current.filter((p) => !isFinished(p.displayStatus) && p.runId)
      await Promise.all(
        targets.map(async (pill) => {
          const detail = await callRun(pill.runId)
          if (cancelled || detail === null) return
          const row = runDetailToProjectionRow(pill, detail)
          // Same guard as the list poll: if this pill was dismissed while its
          // get_agent_run was in flight, don't let the refreshed row re-create it.
          if (row && !isRowDismissed(dismissedRef.current, row)) {
            setPills((prev) => {
              const next = mergeProjectedPills(prev, [row], Date.now()).pills
              return samePills(prev, next) ? prev : next
            })
          }
          const finalText = runDetailFinalText(detail)
          setFinalTextByPillId((prev) =>
            prev[pill.id] === finalText ? prev : { ...prev, [pill.id]: finalText }
          )
        })
      )
    }

    void runListPoll()
    void runRunPoll()
    const listTimer = setInterval(() => void runListPoll(), LIST_POLL_MS)
    const runTimer = setInterval(() => void runRunPoll(), RUN_POLL_MS)
    return () => {
      cancelled = true
      clearInterval(listTimer)
      clearInterval(runTimer)
    }
  }, [])

  const markViewed = useCallback((id: string): void => {
    setPills((prev) => markViewedPure(prev, id, Date.now()))
  }, [])

  const dismiss = useCallback((id: string): void => {
    // Persist the dismissal in the kernel so the list poll stops projecting this
    // pill (durable across restarts + windows), and seed the in-memory guard so
    // an already-in-flight poll can't resurrect it before that write lands. We
    // dismiss both the run and the session subject: the serializer's filter is an
    // OR over `run:<id>` / `session:<id>`, so covering both is resurrection-proof
    // even if the session's projected run changes. Dismissing the session is
    // intentionally pill-wide, not over-broad: a floating_bar session is created
    // per spawn, so it never hosts a second, unrelated pill.
    const pill = pillsRef.current.find((p) => p.id === id)
    if (pill?.runId) {
      rememberDismissed(dismissedRef.current, pill.runId)
      void callDismissOverride('run', pill.runId)
    }
    if (pill?.sessionId) {
      rememberDismissed(dismissedRef.current, pill.sessionId)
      void callDismissOverride('session', pill.sessionId)
    }
    setPills((prev) => prev.filter((p) => p.id !== id))
    setFinalTextByPillId((prev) => {
      if (!(id in prev)) return prev
      const next = { ...prev }
      delete next[id]
      return next
    })
  }, [])

  const transcriptFor = useCallback(
    (id: string): { messages: ChatMsg[]; sending: boolean } => {
      const pill = pills.find((p) => p.id === id)
      if (!pill) return { messages: [], sending: false }
      return synthesizePillTranscript(pill, finalTextByPillId[id] ?? null)
    },
    [pills, finalTextByPillId]
  )

  return { pills, markViewed, dismiss, transcriptFor }
}
