import { Monitor, Mic, Sparkles, type LucideIcon } from 'lucide-react'
import { StepScaffold } from './StepScaffold'

type TrustStepProps = {
  stepIndex: number
  totalSteps: number
  onContinue: () => void
  onBack: () => void
}

// The macOS desktop app's "Read the source code" button opens the public repo.
const SOURCE_URL = 'https://github.com/BasedHardware/omi'

const PERMISSIONS: { icon: LucideIcon; title: string; detail: string }[] = [
  {
    icon: Monitor,
    title: 'Screen + recording',
    detail: 'Build context for what you’re working on.'
  },
  {
    icon: Mic,
    title: 'Microphone',
    detail: 'Capture voice notes and meeting context.'
  },
  {
    icon: Sparkles,
    title: 'Take actions in your apps',
    detail: 'See the active window and, with your approval each time, click and type for you.'
  }
]

export function TrustStep({
  stepIndex,
  totalSteps,
  onContinue
}: TrustStepProps): React.JSX.Element {
  return (
    <StepScaffold
      stepIndex={stepIndex}
      totalSteps={totalSteps}
      eyebrow="BEFORE WE CONTINUE"
      title="I'm going to ask you for a few permissions"
    >
      <div className="w-full">
        <p className="text-center text-sm leading-relaxed text-white">
          Omi is open source and private by design. During setup, we’ll ask you for these
          permissions to understand your work and help in the right places.
        </p>

        <div className="mt-6 flex flex-col gap-3">
          {PERMISSIONS.map(({ icon: Icon, title, detail }) => (
            <div
              key={title}
              className="flex w-full items-center gap-4 rounded-xl bg-white/[0.06] px-5 py-3 text-left"
            >
              <Icon className="h-6 w-6 shrink-0 text-white/80" strokeWidth={1.75} />
              <div>
                <p className="text-sm font-semibold text-white">{title}</p>
                <p className="mt-0.5 text-xs text-white/60">{detail}</p>
              </div>
            </div>
          ))}
        </div>

        <div className="mt-6 flex items-center justify-center gap-2.5">
          <button
            type="button"
            onClick={onContinue}
            className="rounded-lg bg-white px-5 py-2 text-sm font-medium text-black transition-opacity hover:opacity-90"
          >
            Continue
          </button>
          <button
            type="button"
            onClick={() => window.open(SOURCE_URL)}
            className="rounded-lg bg-black px-5 py-2 text-sm font-medium text-white ring-1 ring-white/15 transition-colors hover:bg-white/5"
          >
            Read the source code
          </button>
        </div>
      </div>
    </StepScaffold>
  )
}
