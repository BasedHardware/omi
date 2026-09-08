import { AlertCircle, Bot, CheckCircle2, CircleSlash, Loader2 } from 'lucide-react'
import type { AgentThreadCardBlock } from '../../../../shared/types'

// Shared-thread agent cards (B4, INV-CHAT-1). The two durable artifacts a
// background agent leaves in the shared thread: a spawn card at launch and one
// completion card at terminal. Understated + neutral — no purple (INV-UI-1).

type CompletionStatus = 'succeeded' | 'stopped' | 'failed'

const STATUS: Record<CompletionStatus, { label: string; dot: string; Icon: typeof CheckCircle2 }> =
  {
    succeeded: { label: 'Done', dot: 'text-emerald-400', Icon: CheckCircle2 },
    stopped: { label: 'Stopped', dot: 'text-white/50', Icon: CircleSlash },
    failed: { label: 'Failed', dot: 'text-red-400', Icon: AlertCircle }
  }

function coerceStatus(status: string): CompletionStatus {
  return status === 'succeeded' || status === 'stopped' || status === 'failed' ? status : 'failed'
}

/**
 * One shared-thread agent card. Rendered inside the assistant column of the chat
 * thread (both the main window and the floating bar). `compact` trims padding and
 * type for the bar's narrower panel.
 */
export function AgentThreadCard({
  block,
  compact
}: {
  block: AgentThreadCardBlock
  compact: boolean
}): React.JSX.Element {
  const pad = compact ? 'px-3 py-2' : 'px-3.5 py-2.5'
  const shell = `mr-auto w-fit max-w-[85%] rounded-2xl border border-white/10 bg-white/[0.04] ${pad}`
  const titleCls = `truncate font-medium ${compact ? 'text-[13px]' : 'text-sm'} text-white/90`
  const bodyCls = `${compact ? 'text-[12px]' : 'text-[13px]'} leading-snug text-white/60`

  if (block.type === 'agentSpawn') {
    return (
      <div className={`bubble-in ${shell}`}>
        <div className="flex items-center gap-2">
          <Bot className={`${compact ? 'h-3.5 w-3.5' : 'h-4 w-4'} shrink-0 text-white/70`} />
          <span className={titleCls}>{block.title}</span>
          <span className="ml-1 flex shrink-0 items-center gap-1 text-white/45">
            <Loader2 className="h-3 w-3 animate-spin" />
            <span className="text-[11px]">Running</span>
          </span>
        </div>
        {block.objective ? (
          <p className={`mt-1 line-clamp-2 ${bodyCls}`}>{block.objective}</p>
        ) : null}
      </div>
    )
  }

  const status = coerceStatus(block.status)
  const { label, dot, Icon } = STATUS[status]
  return (
    <div className={`bubble-in ${shell}`}>
      <div className="flex items-center gap-2">
        <Bot className={`${compact ? 'h-3.5 w-3.5' : 'h-4 w-4'} shrink-0 text-white/70`} />
        <span className={titleCls}>{block.title}</span>
        <span className={`ml-1 flex shrink-0 items-center gap-1 ${dot}`}>
          <Icon className="h-3.5 w-3.5" />
          <span className="text-[11px] font-medium">{label}</span>
        </span>
      </div>
      {block.output ? (
        <p className={`mt-1.5 line-clamp-4 whitespace-pre-wrap ${bodyCls}`}>{block.output}</p>
      ) : null}
    </div>
  )
}
