import { useState } from 'react'
import { Brain, ChevronRight } from 'lucide-react'
import type { ChatContentBlock } from '../../../../shared/chatContent'

type ThinkingBlockData = Extract<ChatContentBlock, { type: 'thinking' }>

/**
 * Model reasoning, rendered as a collapsible italic block (mirrors macOS
 * ChatBubble's thinking block). Collapsed by default — reasoning is available on
 * demand, not in the reader's face. Understated + neutral, no purple (INV-UI-1).
 *
 * Note: `thinking` blocks are pruned from the transcript once a turn's stream
 * settles (see chatContent.ts render-pruning rule), so this renders for in-flight
 * turns and any transcript that deliberately retains reasoning.
 */
export function ThinkingBlock({
  block,
  compact
}: {
  block: ThinkingBlockData
  compact: boolean
}): React.JSX.Element {
  const [open, setOpen] = useState(false)
  const pad = compact ? 'px-3 py-2' : 'px-3.5 py-2.5'
  const bodyCls = `${compact ? 'text-[12px]' : 'text-[13px]'} leading-relaxed text-white/55`
  return (
    <div className={`bubble-in mr-auto w-fit max-w-[85%] rounded-2xl bg-white/[0.03] ${pad}`}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="focus-ring flex items-center gap-1.5 text-white/50 transition-colors hover:text-white/75"
      >
        <Brain className={compact ? 'h-3.5 w-3.5' : 'h-4 w-4'} />
        <span className={`${compact ? 'text-[12px]' : 'text-[13px]'} font-medium`}>Thinking</span>
        <ChevronRight className={`h-3.5 w-3.5 transition-transform ${open ? 'rotate-90' : ''}`} />
      </button>
      {open ? <p className={`mt-1.5 whitespace-pre-wrap italic ${bodyCls}`}>{block.text}</p> : null}
    </div>
  )
}
