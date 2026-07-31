import { ArrowUpRight, Sparkles } from 'lucide-react'
import { cn } from '../../../lib/utils'
import { HUB_SUGGESTIONS } from './hubPrompts'

export function HubSuggestions({ onPick }: { onPick: (text: string) => void }): React.JSX.Element {
  return (
    // VStack(spacing: 8) on Mac (DashboardPage.swift:961).
    <div className="flex w-full flex-col gap-2">
      {HUB_SUGGESTIONS.map((text) => (
        <button
          key={text}
          type="button"
          onClick={() => onPick(text)}
          className={cn(
            'focus-ring group flex h-[42px] w-full items-center gap-2.5 rounded-[21px]',
            'border border-home-hairline bg-home-tile/[0.55] px-4 text-left',
            'transition-colors duration-150 hover:bg-home-tileHover'
          )}
        >
          {/* Gold, not violet — the one warm accent on the stage. */}
          <Sparkles
            className="h-[11px] w-[11px] shrink-0 text-home-muted transition-colors duration-150 group-hover:text-[#E3BF63]"
            strokeWidth={2.5}
          />
          <span className="min-w-0 flex-1 truncate text-[13px] font-medium text-home-secondary transition-colors duration-150 group-hover:text-home-ink">
            {text}
          </span>
          <ArrowUpRight
            className="h-2.5 w-2.5 shrink-0 text-home-faint transition-colors duration-150 group-hover:text-home-secondary"
            strokeWidth={2.5}
          />
        </button>
      ))}
    </div>
  )
}
