import { useState } from 'react'
import { StepScaffold } from './StepScaffold'

export type PermissionStatus = 'idle' | 'waiting' | 'granted'

type PermissionStepProps = {
  stepIndex: number
  totalSteps: number
  aside?: React.ReactNode
  eyebrow: string
  title: string
  subtitle?: string
  /** Icon shown inside the status card (e.g. a lucide glyph). */
  icon: React.ReactNode
  /** Label for the row inside the status card, e.g. "Screen Recording". */
  cardLabel: string
  statusText: Record<PermissionStatus, string>
  buttonLabel: Record<PermissionStatus, string>
  /** The grant/scan work to run on click. Resolves when access is settled. */
  onActivate: () => Promise<void>
  /** Advance to the next step. Called automatically after the granted state. */
  onContinue: () => void
  /** Skip this permission without granting it (small text button up top). */
  onSkip?: () => void
}

/**
 * Shared onboarding "permission" step: an icon status card plus an action button
 * that runs `onActivate` (waiting → granted), then auto-advances via `onContinue`
 * ~1s after access is granted. Used by the screen-recording and disk-access steps.
 */
export function PermissionStep({
  stepIndex,
  totalSteps,
  aside,
  eyebrow,
  title,
  subtitle,
  icon,
  cardLabel,
  statusText,
  buttonLabel,
  onActivate,
  onContinue,
  onSkip
}: PermissionStepProps): React.JSX.Element {
  const [status, setStatus] = useState<PermissionStatus>('idle')

  const handleActivate = async (): Promise<void> => {
    setStatus('waiting')
    try {
      await onActivate()
    } finally {
      setStatus('granted')
      // Brief confirmation of the granted state, then auto-advance.
      setTimeout(onContinue, 1000)
    }
  }

  return (
    <StepScaffold
      stepIndex={stepIndex}
      totalSteps={totalSteps}
      eyebrow={eyebrow}
      title={title}
      subtitle={subtitle}
      align="left"
      aside={aside}
      onSkip={onSkip}
    >
      <div className="flex w-full items-center justify-between rounded-xl bg-white/[0.06] px-5 py-4">
        <div className="flex items-center gap-3">
          {icon}
          <div className="flex flex-col gap-0.5">
            <span className="text-sm font-medium text-white/90">{cardLabel}</span>
            <span
              className={'text-xs ' + (status === 'granted' ? 'text-green-400' : 'text-white/40')}
            >
              {statusText[status]}
            </span>
          </div>
        </div>
      </div>

      <div className="mt-8">
        <button
          type="button"
          onClick={() => void handleActivate()}
          disabled={status !== 'idle'}
          className={
            'rounded-xl px-8 py-3 text-sm font-medium transition-all ' +
            (status === 'idle'
              ? 'bg-white text-black hover:opacity-90'
              : status === 'waiting'
                ? 'cursor-not-allowed bg-white/20 text-white/50'
                : 'cursor-default bg-green-500/20 text-green-400')
          }
        >
          {buttonLabel[status]}
        </button>
      </div>
    </StepScaffold>
  )
}
