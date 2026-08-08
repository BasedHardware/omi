import { useState } from 'react'
import { AlertCircle, CheckCircle2, ChevronRight, Loader2, Wrench } from 'lucide-react'
import type { ChatContentBlock, ToolCallStatus } from '../../../../shared/chatContent'

type ToolCallData = Extract<ChatContentBlock, { type: 'toolCall' }>

// Per-status presentation. `running`/`slow`/`stalled` are still in-flight (a
// spinner); `slow`/`stalled` add a muted hint that the call is taking a while.
// `completed`/`failed` are terminal. Neutral + no purple (INV-UI-1); mirrors
// macOS ChatBubble's ToolCallCard status treatment.
const STATUS: Record<
  ToolCallStatus,
  { label: string; tint: string; spin: boolean; Icon: typeof CheckCircle2 }
> = {
  running: { label: 'Running', tint: 'text-white/45', spin: true, Icon: Loader2 },
  slow: { label: 'Still working', tint: 'text-white/45', spin: true, Icon: Loader2 },
  stalled: { label: 'Taking a while', tint: 'text-amber-400/80', spin: true, Icon: Loader2 },
  completed: { label: 'Done', tint: 'text-emerald-400', spin: false, Icon: CheckCircle2 },
  failed: { label: 'Failed', tint: 'text-red-400', spin: false, Icon: AlertCircle }
}

/**
 * One tool invocation, rendered inline in the assistant column. The header shows
 * the tool name, an inline argument summary, and a status pill; the row expands
 * to reveal full arguments (`input.details`) and any `output`. Collapsed by
 * default so a chain of tool calls stays scannable.
 */
export function ToolCallCard({
  block,
  compact
}: {
  block: ToolCallData
  compact: boolean
}): React.JSX.Element {
  const { label, tint, spin, Icon } = STATUS[block.status]
  const hasDetail = Boolean(block.input?.details || block.output)
  const [open, setOpen] = useState(false)
  const pad = compact ? 'px-3 py-2' : 'px-3.5 py-2.5'
  const nameCls = `font-medium ${compact ? 'text-[13px]' : 'text-sm'} text-white/90`
  const monoCls = `${compact ? 'text-[11px]' : 'text-[12px]'} font-mono text-white/45`

  return (
    <div
      className={`bubble-in mr-auto w-fit max-w-[85%] rounded-2xl border border-white/10 bg-white/[0.04] ${pad}`}
    >
      <button
        type="button"
        onClick={hasDetail ? () => setOpen((v) => !v) : undefined}
        aria-expanded={hasDetail ? open : undefined}
        disabled={!hasDetail}
        className={`flex w-full items-center gap-2 text-left ${
          hasDetail ? 'focus-ring cursor-pointer' : 'cursor-default'
        }`}
      >
        <Wrench className={`${compact ? 'h-3.5 w-3.5' : 'h-4 w-4'} shrink-0 text-white/70`} />
        <span className={nameCls}>{block.name}</span>
        {block.input?.summary ? (
          <span className={`min-w-0 truncate ${monoCls}`}>{block.input.summary}</span>
        ) : null}
        <span className={`ml-auto flex shrink-0 items-center gap-1 ${tint}`}>
          <Icon className={`h-3.5 w-3.5 ${spin ? 'animate-spin' : ''}`} />
          <span className="text-[11px] font-medium">{label}</span>
        </span>
        {hasDetail ? (
          <ChevronRight
            className={`h-3.5 w-3.5 shrink-0 text-white/35 transition-transform ${
              open ? 'rotate-90' : ''
            }`}
          />
        ) : null}
      </button>
      {hasDetail && open ? (
        <div className="mt-2 flex flex-col gap-2">
          {block.input?.details ? (
            <pre
              className={`overflow-x-auto rounded-lg bg-black/25 p-2 ${monoCls} whitespace-pre-wrap`}
            >
              {block.input.details}
            </pre>
          ) : null}
          {block.output ? (
            <pre
              className={`overflow-x-auto rounded-lg bg-black/25 p-2 ${monoCls} whitespace-pre-wrap`}
            >
              {block.output}
            </pre>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}
