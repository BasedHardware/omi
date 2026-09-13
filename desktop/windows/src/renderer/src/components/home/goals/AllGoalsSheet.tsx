import { useEffect, useState } from 'react'
import { X } from 'lucide-react'
import { cn } from '../../../lib/utils'
import { useDashboardIntelligence } from '../../../hooks/useDashboardIntelligence'
import {
  dashboardIntelligence,
  currentGoals,
  endedGoals,
  focusedGoals
} from '../../../lib/intelligence/dashboardStore'
import type { CanonicalGoal, GoalLifecycleTarget } from '../../../lib/intelligence/wireTypes'
import { ModalShell } from '../../conversations/ModalShell'

// The All-goals sheet (mac parity: AllGoalsSheet, WhatMattersNowSection.swift).
// Current/History segmented views, per-row Open / Focus-Unfocus / lifecycle
// menu, and the focus-replacement flow: when focusing 409s because the focus
// set is full, the store surfaces focusReplacementGoalId and this sheet asks
// which focused goal to swap out. Nothing is archived by a replacement; the
// replaced goal simply returns to All goals.

export function AllGoalsSheet({
  onClose,
  onAddGoal,
  onOpenGoal
}: {
  onClose: () => void
  onAddGoal: () => void
  onOpenGoal: (goalId: string) => void
}): React.JSX.Element {
  const intelligence = useDashboardIntelligence()
  const [showHistory, setShowHistory] = useState(false)
  const [menuGoalId, setMenuGoalId] = useState<string | null>(null)
  const [replacementFor, setReplacementFor] = useState<string | null>(null)
  const [replacementChoice, setReplacementChoice] = useState<string | null>(null)

  const focused = focusedGoals(intelligence.goals)
  const listed = showHistory ? endedGoals(intelligence.goals) : currentGoals(intelligence.goals)

  const focusGoal = async (goal: CanonicalGoal): Promise<void> => {
    const ok = await dashboardIntelligence.focus(goal.goalId, null)
    if (!ok && dashboardIntelligence.getState().focusReplacementGoalId === goal.goalId) {
      setReplacementFor(goal.goalId)
      setReplacementChoice(focused[0]?.goalId ?? null)
    }
  }

  const confirmReplacement = async (): Promise<void> => {
    if (replacementFor === null || replacementChoice === null) return
    const ok = await dashboardIntelligence.focus(replacementFor, replacementChoice)
    // A failed replacement keeps the dialog open for a retry; the store's
    // error line explains what happened.
    if (!ok) return
    setReplacementFor(null)
    setReplacementChoice(null)
  }

  const cancelReplacement = (): void => {
    // Local dismissal must also clear the store's replacement request, or the
    // Goals page's dialog (driven by the same store field) reopens the flow.
    dashboardIntelligence.clearFocusReplacement()
    setReplacementFor(null)
    setReplacementChoice(null)
  }

  // While the nested replacement dialog is open, Escape must close IT and not
  // the whole sheet: a capture-phase listener with stopImmediatePropagation
  // pre-empts the outer ModalShell's window keydown.
  useEffect(() => {
    if (replacementFor === null) return
    const onKey = (e: KeyboardEvent): void => {
      if (e.key !== 'Escape') return
      e.stopImmediatePropagation()
      cancelReplacement()
    }
    window.addEventListener('keydown', onKey, true)
    return () => window.removeEventListener('keydown', onKey, true)
  })

  const transition = async (goal: CanonicalGoal, status: GoalLifecycleTarget): Promise<void> => {
    setMenuGoalId(null)
    await dashboardIntelligence.transition(goal.goalId, status)
  }

  return (
    <ModalShell onClose={onClose} maxWidth="max-w-[620px]" labelledBy="all-goals-title">
      <div className="flex max-h-[500px] flex-col">
        <div className="mb-4 flex items-center gap-3">
          <h2 id="all-goals-title" className="text-[20px] font-semibold text-home-ink">
            All goals
          </h2>
          <div className="ml-2 flex rounded-md border border-home-hairline p-0.5" role="tablist">
            {[
              { label: 'Current', value: false },
              { label: 'History', value: true }
            ].map(({ label, value }) => (
              <button
                key={label}
                type="button"
                role="tab"
                aria-selected={showHistory === value}
                onClick={() => setShowHistory(value)}
                className={cn(
                  'focus-ring rounded px-3 py-1 text-[12px] font-medium',
                  showHistory === value
                    ? 'bg-home-tileHover text-home-ink'
                    : 'text-home-muted hover:text-home-secondary'
                )}
              >
                {label}
              </button>
            ))}
          </div>
          <div className="ml-auto flex items-center gap-2">
            <button
              type="button"
              onClick={onAddGoal}
              className="focus-ring rounded-md border border-home-hairline px-3 py-1.5 text-[12px] font-medium text-home-secondary hover:text-home-ink"
            >
              Add goal
            </button>
            <button
              type="button"
              onClick={onClose}
              className="focus-ring rounded-md bg-home-tileHover px-3 py-1.5 text-[12px] font-semibold text-home-ink"
            >
              Done
            </button>
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto">
          {listed.length === 0 ? (
            <p className="py-8 text-center text-[12px] text-home-muted">
              {showHistory ? 'No ended goals yet.' : 'No goals yet.'}
            </p>
          ) : (
            <ul className="flex flex-col gap-1">
              {listed.map((goal) => (
                <li
                  key={goal.goalId}
                  className="flex items-center gap-3 rounded-lg px-3 py-2 hover:bg-home-tileHover"
                  data-testid={`all-goals-row-${goal.goalId}`}
                >
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-[13px] font-semibold text-home-ink">{goal.title}</p>
                    {goal.desiredOutcome && (
                      <p className="truncate text-[10px] text-home-muted">{goal.desiredOutcome}</p>
                    )}
                  </div>
                  <span className="shrink-0 text-[9px] uppercase tracking-wide text-home-faint">
                    {goal.status === '_unknown' ? '' : goal.status}
                  </span>
                  <button
                    type="button"
                    onClick={() => onOpenGoal(goal.goalId)}
                    className="focus-ring shrink-0 text-[12px] font-medium text-home-secondary hover:text-home-ink"
                  >
                    Open
                  </button>
                  {!showHistory && (
                    <>
                      <button
                        type="button"
                        onClick={() =>
                          goal.status === 'focused'
                            ? void dashboardIntelligence.unfocus(goal.goalId)
                            : void focusGoal(goal)
                        }
                        className="focus-ring shrink-0 text-[12px] font-medium text-home-secondary hover:text-home-ink"
                      >
                        {goal.status === 'focused' ? 'Unfocus' : 'Focus'}
                      </button>
                      <div className="relative shrink-0">
                        <button
                          type="button"
                          onClick={() =>
                            setMenuGoalId(menuGoalId === goal.goalId ? null : goal.goalId)
                          }
                          className="focus-ring w-[55px] text-[12px] font-medium text-home-muted hover:text-home-secondary"
                        >
                          More
                        </button>
                        {menuGoalId === goal.goalId && (
                          <div className="absolute right-0 top-6 z-10 w-[150px] rounded-md border border-home-hairline bg-home-tile p-1 shadow-lg">
                            <MenuButton
                              label="Pause"
                              onClick={() => void transition(goal, 'paused')}
                            />
                            <MenuButton
                              label="Mark achieved"
                              onClick={() => void transition(goal, 'achieved')}
                            />
                            <MenuButton
                              label="Abandon"
                              onClick={() => void transition(goal, 'abandoned')}
                            />
                          </div>
                        )}
                      </div>
                    </>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>

        {intelligence.error !== null && (
          <p className="mt-2 text-[10px] text-home-muted">{intelligence.error}</p>
        )}
      </div>

      {replacementFor !== null && (
        <div
          className="fixed inset-0 z-[130] flex items-center justify-center bg-black/40"
          role="dialog"
          aria-modal="true"
          aria-label="Replace a focused goal"
        >
          <div className="w-[380px] rounded-xl border border-home-hairline bg-home-tile p-5 shadow-2xl">
            <div className="mb-2 flex items-start justify-between">
              <h3 className="text-[15px] font-semibold text-home-ink">Replace a focused goal</h3>
              <button
                type="button"
                aria-label="Close"
                onClick={cancelReplacement}
                className="focus-ring rounded p-1 text-home-faint hover:text-home-secondary"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
            <p className="mb-3 text-[12px] text-home-secondary">
              Your focus set is full. Nothing is archived; the replaced goal moves to All goals.
            </p>
            <label className="mb-3 block">
              <span className="mb-1 block text-[11px] font-medium text-home-muted">Replace</span>
              <select
                value={replacementChoice ?? ''}
                onChange={(e) => setReplacementChoice(e.target.value || null)}
                className="w-full rounded-md border border-home-hairline bg-home-tile px-2 py-1.5 text-[12px] text-home-ink"
              >
                {focused.map((goal) => (
                  <option key={goal.goalId} value={goal.goalId}>
                    {goal.title}
                  </option>
                ))}
              </select>
            </label>
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={cancelReplacement}
                className="focus-ring rounded-md border border-home-hairline px-3 py-1.5 text-[12px] font-medium text-home-secondary"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => void confirmReplacement()}
                className="focus-ring rounded-md bg-home-tileHover px-3 py-1.5 text-[12px] font-semibold text-home-ink"
              >
                Replace focus
              </button>
            </div>
          </div>
        </div>
      )}
    </ModalShell>
  )
}

function MenuButton({ label, onClick }: { label: string; onClick: () => void }): React.JSX.Element {
  return (
    <button
      type="button"
      onClick={onClick}
      className="focus-ring block w-full rounded px-2 py-1.5 text-left text-[12px] text-home-secondary hover:bg-home-tileHover hover:text-home-ink"
    >
      {label}
    </button>
  )
}
