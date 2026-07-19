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

  useEffect(() => {
    let cancelled = false

    // List poll → merge + lifecycle. mergeProjectedPills keeps pills absent from
    // the rows; expire/trim are the only removers.
    const runListPoll = async (): Promise<void> => {
      const rows = await callList()
      if (cancelled || rows === null) return
      setPills((prev) => {
        const now = Date.now()
        const merged = mergeProjectedPills(prev, rows, now).pills
        const expired = expireViewedFinished(
          merged,
          now,
          VIEWED_FINISHED_TTL_MS,
          activePillIdRef.current
        )
        const trimmed = trimForSoftCap(expired, activePillIdRef.current)
        return samePills(prev, trimmed) ? prev : trimmed
      })
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
          if (row) {
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
