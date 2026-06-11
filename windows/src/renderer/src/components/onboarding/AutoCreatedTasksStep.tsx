import { useState } from 'react'
import { Check, ListChecks } from 'lucide-react'

type AutoCreatedTasksStepProps = {
  /** Complete onboarding and jump straight to the Tasks tab. */
  onFinish: () => void
}

// Illustrative sample rows shown on the onboarding completion screen — they
// demonstrate the auto-task feature (real tasks come from conversations the user
// hasn't had yet). "Getting started" starts completed; the rows are clickable so
// the user can check the others off too.
const SAMPLE_TASKS = [
  { title: 'Task 1', subtitle: 'From today’s meeting' },
  { title: 'Task 2', subtitle: 'Mentioned in Slack' },
  { title: 'Task 3', subtitle: 'Getting started' }
]

function TaskRow({
  title,
  subtitle,
  done,
  onToggle
}: {
  title: string
  subtitle: string
  done: boolean
  onToggle: () => void
}): React.JSX.Element {
  return (
    <button
      type="button"
      onClick={onToggle}
      className="flex w-full items-center gap-3 rounded-xl bg-white/[0.06] px-4 py-2.5 text-left transition-colors hover:bg-white/[0.1]"
    >
      {done ? (
        <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-green-500">
          <Check className="h-3 w-3 text-black" strokeWidth={3} />
        </span>
      ) : (
        <span className="h-5 w-5 shrink-0 rounded-full border-2 border-white/25" />
      )}
      <div className="flex flex-col gap-0.5">
        <span
          className={
            'text-sm font-medium transition-colors ' +
            (done ? 'text-white/35 line-through' : 'text-white/90')
          }
        >
          {title}
        </span>
        <span className="text-xs text-white/40">{subtitle}</span>
      </div>
    </button>
  )
}

export function AutoCreatedTasksStep({
  onFinish
}: AutoCreatedTasksStepProps): React.JSX.Element {
  // Track which sample rows are checked off. Task 3 ("Getting started") starts
  // done; clicking any row toggles it.
  const [done, setDone] = useState<Set<number>>(new Set([2]))
  const toggle = (i: number): void =>
    setDone((prev) => {
      const next = new Set(prev)
      if (next.has(i)) next.delete(i)
      else next.add(i)
      return next
    })

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

      <div className="mt-7 flex w-full flex-col gap-2">
        {SAMPLE_TASKS.map((t, i) => (
          <TaskRow
            key={t.title}
            title={t.title}
            subtitle={t.subtitle}
            done={done.has(i)}
            onToggle={() => toggle(i)}
          />
        ))}
      </div>

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
