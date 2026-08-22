import { useState } from 'react'
import { ChevronRight, Sparkles } from 'lucide-react'
import type { ChatContentBlock } from '../../../../shared/chatContent'

type DiscoveryCardData = Extract<ChatContentBlock, { type: 'discoveryCard' }>

/**
 * A discovery / AI-profile card: a titled summary that expands to full text
 * (mirrors macOS ChatBubble's discovery card). Collapsed by default; the summary
 * is always visible so the card reads at a glance. Neutral, no purple (INV-UI-1).
 */
export function DiscoveryCard({
  block,
  compact
}: {
  block: DiscoveryCardData
  compact: boolean
}): React.JSX.Element {
  const [open, setOpen] = useState(false)
  const hasMore = Boolean(block.fullText && block.fullText !== block.summary)
  const pad = compact ? 'px-3 py-2' : 'px-3.5 py-2.5'
  const titleCls = `font-medium ${compact ? 'text-[13px]' : 'text-sm'} text-white/90`
  const bodyCls = `${compact ? 'text-[12px]' : 'text-[13px]'} leading-relaxed text-white/60`

  return (
    <div
      className={`bubble-in mr-auto w-fit max-w-[85%] rounded-2xl border border-white/10 bg-white/[0.04] ${pad}`}
    >
      <button
        type="button"
        onClick={hasMore ? () => setOpen((v) => !v) : undefined}
        aria-expanded={hasMore ? open : undefined}
        disabled={!hasMore}
        className={`flex w-full items-center gap-2 text-left ${hasMore ? 'focus-ring' : ''}`}
      >
        <Sparkles className={`${compact ? 'h-3.5 w-3.5' : 'h-4 w-4'} shrink-0 text-white/70`} />
        <span className={titleCls}>{block.title}</span>
        {hasMore ? (
          <ChevronRight
            className={`ml-auto h-3.5 w-3.5 shrink-0 text-white/35 transition-transform ${
              open ? 'rotate-90' : ''
            }`}
          />
        ) : null}
      </button>
      <p className={`mt-1.5 whitespace-pre-wrap ${bodyCls}`}>
        {open && hasMore ? block.fullText : block.summary}
      </p>
    </div>
  )
}
