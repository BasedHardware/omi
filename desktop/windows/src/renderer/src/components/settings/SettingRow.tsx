import type { LucideIcon } from 'lucide-react'
import { cn } from '../../lib/utils'
import { useSearchableRow } from './searchContext'

export type DotTone = 'on' | 'off' | 'warn'

const DOT_CLASS: Record<DotTone, string> = {
  on: 'bg-[color:var(--accent)]',
  off: 'bg-white/25',
  warn: 'bg-amber-400'
}

/**
 * macOS-parity settings row: [status dot] [icon] Title / subtitle ……… [control].
 * Anything that doesn't fit on the right edge (textareas, lists, multi-field
 * panels) goes in `children`, rendered as an expanded body below the row.
 *
 * Self-hides when the current Settings search query doesn't match its title,
 * subtitle, or `keywords`.
 */
export function SettingRow(props: {
  icon?: LucideIcon
  title: string
  subtitle?: string
  /** Extra hidden terms to match in search (not displayed). */
  keywords?: string
  dot?: DotTone
  /** Right-aligned control (Toggle, button, select). */
  control?: React.ReactNode
  children?: React.ReactNode
}): React.JSX.Element | null {
  const { icon: Icon, title, subtitle, keywords, dot, control, children } = props
  const visible = useSearchableRow(`${title} ${subtitle ?? ''} ${keywords ?? ''}`)
  if (!visible) return null

  return (
    <div className="border-b border-white/[0.06] py-5 last:border-b-0">
      <div className="flex items-center gap-4">
        {dot && <span className={cn('h-2 w-2 shrink-0 rounded-full', DOT_CLASS[dot])} />}
        {Icon && <Icon className="h-5 w-5 shrink-0 text-white/55" strokeWidth={1.75} />}
        <div className="min-w-0 flex-1">
          <div className="text-[15px] font-semibold text-text-primary">{title}</div>
          {subtitle && <div className="mt-0.5 text-sm text-text-tertiary">{subtitle}</div>}
        </div>
        {control && <div className="shrink-0">{control}</div>}
      </div>
      {children && <div className="mt-4">{children}</div>}
    </div>
  )
}
