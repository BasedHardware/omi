import { useEffect, useRef, useState } from 'react'
import { X, RotateCcw, Loader2 } from 'lucide-react'
import { cn } from '../../lib/utils'

type Priority = 'high' | 'medium' | 'low'

interface Props {
  onClose: () => void
  onCreate: (description: string, priority: Priority) => Promise<void>
}

const PRIORITY_OPTIONS: { value: Priority; label: string; active: string }[] = [
  { value: 'high', label: 'High', active: 'border-red-500/40 bg-red-500/15 text-red-400' },
  { value: 'medium', label: 'Medium', active: 'border-orange-500/40 bg-orange-500/15 text-orange-400' },
  { value: 'low', label: 'Low', active: 'border-blue-500/40 bg-blue-500/15 text-blue-400' },
]

export function DailyTaskSheet({ onClose, onCreate }: Props): React.JSX.Element {
  const [description, setDescription] = useState('')
  const [priority, setPriority] = useState<Priority>('medium')
  const [creating, setCreating] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    const t = setTimeout(() => inputRef.current?.focus(), 80)
    return () => clearTimeout(t)
  }, [])

  const create = async (): Promise<void> => {
    const text = description.trim()
    if (!text || creating) return
    setCreating(true)
    try {
      await onCreate(text, priority)
      onClose()
    } finally {
      setCreating(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="glass-strong w-[450px] max-w-[calc(100vw-2rem)] animate-spring-enter rounded-2xl shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center gap-3 border-b border-white/[0.07] px-6 py-4">
          <RotateCcw className="h-4 w-4 text-[color:var(--accent)]" strokeWidth={1.75} />
          <div className="flex-1">
            <h2 className="text-sm font-semibold text-white/90">Create Daily Task</h2>
            <p className="text-[11px] text-white/40">This task will repeat every day until completed</p>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-white/30 transition-colors hover:bg-white/10 hover:text-white/70"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="px-6 py-5 space-y-4">
          {/* Description */}
          <div>
            <label className="mb-1.5 block text-[10px] font-semibold uppercase tracking-wider text-white/35">
              Task Description
            </label>
            <input
              ref={inputRef}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') void create()
                else if (e.key === 'Escape') onClose()
              }}
              placeholder="What needs to be done daily?"
              className="input-field"
            />
          </div>

          {/* Priority */}
          <div>
            <label className="mb-2 block text-[10px] font-semibold uppercase tracking-wider text-white/35">
              Priority
            </label>
            <div className="flex gap-2">
              {PRIORITY_OPTIONS.map((p) => (
                <button
                  key={p.value}
                  onClick={() => setPriority(p.value)}
                  className={cn(
                    'flex-1 rounded-xl border py-2 text-sm font-medium transition-all',
                    priority === p.value
                      ? p.active
                      : 'border-white/10 bg-white/[0.04] text-white/50 hover:bg-white/[0.08]'
                  )}
                >
                  {p.label}
                </button>
              ))}
            </div>
          </div>

          {/* Create button */}
          <div className="flex justify-end pt-1">
            <button
              onClick={() => void create()}
              disabled={!description.trim() || creating}
              className="btn-primary px-5 py-2 disabled:opacity-40"
            >
              {creating ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                '+ Create Daily Task'
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
