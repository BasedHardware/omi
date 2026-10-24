import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useDashboardIntelligence } from '../../../hooks/useDashboardIntelligence'
import { dashboardIntelligence, focusedGoals } from '../../../lib/intelligence/dashboardStore'
import type { HubHomeWidgetsProps } from '../hub/hubHomeWidgetsSlot'
import { HomeGoalsChips } from '../HomeGoalsChips'
import { AllGoalsSheet } from './AllGoalsSheet'
import { GoalCreateSheet } from './GoalCreateSheet'
import { GoalDetailSheet } from './GoalDetailSheet'

// The resting Hub's goals row, upgraded to the canonical model (mac parity:
// FocusedGoalsSection). When the account is inside the intelligence rollout
// (accountGeneration bound), the row shows the true FOCUSED subset with the
// All-goals sheet, create sheet, and detail sheet behind it — closing the
// deviation HomeGoalsChips documented ("Windows has no focused subset"). When
// the account is outside the rollout, the legacy active-goals chip row renders
// unchanged, so nothing regresses for accounts the canonical system has not
// reached.

export function CanonicalGoalsChips(props: HubHomeWidgetsProps): React.JSX.Element {
  const intelligence = useDashboardIntelligence()
  const navigate = useNavigate()
  const [showAllGoals, setShowAllGoals] = useState(false)
  const [showCreate, setShowCreate] = useState(false)
  const [detailGoalId, setDetailGoalId] = useState<string | null>(null)

  if (!intelligence.hasLoadedOnce) {
    // Cold start: the gate is unknown. Render nothing (mac renders nothing for
    // an unbound generation) instead of flashing the legacy row at canonical
    // accounts or firing the legacy fetch before the control answers.
    return <></>
  }
  if (intelligence.accountGeneration === null) {
    return <HomeGoalsChips {...props} />
  }

  const focused = focusedGoals(intelligence.goals).slice(0, 5)

  const openDetail = (goalId: string): void => {
    setDetailGoalId(goalId)
    void dashboardIntelligence.loadGoalDetail(goalId)
  }

  return (
    <>
      <div
        className="flex h-[30px] w-full items-center gap-2 overflow-hidden"
        data-testid="focused-goals"
      >
        {focused.length > 0 ? (
          <>
            <span className="shrink-0 text-[11px] font-semibold text-home-muted">
              Focused goals
            </span>
            {focused.map((goal) => (
              <button
                key={goal.goalId}
                type="button"
                data-testid={`focused-goal-${goal.goalId}`}
                onClick={() =>
                  props.onOpenGoal ? props.onOpenGoal(goal.goalId) : openDetail(goal.goalId)
                }
                className="focus-ring min-w-0 shrink truncate rounded-full bg-home-tile/[0.8] px-[9px] py-[6px] text-[10px] font-medium text-home-secondary hover:text-home-ink"
              >
                {goal.title}
              </button>
            ))}
            <button
              type="button"
              onClick={() => (props.onShowAll ? props.onShowAll() : setShowAllGoals(true))}
              className="focus-ring ml-auto shrink-0 text-[11px] font-medium text-home-muted hover:text-home-secondary"
            >
              All goals
            </button>
          </>
        ) : (
          <>
            <span className="shrink-0 text-[11px] font-semibold text-home-muted">
              No focused goals
            </span>
            <button
              type="button"
              onClick={() => {
                if (intelligence.goals.length === 0) setShowCreate(true)
                else if (props.onShowAll) props.onShowAll()
                else setShowAllGoals(true)
              }}
              className="focus-ring shrink-0 text-[11px] font-medium text-home-secondary hover:text-home-ink"
            >
              {intelligence.goals.length === 0 ? 'Add goal' : 'Choose focus'}
            </button>
          </>
        )}
      </div>

      {showAllGoals && (
        <AllGoalsSheet
          onClose={() => setShowAllGoals(false)}
          onAddGoal={() => {
            setShowAllGoals(false)
            setShowCreate(true)
          }}
          onOpenGoal={(goalId) => {
            setShowAllGoals(false)
            openDetail(goalId)
          }}
        />
      )}
      {showCreate && <GoalCreateSheet onClose={() => setShowCreate(false)} />}
      {detailGoalId !== null && (
        <GoalDetailSheet
          goalId={detailGoalId}
          onClose={() => {
            setDetailGoalId(null)
            dashboardIntelligence.clearGoalDetail()
          }}
          onWorkOnGoal={() => {
            // Mac starts an agent thread on the goal; Windows has no
            // workstream-thread UI yet, so working a goal lands on the Tasks
            // surface. Called out as a deviation in the PR body.
            setDetailGoalId(null)
            dashboardIntelligence.clearGoalDetail()
            navigate('/tasks')
          }}
        />
      )}
    </>
  )
}
