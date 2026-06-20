import { MessageCircle } from 'lucide-react'

type AutoCreatedTasksStepProps = {
  /** Complete onboarding and open the main chat page. */
  onFinish: () => void
}

export function AutoCreatedTasksStep({ onFinish }: AutoCreatedTasksStepProps): React.JSX.Element {
  return (
    <div className="animate-fade-in flex w-full max-w-[360px] flex-col items-center text-center">
      <div className="relative mb-6 flex h-24 w-24 items-center justify-center">
        {/* Soft radial glow behind the icon. */}
        <div className="absolute inset-0 rounded-full bg-white/[0.07] blur-2xl" />
        <div className="relative flex h-16 w-16 items-center justify-center rounded-3xl bg-white/[0.08]">
          <MessageCircle className="h-8 w-8 text-white/85" />
        </div>
      </div>

      <h1 className="font-display text-3xl font-semibold text-white/95">You are ready</h1>
      <p className="mt-3 text-sm leading-relaxed text-white/50">
        Start with chat, then bring in recordings, memories, and local context when you choose.
      </p>

      <button
        type="button"
        onClick={onFinish}
        className="mt-8 rounded-xl bg-white px-8 py-3 text-sm font-semibold text-black transition-opacity hover:opacity-90"
      >
        Go to chat
      </button>
    </div>
  )
}
