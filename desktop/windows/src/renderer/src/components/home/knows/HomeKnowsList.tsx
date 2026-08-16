import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AlertTriangle } from 'lucide-react'
import { useDashboardIntelligence } from '../../../hooks/useDashboardIntelligence'
import { dashboardIntelligence } from '../../../lib/intelligence/dashboardStore'
import {
  canRotateKnows,
  composeKnowsRows,
  knowsActionTip,
  type KnowsRow
} from '../../../lib/intelligence/knowsComposer'
import type { FeedbackReason } from '../../../lib/intelligence/wireTypes'
import { fetchAllActionItems } from '../../../lib/actionItems'
import { useHomeSuggestions } from '../../../hooks/useHomeSuggestions'
import { reportHubKnowsPresence, type HubKnowsProps } from '../hub/hubKnowsSlot'
import { HomeKnowsRow } from './HomeKnowsRow'

// The Home knows list (mac parity: DashboardPage's home-knows-list). Composes
// at most four diverse rows from open tasks, What Matters Now recommendations
// stacked ahead of learned insights, the action tip, and suggested questions.
// One 7s timer advances every source's rotation together, pausing while a chat
// send is in flight. Task dismissals are session-only (mac parity: an @State
// set, never persisted, never sent to the server); insight-row dismiss/later go
// through the intelligence store's durable feedback loop.

const ROTATE_MS = 7000
const INSIGHT_HISTORY_LIMIT = 12

type LocalInsight = { id: string; headline: string; dismissed: boolean }

export function HomeKnowsList({
  onAskPrefill,
  chatSending,
  variant = 'stage'
}: HubKnowsProps): React.JSX.Element | null {
  const navigate = useNavigate()
  const intelligence = useDashboardIntelligence()
  const suggestions = useHomeSuggestions()
  const [tasks, setTasks] = useState<{ id: string; text: string }[]>([])
  const [insightHistory, setInsightHistory] = useState<{ id: string; text: string }[]>([])
  const [dismissedTaskIds, setDismissedTaskIds] = useState<ReadonlySet<string>>(new Set())
  const [rotation, setRotation] = useState(0)
  const [openTaskCount, setOpenTaskCount] = useState(0)

  // State lands only in promise continuations (the repo's HomeGoalsChips
  // idiom), so the effect body itself never sets state synchronously.
  useEffect(() => {
    const read = (): void => {
      fetchAllActionItems()
        .then((items) => {
          const open = items.filter((t) => !t.completed)
          setOpenTaskCount(open.length)
          // Due-dated work first (soonest due leads), then the freshest
          // captures — the same emphasis as mac's overdue + today + recent
          // concatenation.
          open.sort((a, b) => {
            const ad = a.dueAt ?? Number.POSITIVE_INFINITY
            const bd = b.dueAt ?? Number.POSITIVE_INFINITY
            if (ad !== bd) return ad - bd
            return b.createdAt - a.createdAt
          })
          setTasks(open.map((t) => ({ id: String(t.id), text: t.description })))
        })
        .catch(() => setTasks([]))
      ;(window.omi.insightRecent(100) as unknown as Promise<LocalInsight[]>)
        .then((recent) => {
          setInsightHistory(
            recent
              .filter((i) => !i.dismissed)
              .slice(0, INSIGHT_HISTORY_LIMIT)
              .map((i) => ({ id: i.id, text: i.headline }))
          )
        })
        .catch(() => setInsightHistory([]))
    }
    read()
    window.addEventListener('focus', read)
    return () => window.removeEventListener('focus', read)
  }, [])

  // Recommendations lead the insight slot; learned insights follow (mac
  // parity: homeKnowsInsightCandidates). Both share the 'insight' row kind and
  // are told apart at action time by looking the id up in the store.
  const insightCandidates = useMemo(
    () => [
      ...intelligence.recommendations.map((r) => ({ id: r.id, text: r.headline })),
      ...insightHistory
    ],
    [intelligence.recommendations, insightHistory]
  )

  const tip = knowsActionTip(openTaskCount)
  const rows = useMemo(
    () =>
      composeKnowsRows({
        tasks,
        insights: insightCandidates,
        tip,
        questions: suggestions,
        dismissedTaskIds,
        rotation
      }),
    [tasks, insightCandidates, tip, suggestions, dismissedTaskIds, rotation]
  )

  const rotatable = canRotateKnows(
    tasks.filter((t) => !dismissedTaskIds.has(t.id)).length,
    insightCandidates.length,
    suggestions.length
  )

  useEffect(() => {
    if (!rotatable || chatSending) return
    const timer = window.setInterval(() => setRotation((r) => r + 1), ROTATE_MS)
    return () => window.clearInterval(timer)
  }, [rotatable, chatSending])

  const rolling = variant === 'rolling'
  const visibleRows = rolling ? rows.slice(0, 3) : rows
  const hasContent =
    (rolling ? visibleRows.length > 0 : rows.length > 0) ||
    (!rolling && intelligence.error !== null)
  useEffect(() => {
    if (rolling) return
    reportHubKnowsPresence(hasContent)
    return () => reportHubKnowsPresence(false)
  }, [rolling, hasContent])

  const openRow = useCallback(
    (row: KnowsRow): void => {
      if (row.kind === 'task') {
        navigate('/tasks')
        return
      }
      if (row.kind === 'question') {
        onAskPrefill?.(row.text)
        return
      }
      const recommendation = intelligence.recommendations.find((r) => `insight-${r.id}` === row.id)
      if (!recommendation) return // learned insights are inert here (mac parity)
      // The store owns the open flow (stale-id reload, unavailable error, and
      // do_now recorded only after a successful open — mac's ordering). All
      // destinations land on the Tasks surface for now: Windows has no
      // workstream-thread UI yet, so thread destinations open Tasks rather than
      // being dropped. Called out as a deviation in the PR body.
      void dashboardIntelligence.openRecommendation(recommendation.id, () => {
        navigate('/tasks')
        return true
      })
    },
    [navigate, onAskPrefill, intelligence.recommendations]
  )

  const dismissRow = useCallback(
    (row: KnowsRow, reason: FeedbackReason | null): void => {
      if (row.kind === 'task') {
        const id = row.id.slice('task-'.length)
        setDismissedTaskIds((prev) => new Set(prev).add(id))
        return
      }
      const recommendation = intelligence.recommendations.find((r) => `insight-${r.id}` === row.id)
      if (recommendation) void dashboardIntelligence.dismiss(recommendation, reason)
    },
    [intelligence.recommendations]
  )

  const laterRow = useCallback(
    (row: KnowsRow): void => {
      const recommendation = intelligence.recommendations.find((r) => `insight-${r.id}` === row.id)
      if (recommendation) void dashboardIntelligence.later(recommendation)
    },
    [intelligence.recommendations]
  )

  if (!hasContent) return null

  return (
    <div
      className="flex w-full flex-col gap-2"
      data-testid={rolling ? 'home-knows-rolling' : 'home-knows-list'}
    >
      {!rolling && intelligence.error !== null && (
        <div
          className="flex h-[42px] w-full items-center gap-2.5 rounded-[13px] border border-home-hairline bg-home-tile/[0.55] px-4"
          data-testid="dashboard-intelligence-error"
        >
          <AlertTriangle className="h-3 w-3 shrink-0 text-home-muted" strokeWidth={2.5} />
          <span className="min-w-0 flex-1 truncate text-[12px] text-home-secondary">
            {intelligence.error}
          </span>
          <button
            type="button"
            onClick={() => void dashboardIntelligence.load()}
            className="focus-ring shrink-0 rounded px-2 py-1 text-[12px] font-medium text-home-secondary hover:text-home-ink"
          >
            Retry
          </button>
        </div>
      )}
      {visibleRows.map((row) => {
        const isRecommendation =
          row.kind === 'insight' &&
          intelligence.recommendations.some((r) => `insight-${r.id}` === row.id)
        return (
          <HomeKnowsRow
            key={row.id}
            row={row}
            onOpen={() => openRow(row)}
            onDismiss={
              row.kind === 'question'
                ? undefined
                : (reason) => dismissRow(row, row.kind === 'insight' ? reason : null)
            }
            onLater={isRecommendation ? () => laterRow(row) : undefined}
          />
        )
      })}
    </div>
  )
}
