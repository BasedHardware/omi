import { ListChecks } from 'lucide-react'

type AutoCreatedTasksStepProps = {
  /** Complete onboarding and jump straight to the Tasks tab. */
  onFinish: () => void
}

export function AutoCreatedTasksStep({
  onFinish
}: AutoCreatedTasksStepProps): React.JSX.Element {
  return (
    <div className="animate-fade-in flex w-full max-w-[360px] flex-col items-center text-center">
      <div className="relative mb-6 flex h-24 w-24 items-center justify-center">
        {/* Soft radial glow behind the icon. */}
        <div className="absolute inset-0 rounded-full bg-white/[0.07] blur-2xl" />
        <div className="relative flex h-16 w-16 items-center justify-center rounded-3xl bg-white/[0.08]">
          <ListChecks className="h-8 w-8 text-white/85" />
        </div>
      </div>

      <h1 className="font-display text-3xl font-semibold text-white/95">Auto-created Tasks</h1>
      <p className="mt-3 text-sm leading-relaxed text-white/50">
        omi listens to your conversations and automatically creates tasks, action items, and
        follow-ups for you.
      </p>

      <button
        type="button"
        onClick={onFinish}
        className="mt-8 rounded-xl bg-white px-8 py-3 text-sm font-semibold text-black transition-opacity hover:opacity-90"
      >
        Take me to my tasks
      </button>
    </div>
  )
}
