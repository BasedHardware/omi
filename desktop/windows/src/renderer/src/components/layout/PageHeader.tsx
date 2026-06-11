import { useEffect, useRef, useState } from 'react'
import { ArrowLeft, Pencil } from 'lucide-react'

export function PageHeader(props: {
  title: string
  subtitle?: string
  actions?: React.ReactNode
  /** When set, a back arrow is shown at the top-left and calls this on click. */
  onBack?: () => void
  /**
   * When set, the title becomes click-to-edit: clicking it reveals an input,
   * and committing (Enter / blur) calls this with the new name. Escape cancels.
   */
  onRename?: (title: string) => void
  /**
   * When set, replaces the <h1> title with custom content (e.g. a segmented
   * tab switcher). `title` is still required for accessibility/fallback but is
   * not rendered. Ignored together with onRename.
   */
  titleSlot?: React.ReactNode
}): React.JSX.Element {
  const { title, subtitle, actions, onBack, onRename, titleSlot } = props
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(title)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (editing) {
      inputRef.current?.focus()
      inputRef.current?.select()
    }
  }, [editing])

  const startEdit = (): void => {
    setDraft(title)
    setEditing(true)
  }

  const commit = (): void => {
    setEditing(false)
    const next = draft.trim()
    if (next && next !== title) onRename?.(next)
  }

  return (
    <header className="relative z-10 shrink-0 px-6 py-6 lg:px-10 lg:py-7">
      <div className="panel-header flex items-center justify-between gap-4">
        <div className="flex min-w-0 flex-1 items-center gap-3">
          {onBack && (
            <button
              onClick={onBack}
              className="btn-ghost -ml-1 shrink-0 p-2"
              title="Back to conversations"
              aria-label="Back"
            >
              <ArrowLeft className="h-5 w-5" />
            </button>
          )}
          <div className="min-w-0 flex-1">
            {titleSlot ? (
              titleSlot
            ) : editing ? (
              <input
                ref={inputRef}
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onBlur={commit}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') commit()
                  else if (e.key === 'Escape') setEditing(false)
                }}
                className="w-full border-0 border-b border-white/25 bg-transparent pb-1 font-display text-2xl font-bold tracking-tight text-white focus:border-white/60 focus:outline-none focus:ring-0"
              />
            ) : onRename ? (
              <button
                onClick={startEdit}
                title="Rename"
                className="group flex max-w-full items-center gap-2 text-left"
              >
                <h1 className="truncate font-display text-2xl font-bold tracking-tight text-white">
                  {title}
                </h1>
                <Pencil className="h-4 w-4 shrink-0 text-white/30 transition-colors group-hover:text-white/70" />
              </button>
            ) : (
              <h1 className="truncate font-display text-2xl font-bold tracking-tight text-white">
                {title}
              </h1>
            )}
            {subtitle && <p className="mt-1 text-sm text-white/50">{subtitle}</p>}
          </div>
        </div>
        {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
      </div>
    </header>
  )
}
