import { useDashboardIntelligence } from '../../../hooks/useDashboardIntelligence'

// The goal detail sheet (mac parity: CanonicalGoalDetailSheet): why it matters,
// success criteria, metric progress, active work threads, and meaningful
// progress events, with the work-with-Omi primary action. The store loads the
// detail projection when the sheet opens; a load failure closes back to the
// goal-unavailable error rather than substituting a stale record.

export function GoalDetailSheet({
  goalId,
  onClose,
  onWorkOnGoal
}: {
  goalId: string
  onClose: () => void
  onWorkOnGoal: () => void
}): React.JSX.Element {
  const intelligence = useDashboardIntelligence()
  const detail = intelligence.selectedGoalDetail
  const matches = detail !== null && detail.goal.goalId === goalId

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" role="dialog">
      <div className="flex max-h-[600px] w-[620px] flex-col rounded-xl border border-home-hairline bg-home-tile p-5 shadow-2xl">
        {!matches ? (
          <p className="py-10 text-center text-[12px] text-home-muted">
            {intelligence.error ?? 'Loading goal…'}
          </p>
        ) : (
          <>
            <h2 className="mb-1 text-[18px] font-semibold text-home-ink">{detail.goal.title}</h2>
            {detail.goal.desiredOutcome && (
              <p className="mb-3 text-[12px] text-home-secondary">{detail.goal.desiredOutcome}</p>
            )}
            <div className="min-h-0 flex-1 overflow-y-auto">
              {detail.goal.whyItMatters && (
                <Section title="Why it matters">
                  <p className="text-[12px] text-home-secondary">{detail.goal.whyItMatters}</p>
                </Section>
              )}
              {detail.goal.successCriteria.length > 0 && (
                <Section title="Success looks like">
                  <p className="text-[12px] text-home-secondary">
                    {detail.goal.successCriteria.join(' • ')}
                  </p>
                </Section>
              )}
              {detail.goal.currentValue !== null && detail.goal.targetValue !== null && (
                <Section title="Progress">
                  <p className="text-[12px] text-home-secondary">
                    {detail.goal.currentValue} / {detail.goal.targetValue} {detail.goal.unit ?? ''}
                  </p>
                </Section>
              )}
              {detail.activeThreads.length > 0 && (
                <Section title="Active work">
                  <ul className="flex flex-col gap-1">
                    {detail.activeThreads.map((thread) => (
                      <li
                        key={thread.workstreamId}
                        className="flex items-center gap-2 text-[12px] text-home-secondary"
                      >
                        <span className="min-w-0 flex-1 truncate">{thread.summary}</span>
                        <button
                          type="button"
                          onClick={onWorkOnGoal}
                          className="focus-ring shrink-0 text-[11px] font-medium text-home-muted hover:text-home-ink"
                        >
                          Continue
                        </button>
                      </li>
                    ))}
                  </ul>
                </Section>
              )}
              {detail.progressEvents.length > 0 && (
                <Section title="Meaningful progress">
                  <ul className="list-disc pl-4">
                    {detail.progressEvents.map((event, i) => (
                      <li key={i} className="text-[12px] text-home-secondary">
                        {event.summary}
                      </li>
                    ))}
                  </ul>
                </Section>
              )}
            </div>
            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                onClick={onWorkOnGoal}
                data-testid={`goal-work-with-omi-${detail.goal.goalId}`}
                className="focus-ring rounded-md bg-home-tileHover px-3 py-1.5 text-[12px] font-semibold text-home-ink"
              >
                Work on this with Omi
              </button>
              <button
                type="button"
                onClick={onClose}
                className="focus-ring rounded-md border border-home-hairline px-3 py-1.5 text-[12px] font-medium text-home-secondary"
              >
                Done
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

function Section({
  title,
  children
}: {
  title: string
  children: React.ReactNode
}): React.JSX.Element {
  return (
    <div className="mb-3">
      <h3 className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-home-muted">
        {title}
      </h3>
      {children}
    </div>
  )
}
