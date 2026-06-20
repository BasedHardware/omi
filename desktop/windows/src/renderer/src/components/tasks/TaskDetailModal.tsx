import { useState } from 'react'
import { X, Calendar, CheckCircle, Circle, ExternalLink, Tag, Zap, Info } from 'lucide-react'
import { Link } from 'react-router-dom'
import { cn } from '../../lib/utils'

export type ActionItem = {
  id: string
  description: string
  completed: boolean
  due_at?: string | null
  completed_at?: string | null
  created_at?: string | null
  conversation_id?: string | null
  // Extended API fields
  category?: string | null
  priority?: 'high' | 'medium' | 'low' | null
  source?: string | null
  tags?: string[] | null
  origin?: string | null
  source_app?: string | null
}

type ConvMeta = { title: string; emoji?: string }

interface Props {
  task: ActionItem
  convMeta?: ConvMeta
  onClose: () => void
  onToggleComplete: (id: string, done: boolean) => void
  onDelete: (id: string) => void
}

function FieldRow({ label, value }: { label: string; value: string }): React.JSX.Element {
  return (
    <div className="flex items-baseline gap-3">
      <span className="w-[90px] shrink-0 text-[10px] font-semibold uppercase tracking-wider text-white/30">{label}</span>
      <span className="text-sm text-white/70">{value}</span>
    </div>
  )
}

function fmtDate(iso?: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return isNaN(d.getTime()) ? '—' : d.toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })
}

const PRIORITY_STYLE: Record<string, string> = {
  high: 'bg-red-500/15 text-red-400',
  medium: 'bg-orange-500/15 text-orange-400',
  low: 'bg-blue-500/15 text-blue-400',
}

export function TaskInfoButton({ onClick }: { onClick: (e: React.MouseEvent) => void }): React.JSX.Element {
  return (
    <button
      onClick={(e) => { e.stopPropagation(); onClick(e) }}
      className="shrink-0 rounded-md p-1 text-white/20 opacity-0 transition-all hover:bg-white/5 hover:text-white/50 group-hover:opacity-100"
      title="View task details"
      aria-label="Task details"
    >
      <Info className="h-3.5 w-3.5" />
    </button>
  )
}

export function TaskDetailModal({ task, convMeta, onClose, onToggleComplete, onDelete }: Props): React.JSX.Element {
  const [confirming, setConfirming] = useState(false)

  const priorityLabel = task.priority
    ? task.priority.charAt(0).toUpperCase() + task.priority.slice(1)
    : null

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="glass-strong flex max-h-[80vh] w-[550px] max-w-[calc(100vw-2rem)] flex-col overflow-hidden rounded-2xl shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex shrink-0 items-start gap-3 border-b border-white/[0.07] px-6 py-4">
          <div className="flex-1 min-w-0">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-white/30">Task Details</p>
            <h2 className="mt-1 text-[15px] font-semibold leading-snug text-white/90">{task.description}</h2>
          </div>
          <button
            onClick={onClose}
            className="shrink-0 rounded-lg p-1.5 text-white/30 transition-colors hover:bg-white/10 hover:text-white/70"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-5">
          {/* Status + priority chips */}
          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={() => { onToggleComplete(task.id, !task.completed); onClose() }}
              className={cn(
                'flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors',
                task.completed
                  ? 'bg-green-500/15 text-green-400 hover:bg-green-500/25'
                  : 'bg-white/[0.06] text-white/60 hover:bg-white/10'
              )}
            >
              {task.completed
                ? <CheckCircle className="h-4 w-4" />
                : <Circle className="h-4 w-4" />}
              {task.completed ? 'Completed' : 'Open'}
            </button>
            {priorityLabel && (
              <span className={cn('flex items-center gap-1 rounded-lg px-3 py-1.5 text-sm font-medium', PRIORITY_STYLE[task.priority!] ?? 'bg-white/[0.05] text-white/50')}>
                <Zap className="h-3.5 w-3.5" />
                {priorityLabel} Priority
              </span>
            )}
            {task.category && (
              <span className="rounded-lg bg-white/[0.06] px-3 py-1.5 text-sm text-white/55">
                {task.category}
              </span>
            )}
          </div>

          {/* Core fields */}
          <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] px-4 py-4 space-y-3">
            {task.source && <FieldRow label="Source" value={task.source} />}
            {task.source_app && <FieldRow label="App" value={task.source_app} />}
            {task.origin && <FieldRow label="Origin" value={task.origin} />}
            <FieldRow label="Created" value={fmtDate(task.created_at)} />
            {task.due_at && (
              <div className="flex items-baseline gap-3">
                <span className="w-[90px] shrink-0 text-[10px] font-semibold uppercase tracking-wider text-white/30">Due</span>
                <span className={cn('flex items-center gap-1.5 text-sm', new Date(task.due_at) < new Date() && !task.completed ? 'text-red-300' : 'text-white/70')}>
                  <Calendar className="h-3 w-3" />
                  {fmtDate(task.due_at)}
                </span>
              </div>
            )}
            {task.completed_at && <FieldRow label="Completed" value={fmtDate(task.completed_at)} />}
          </div>

          {/* Tags */}
          {task.tags && task.tags.length > 0 && (
            <div>
              <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-white/30">Tags</p>
              <div className="flex flex-wrap gap-1.5">
                {task.tags.map((t) => (
                  <span
                    key={t}
                    className="flex items-center gap-1 rounded-full border border-white/[0.08] bg-white/[0.04] px-2.5 py-0.5 text-[11px] text-white/55"
                  >
                    <Tag className="h-2.5 w-2.5" />
                    {t}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Source conversation */}
          {task.conversation_id && (
            <div>
              <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-white/30">Source Conversation</p>
              <Link
                to={`/conversations/${task.conversation_id}`}
                onClick={onClose}
                className="flex items-center gap-2 rounded-xl border border-white/[0.07] bg-white/[0.03] px-4 py-3 text-sm text-white/70 transition-colors hover:bg-white/[0.07] hover:text-white/90"
              >
                {convMeta ? (
                  <span className="flex-1 truncate">
                    {convMeta.emoji ? convMeta.emoji + ' ' : ''}{convMeta.title}
                  </span>
                ) : (
                  <span className="flex-1 truncate font-mono text-xs text-white/40">{task.conversation_id}</span>
                )}
                <ExternalLink className="h-3.5 w-3.5 shrink-0 text-white/30" />
              </Link>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex shrink-0 items-center justify-between border-t border-white/[0.07] px-6 py-3">
          {confirming ? (
            <div className="flex items-center gap-2">
              <span className="text-xs text-white/50">Delete this task?</span>
              <button
                onClick={() => { onDelete(task.id); onClose() }}
                className="rounded-lg bg-red-500/80 px-3 py-1 text-xs font-medium text-white hover:bg-red-500"
              >
                Delete
              </button>
              <button
                onClick={() => setConfirming(false)}
                className="rounded-lg bg-white/10 px-3 py-1 text-xs font-medium text-white/60 hover:bg-white/15"
              >
                Cancel
              </button>
            </div>
          ) : (
            <button
              onClick={() => setConfirming(true)}
              className="text-xs text-white/30 transition-colors hover:text-red-400"
            >
              Delete task
            </button>
          )}
          <button onClick={onClose} className="btn-ghost px-4 py-2 text-sm">
            Close
          </button>
        </div>
      </div>
    </div>
  )
}
