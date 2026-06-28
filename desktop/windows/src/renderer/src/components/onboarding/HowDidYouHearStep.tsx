import { useState } from 'react'
import { StepScaffold } from './StepScaffold'

type HowDidYouHearStepProps = {
  stepIndex: number
  totalSteps: number
  onContinue: (source: string) => void
  onBack: () => void
  aside?: React.ReactNode
}

// Same set the macOS desktop app offers (canonical casing matches the values it
// reports to PostHog), in the order requested for the Windows wizard.
const SOURCES = [
  'Other',
  'Colleague',
  'Product Hunt',
  'Article',
  'Friend',
  'Event',
  'AI chat',
  'YouTube',
  'Search engine',
  'Newsletter',
  'Podcast',
  'Social media'
]

export function HowDidYouHearStep({
  stepIndex,
  totalSteps,
  onContinue,
  aside
}: HowDidYouHearStepProps): React.JSX.Element {
  const [selected, setSelected] = useState<string | null>(null)

  const pick = (source: string): void => {
    if (selected) return
    setSelected(source)
    // Brief highlight before advancing, mirroring the desktop app's 0.25s delay.
    setTimeout(() => onContinue(source), 250)
  }

  return (
    <StepScaffold
      stepIndex={stepIndex}
      totalSteps={totalSteps}
      eyebrow="QUICK QUESTION"
      title="How did you hear about Omi?"
      align="left"
      aside={aside}
    >
      <div className="flex flex-wrap gap-2.5">
        {SOURCES.map((source) => (
          <button
            key={source}
            type="button"
            onClick={() => pick(source)}
            className={
              'rounded-xl px-5 py-2.5 text-sm font-medium ' +
              (selected === source
                ? 'bg-white text-black'
                : 'bg-white/[0.06] text-white/80 hover:bg-white/[0.1]')
            }
          >
            {source}
          </button>
        ))}
      </div>
    </StepScaffold>
  )
}
