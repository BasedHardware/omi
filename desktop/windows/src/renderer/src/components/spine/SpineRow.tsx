// One row of the Activity stream.
//
// Every row draws the same gutter so the day reads as a single timeline rather
// than five stacked lists. Only unattached rows print their time: an attached
// row belongs to the conversation above it and repeating the clock beside it
// implies it happened separately.

import { MessagesSquare, Brain, ListChecks, Monitor, Network, Star } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { formatRowTime, type SpineRow as Row } from '../../lib/spine/spineModel'

const KIND_ICONS: Record<string, LucideIcon> = {
  conversations: MessagesSquare,
  memories: Brain,
  tasks: ListChecks,
  screen: Monitor
}

function Gutter(props: { time: string | null }): React.JSX.Element {
  return (
    <div className="relative w-[68px] shrink-0 border-r border-white/10 pr-3 text-right">
      {props.time !== null && (
        <>
          <span className="text-[11px] tabular-nums text-white/35">{props.time}</span>
          <span className="absolute -right-[3px] top-1.5 block h-[5px] w-[5px] rounded-full bg-white/30" />
        </>
      )}
    </div>
  )
}

export function SpineRowView(props: {
  row: Row
  /** Attached rows indent only in the unfiltered view; inside a single-kind
   *  filter there is no parent on screen to indent under. */
  showIndent: boolean
  onOpenConversation: (id: string) => void
  onToggleStar: (id: string, starred: boolean) => void
  onOpenKind: (kind: Row['kind']) => void
}): React.JSX.Element {
  const { row } = props
  const nested = row.isAttached && props.showIndent
  const Icon = KIND_ICONS[row.kind] ?? Monitor

  return (
    <div className={`flex items-start ${nested ? 'pt-2' : 'pt-5'}`}>
      <Gutter time={row.isAttached ? null : formatRowTime(row.anchor)} />
      <div className={`min-w-0 flex-1 ${nested ? 'pl-7' : 'pl-4'}`}>
        {row.content.type === 'conversation' && (
          <button
            type="button"
            onClick={() =>
              props.onOpenConversation(
                row.content.type === 'conversation' ? row.content.conversation.id : ''
              )
            }
            className="group flex w-full items-center gap-3 rounded-xl bg-white/[0.04] px-4 py-3 text-left hover:bg-white/[0.07]"
          >
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-white/10 bg-white/[0.06] text-lg">
              {row.content.conversation.emoji}
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm text-white/90">
                {row.content.conversation.title || 'Untitled conversation'}
              </span>
              <span className="block truncate text-xs text-white/40">
                {row.content.conversation.overview}
              </span>
            </span>
            <span
              role="button"
              tabIndex={0}
              aria-label={row.content.conversation.starred ? 'Unstar' : 'Star'}
              onClick={(e) => {
                e.stopPropagation()
                if (row.content.type !== 'conversation') return
                props.onToggleStar(row.content.conversation.id, row.content.conversation.starred)
              }}
              onKeyDown={(e) => {
                if (e.key !== 'Enter' && e.key !== ' ') return
                e.preventDefault()
                e.stopPropagation()
                if (row.content.type !== 'conversation') return
                props.onToggleStar(row.content.conversation.id, row.content.conversation.starred)
              }}
              className={`shrink-0 rounded p-1 ${
                row.content.conversation.starred
                  ? 'text-amber-300'
                  : 'text-white/35 opacity-0 group-hover:opacity-100'
              }`}
            >
              <Star
                className="h-3.5 w-3.5"
                fill={row.content.conversation.starred ? 'currentColor' : 'none'}
              />
            </span>
          </button>
        )}

        {row.content.type === 'memories' && (
          <ul className="space-y-1.5">
            {row.content.memories.map((memory) => (
              <li key={memory.id} className="flex items-start gap-2">
                <Icon className="mt-0.5 h-3.5 w-3.5 shrink-0 text-white/30" strokeWidth={1.8} />
                <span className="text-sm leading-snug text-white/75">{memory.text}</span>
              </li>
            ))}
          </ul>
        )}

        {row.content.type === 'tasks' && (
          <ul className="space-y-1.5">
            {row.content.tasks.map((task) => (
              <li key={task.id} className="flex items-start gap-2">
                <Icon className="mt-0.5 h-3.5 w-3.5 shrink-0 text-white/30" strokeWidth={1.8} />
                <span
                  className={`text-sm leading-snug ${
                    task.completed ? 'text-white/35 line-through' : 'text-white/75'
                  }`}
                >
                  {task.text}
                </span>
              </li>
            ))}
          </ul>
        )}

        {row.content.type === 'moments' && (
          <div>
            <div className="flex flex-wrap gap-1.5">
              {row.content.shown.map((moment) => (
                <span
                  key={moment.id}
                  title={moment.windowTitle ?? moment.appName}
                  className="max-w-[180px] truncate rounded-md bg-white/[0.05] px-2 py-1 text-xs text-white/55"
                >
                  {moment.windowTitle ?? moment.appName}
                </span>
              ))}
            </div>
            {row.content.total > row.content.shown.length && (
              // The strip says how much it is not showing rather than implying
              // these were the only frames captured.
              <p className="mt-1 text-[11px] text-white/30">
                {`Showing ${row.content.shown.length} of ${row.content.total.toLocaleString()} screen moments`}
              </p>
            )}
          </div>
        )}

        {row.content.type === 'brainMap' && (
          <button
            type="button"
            onClick={() => props.onOpenKind('memories')}
            className="flex w-full items-center gap-3 rounded-xl border border-white/10 px-4 py-3 text-left hover:bg-white/[0.05]"
          >
            <Network className="h-4 w-4 shrink-0 text-white/40" strokeWidth={1.8} />
            <span className="min-w-0 flex-1">
              <span className="block text-sm text-white/85">Brain map</span>
              <span className="block text-xs text-white/40">
                {`How the day’s ${row.content.memoryCount === 1 ? 'memory connects' : `${row.content.memoryCount} memories connect`}`}
              </span>
            </span>
          </button>
        )}
      </div>
    </div>
  )
}
