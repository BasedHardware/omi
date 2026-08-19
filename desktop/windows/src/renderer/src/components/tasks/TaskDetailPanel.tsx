import { Link } from 'react-router-dom'
import { Check, MessageSquare, Pencil, Trash2, X, Film } from 'lucide-react'
import type { ActionItemRecord } from '../../../../shared/types'
import {
  availableActions,
  contextBlocks,
  detailFields,
  isPriorityEditable,
  sourceLinks,
  whyOmiAddedThis
} from '../../lib/taskDetailPolicy'
import { PRIORITY_LABEL, PRIORITY_ORDER, normalizePriority } from '../../lib/taskFields'

// Task detail panel (mac parity: TaskDetailPanel.swift). A 360px trailing panel:
// header with live status, the task text, editable priority chips (hidden once
// completed, like mac), "Why Omi added this", navigable sources, the read-only
// details table, captured context, and the action list. The page owns layout and
// mutual exclusion with the investigate chat; this renders one task and calls up.

export type TaskDetailPanelProps = {
  task: ActionItemRecord
  conversationTitle?: string
  busy: boolean
  hasChat: boolean
  onClose: () => void
  onToggle: (task: ActionItemRecord) => void
  onEdit: (task: ActionItemRecord) => void
  onDelete: (task: ActionItemRecord) => void
  onInvestigate: (task: ActionItemRecord) => void
  onPriorityChange: (task: ActionItemRecord, priority: 'high' | 'medium' | 'low') => void
}

function Section({
  title,
  children
}: {
  title: string
  children: React.ReactNode
}): React.JSX.Element {
  return (
    <section className="border-t border-white/10 px-4 py-3">
      <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-white/40">
        {title}
      </h3>
      {children}
    </section>
  )
}

export function TaskDetailPanel({
  task,
  conversationTitle,
  busy,
  hasChat,
  onClose,
  onToggle,
  onEdit,
  onDelete,
  onInvestigate,
  onPriorityChange
}: TaskDetailPanelProps): React.JSX.Element {
  const actions = availableActions(task, { hasChat })
  const links = sourceLinks(task)
  const fields = detailFields(task)
  const context = contextBlocks(task)
  const currentPriority = normalizePriority(task.priority)

  return (
    <aside
      data-testid="task-detail-panel"
      className="flex h-full w-[360px] shrink-0 flex-col overflow-y-auto border-l border-white/10 bg-black/30"
    >
      <div className="flex items-start justify-between px-4 py-3">
        <div>
          <h2 className="text-sm font-semibold text-white/90">Task details</h2>
          <p className="text-[11px] text-white/45">{task.completed ? 'Completed' : 'Active'}</p>
        </div>
        <button
          data-testid="task-detail-close"
          onClick={onClose}
          className="rounded-md p-1 text-white/40 hover:bg-white/5 hover:text-white/80"
          aria-label="Close task details"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <Section title="Task">
        <p
          className={`select-text text-sm leading-relaxed ${task.completed ? 'text-white/45 line-through' : 'text-white/90'}`}
        >
          {task.description}
        </p>
      </Section>

      {isPriorityEditable(task) && (
        <Section title="Priority">
          <div className="flex items-center gap-1.5">
            {PRIORITY_ORDER.map((p) => {
              const selected = currentPriority === p
              return (
                <button
                  key={p}
                  data-testid={`task-detail-priority-${p}`}
                  aria-pressed={selected}
                  disabled={busy}
                  onClick={() => {
                    if (!selected) onPriorityChange(task, p)
                  }}
                  className={`rounded-xl border px-3 py-1.5 text-xs transition-colors ${
                    selected
                      ? 'border-white/40 bg-white/15 text-white'
                      : 'border-white/15 text-white/55 hover:bg-white/5 hover:text-white/80'
                  } ${busy ? 'opacity-50' : ''}`}
                >
                  {PRIORITY_LABEL[p]}
                </button>
              )
            })}
          </div>
        </Section>
      )}

      <Section title="Why Omi added this">
        <p data-testid="task-detail-why" className="text-xs leading-relaxed text-white/60">
          {whyOmiAddedThis(task.source)}
        </p>
      </Section>

      <Section title={`${links.length} linked source${links.length === 1 ? '' : 's'}`}>
        {links.length === 0 ? (
          <p className="text-xs text-white/40">No navigable source was attached to this task.</p>
        ) : (
          <ul className="space-y-1.5">
            {links.map((link, i) => (
              <li key={`${link.kind}-${i}`}>
                {link.kind === 'conversation' ? (
                  <Link
                    data-testid={`task-detail-source-${i}`}
                    to={`/conversations/${link.id}`}
                    className="flex items-center gap-2 rounded-lg border border-white/10 px-3 py-2 text-xs text-white/70 hover:bg-white/5 hover:text-white"
                  >
                    <MessageSquare className="h-3.5 w-3.5 shrink-0 text-white/40" />
                    <span className="min-w-0">
                      <span className="block truncate">{conversationTitle || link.title}</span>
                      <span className="block text-[10px] text-white/35">{link.subtitle}</span>
                    </span>
                  </Link>
                ) : (
                  <Link
                    data-testid={`task-detail-source-${i}`}
                    to="/rewind"
                    className="flex items-center gap-2 rounded-lg border border-white/10 px-3 py-2 text-xs text-white/70 hover:bg-white/5 hover:text-white"
                  >
                    <Film className="h-3.5 w-3.5 shrink-0 text-white/40" />
                    <span className="min-w-0">
                      <span className="block truncate">{link.title}</span>
                      <span className="block text-[10px] text-white/35">{link.subtitle}</span>
                    </span>
                  </Link>
                )}
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="Details">
        <dl className="space-y-1.5">
          {fields.map((f) => (
            <div key={f.label} className="flex items-baseline justify-between gap-3 text-xs">
              <dt className="shrink-0 text-white/40">{f.label}</dt>
              <dd className="min-w-0 truncate text-right text-white/75">{f.value}</dd>
            </div>
          ))}
        </dl>
      </Section>

      {context.length > 0 && (
        <Section title="Context">
          <div className="space-y-2">
            {context.map((b) => (
              <div key={b.label}>
                <p className="text-[10px] font-medium uppercase tracking-wide text-white/35">
                  {b.label}
                </p>
                <p className="mt-0.5 select-text text-xs leading-relaxed text-white/65">{b.text}</p>
              </div>
            ))}
          </div>
        </Section>
      )}

      <Section title="Actions">
        <div className="space-y-1.5">
          {actions.includes('toggleCompletion') && (
            <button
              data-testid="task-detail-toggle"
              disabled={busy}
              onClick={() => onToggle(task)}
              className="btn-ghost w-full justify-start px-3 py-2 text-xs disabled:opacity-50"
            >
              <Check className="h-3.5 w-3.5" />
              {task.completed ? 'Mark as active' : 'Mark complete'}
            </button>
          )}
          {actions.includes('edit') && (
            <button
              data-testid="task-detail-edit"
              disabled={busy}
              onClick={() => onEdit(task)}
              className="btn-ghost w-full justify-start px-3 py-2 text-xs disabled:opacity-50"
            >
              <Pencil className="h-3.5 w-3.5" />
              Edit task
            </button>
          )}
          {actions.includes('investigate') && (
            <button
              data-testid="task-detail-chat"
              disabled={busy}
              onClick={() => onInvestigate(task)}
              className="btn-ghost w-full justify-start px-3 py-2 text-xs disabled:opacity-50"
            >
              <MessageSquare className="h-3.5 w-3.5" />
              Investigate with Omi
            </button>
          )}
          {actions.includes('delete') && (
            <button
              data-testid="task-detail-delete"
              disabled={busy}
              onClick={() => onDelete(task)}
              className="btn-ghost w-full justify-start px-3 py-2 text-xs text-rose-300/80 hover:text-rose-300 disabled:opacity-50"
            >
              <Trash2 className="h-3.5 w-3.5" />
              Delete task
            </button>
          )}
        </div>
      </Section>
    </aside>
  )
}
