import { useEffect, useState } from 'react'
import { StepScaffold } from './StepScaffold'
import macsImg from '../../assets/macs.png'

type AskDemoStepProps = {
  stepIndex: number
  totalSteps: number
  onContinue: () => void
  onSkip?: () => void
}

/**
 * Onboarding demo step: the user is invited to type "Which computer should I
 * buy?" in the floating bar; Omi's "answer" — a Mac comparison image — is shown
 * as the payoff. The image renders unconditionally (with a mount fade-in) so it
 * can never be held hostage to the floating-bar event firing; Continue is always
 * available so the step can't dead-end.
 */
export function AskDemoStep({
  stepIndex,
  totalSteps,
  onContinue,
  onSkip
}: AskDemoStepProps): React.JSX.Element {
  // Drives the enter transition: mount with the "from" classes, then flip to
  // "to" on the next frame so the fade+slide animates.
  const [revealed, setRevealed] = useState(false)

  useEffect(() => {
    // The bar should already be enabled/warm from earlier steps; ensure it.
    window.omiOverlay?.setEnabled(true)
    const id = requestAnimationFrame(() => setRevealed(true))
    return () => cancelAnimationFrame(id)
  }, [])

  return (
    <StepScaffold
      stepIndex={stepIndex}
      totalSteps={totalSteps}
      title={'Type in the floating bar “Which computer should I buy?”'}
      align="center"
      widthClassName="max-w-[820px]"
      onContinue={onContinue}
      onSkip={onSkip}
    >
      <div className="mt-4 flex min-h-[260px] w-full items-center justify-center">
        <img
          src={macsImg}
          alt="Omi's answer: a comparison of Mac models"
          onError={(e) => console.error('[AskDemoStep] macs.png failed to load', e)}
          className={
            'w-full rounded-2xl shadow-2xl ring-1 ring-white/10 transition-all duration-500 ease-out ' +
            (revealed ? 'translate-y-0 opacity-100' : 'translate-y-4 opacity-0')
          }
        />
      </div>
    </StepScaffold>
  )
}
