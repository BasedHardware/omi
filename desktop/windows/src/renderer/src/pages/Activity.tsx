// Activity: one reverse-chronological stream of everything Omi kept, grouped by
// day, with an hour rail beside each day.
//
// Windows had four separate lists (Conversations, Memories, Tasks, Rewind) and
// no way to see a day. This is the same records composed into one timeline, so
// "what happened on Tuesday" is one screen rather than four cross-referenced
// ones.
//
// Ported from macOS MainWindow/Spine. The composition rules live in
// lib/spine/spineModel.ts; this file is presentation over their output.

import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ChevronDown, GanttChartSquare } from 'lucide-react'
import { PageHeader } from '../components/layout/PageHeader'
import { EmptyState } from '../components/ui/EmptyState'
import { SpineHourRail } from '../components/spine/SpineHourRail'
import { SpineRowView } from '../components/spine/SpineRow'
import { useSpine } from '../hooks/useSpine'
import { countRows, localHour, startOfLocalDay, type SpineKind } from '../lib/spine/spineModel'
import { omiApi } from '../lib/apiClient'
import { toast } from '../lib/toast'

const CHIPS: Array<{ id: SpineKind | null; label: string }> = [
  { id: null, label: 'All' },
  { id: 'conversations', label: 'Conversations' },
  { id: 'memories', label: 'Memories' },
  { id: 'tasks', label: 'Tasks' },
  { id: 'screen', label: 'Screen' }
]

const EMPTY_DETAIL: Record<string, string> = {
  all: 'Conversations, memories, tasks and screen moments appear here as they happen.',
  conversations: 'Conversations appear here once Omi has heard one.',
  memories: 'Memories appear here as Omi learns things worth keeping.',
  tasks: 'Tasks you add or Omi extracts appear here.',
  screen: 'Screen moments appear here while screen capture is on.'
}

export function Activity(): React.JSX.Element {
  const navigate = useNavigate()
  const spine = useSpine()
  // Read once, at mount. `now` is impure, so it is pinned in state rather than
  // recomputed on every render - which also keeps the "current hour" marker from
  // jittering while the list is being scrolled.
  const [now] = useState(() => Date.now())
  const today = useMemo(() => startOfLocalDay(now), [now])
  const currentHour = useMemo(() => localHour(now), [now])
  const matches = useMemo(() => countRows(spine.days), [spine.days])

  const toggleStar = async (id: string, starred: boolean): Promise<void> => {
    try {
      await omiApi.patch(`/v1/conversations/${id}/starred`, null, { params: { value: !starred } })
      spine.reload()
    } catch {
      toast('Could not update that conversation.', { tone: 'warn' })
    }
  }

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="Activity"
        subtitle="Everything Omi kept, in the order it happened"
        actions={
          spine.query.length > 0 || spine.kind !== null ? (
            <span className="text-xs text-white/40">
              {matches === 1 ? '1 result' : `${matches.toLocaleString()} results`}
            </span>
          ) : undefined
        }
      />

      <div className="flex items-center gap-1.5 px-6 pb-1">
        {CHIPS.map((chip) => {
          const active = spine.kind === chip.id
          return (
            <button
              key={chip.label}
              type="button"
              onClick={() => spine.setKind(chip.id)}
              aria-pressed={active}
              className={`rounded-full px-3 py-1 text-xs ${
                active ? 'bg-white/15 text-white/90' : 'text-white/45 hover:bg-white/[0.06]'
              }`}
            >
              {chip.label}
            </button>
          )
        })}
      </div>

      {spine.degraded && (
        <p className="px-6 pt-2 text-xs text-amber-300/80">
          Some of your history could not be loaded, so this day may be incomplete.
        </p>
      )}

      <div className="min-h-0 flex-1 overflow-y-auto px-3 pt-3">
        {spine.loading && spine.days.length === 0 && (
          <p className="px-6 text-sm text-white/40">Reading your day…</p>
        )}

        {!spine.loading && spine.days.length === 0 && (
          <EmptyState
            icon={GanttChartSquare}
            title="Nothing here yet"
            description={EMPTY_DETAIL[spine.kind ?? 'all']}
          />
        )}

        {spine.days.map((day) => {
          const isFolded = spine.folded.has(day.id)
          return (
            <section key={day.id} className="mb-2">
              <button
                type="button"
                onClick={() => spine.toggleFold(day.id)}
                aria-expanded={!isFolded}
                aria-label={`${isFolded ? 'Expand' : 'Collapse'} ${day.title}`}
                className="sticky top-0 z-10 flex w-full items-center gap-2 rounded-lg border border-white/10 bg-neutral-900/80 px-3 py-2 text-left backdrop-blur"
              >
                <ChevronDown
                  className={`h-3.5 w-3.5 text-white/40 transition-transform ${
                    isFolded ? '-rotate-90' : ''
                  }`}
                />
                <span className="text-[11px] font-semibold uppercase tracking-wider text-white/70">
                  {day.title}
                </span>
                <span className="text-[11px] text-white/30">
                  {day.rows.length === 1 ? '1 entry' : `${day.rows.length} entries`}
                </span>
              </button>

              {!isFolded && (
                <div className="flex gap-2 pb-4">
                  <div className="min-w-0 flex-1">
                    {day.rows.map((row) => (
                      <SpineRowView
                        key={row.id}
                        row={row}
                        showIndent={spine.kind === null}
                        onOpenConversation={(id) => navigate(`/conversations/${id}`)}
                        onToggleStar={(id, starred) => void toggleStar(id, starred)}
                        onOpenKind={() => navigate('/knowledge-graph')}
                      />
                    ))}
                  </div>
                  <SpineHourRail
                    hourCounts={day.hourCounts}
                    momentCount={day.momentCount}
                    dayTitle={day.title}
                    conversationCount={day.conversationCount}
                    currentHour={day.id === today ? currentHour : null}
                  />
                </div>
              )}
            </section>
          )
        })}
      </div>
    </div>
  )
}
