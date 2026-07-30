import { Clock, AlertCircle, Check } from 'lucide-react'
import { BillingCard } from './BillingCard'
import { cn } from '../../../lib/utils'
import { trialCountdownText, trialProgress, trialTimeTone } from '../../../lib/billing'
import type { TrialMetadata } from '../../../lib/omiApi.generated'

const RING_STROKE: Record<'amber' | 'yellow' | 'green', string> = {
  amber: 'stroke-amber-400',
  yellow: 'stroke-yellow-300',
  green: 'stroke-emerald-400'
}

function ProgressRing(props: {
  progress: number
  tone: 'amber' | 'yellow' | 'green'
}): React.JSX.Element {
  const r = 13
  const c = 2 * Math.PI * r
  const offset = c * (1 - Math.max(0, Math.min(1, props.progress)))
  return (
    <svg width="32" height="32" viewBox="0 0 32 32" className="-rotate-90">
      <circle cx="16" cy="16" r={r} fill="none" strokeWidth="3" className="stroke-white/12" />
      <circle
        cx="16"
        cy="16"
        r={r}
        fill="none"
        strokeWidth="3"
        strokeLinecap="round"
        strokeDasharray={c}
        strokeDashoffset={offset}
        className={cn('transition-all duration-500', RING_STROKE[props.tone])}
      />
    </svg>
  )
}

const TRIAL_INCLUDED = [
  'Unlimited listening & transcription',
  'Unlimited memories & insights',
  'Chat questions'
]

/**
 * Trial card (AccountBilling): an active countdown with a progress ring, or the
 * expired variant whose "View Plans" jumps to the Operator card. Ring/clock tone
 * shifts amber ≤1h, yellow ≤24h, else green (Mac parity; no purple).
 */
export function TrialCard(props: {
  trial: TrialMetadata
  onViewPlans: () => void
}): React.JSX.Element {
  const { trial, onViewPlans } = props

  if (trial.trial_expired) {
    return (
      <BillingCard
        icon={AlertCircle}
        iconTone="amber"
        title="Trial Ended"
        subtitle="Upgrade to keep unlimited access"
        trailing={
          <button onClick={onViewPlans} className="btn-primary">
            View Plans
          </button>
        }
      />
    )
  }

  const remaining = trial.trial_remaining_seconds ?? 0
  const tone = trialTimeTone(remaining)

  return (
    <BillingCard
      icon={Clock}
      iconTone={tone}
      title="Premium Trial Active"
      subtitle={trialCountdownText(remaining)}
      trailing={<ProgressRing progress={trialProgress(trial)} tone={tone} />}
    >
      <div className="border-t border-white/[0.06] pt-3">
        <div className="mb-2 text-xs font-medium text-white/45">Included in your trial</div>
        <ul className="space-y-1.5">
          {TRIAL_INCLUDED.map((f) => (
            <li key={f} className="flex items-start gap-2 text-sm text-white/75">
              <Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-400" />
              <span>{f}</span>
            </li>
          ))}
        </ul>
      </div>
    </BillingCard>
  )
}
