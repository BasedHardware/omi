import React, { useEffect, useMemo, useRef, useState } from 'react'
import { IconPlus, IconTrash } from '../../components/Icons'
import { EmptyState, Spinner } from '../../components/ui'
import { useTasks } from '../../stores/tasks'
import type { TaskActionItem } from '../../api/types'

// Priority metadata, ported from DailyTaskCreationSheet.swift (high=red, medium=orange, low=blue).
const PRIORITIES = ['high', 'medium', 'low'] as const
type Priority = (typeof PRIORITIES)[number]

function priorityColor(level: string): string {
  switch (level) {
    case 'high':
      return 'var(--error)'
    case 'medium':
      return 'var(--warning)'
    case 'low':
      return 'var(--info)'
    default:
      return 'var(--text-quaternary)'
  }
}

// Inline SF-Symbols-style flag. Filled for high priority, outline otherwise.
function IconFlag({ size = 13, filled = false }: { size?: number; filled?: boolean }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill={filled ? 'currentColor' : 'none'}
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M5 21V4" />
      <path d="M5 4h11l-2 4 2 4H5" fill={filled ? 'currentColor' : 'none'} />
    </svg>
  )
}

export function TasksPage() {
  const store = useTasks()
  const [draft, setDraft] = useState('')
  const [draftDue, setDraftDue] = useState('')
  const [draftPriority, setDraftPriority] = useState<Priority>('medium')
  const [showCompleted, setShowCompleted] = useState(false)

  const addDraft = () => {
    if (!draft.trim()) return
    void store.add(draft, draftDue ? new Date(draftDue).toISOString() : undefined, draftPriority)
    setDraft('')
    setDraftDue('')
    setDraftPriority('medium')
  }

  useEffect(() => {
    void store.load()
  }, [])

  const groups = useMemo(() => {
    const now = new Date()
    const todayEnd = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1)
    const today: TaskActionItem[] = []
    const upcoming: TaskActionItem[] = []
    const someday: TaskActionItem[] = []
    for (const t of store.incomplete) {
      if (!t.due_at) someday.push(t)
      else {
        const due = new Date(t.due_at)
        // Overdue items fold into Today so nothing slips out of view (matches Mac TaskCategory.today).
        if (due < todayEnd) today.push(t)
        else upcoming.push(t)
      }
    }
    return { today, upcoming, someday }
  }, [store.incomplete])

  return (
    <div style={{ height: '100%', overflowY: 'auto', padding: '44px 26px 26px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
        <div>
          <div style={{ fontSize: 19, fontWeight: 700 }}>Tasks</div>
          <div style={{ fontSize: 12.5, color: 'var(--text-quaternary)', marginTop: 2 }}>
            {store.incomplete.length} open · extracted from your conversations and screen, or added here
          </div>
        </div>
        {store.loading && <Spinner size={15} />}
      </div>

      <div style={{ display: 'flex', gap: 8, marginBottom: 16, alignItems: 'center' }}>
        <input
          value={draft}
          placeholder="Add a task…"
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') addDraft()
          }}
          style={{ flex: 1 }}
        />
        <PriorityPicker value={draftPriority} onChange={(p) => setDraftPriority(p)} />
        <input
          type="date"
          value={draftDue}
          onChange={(e) => setDraftDue(e.target.value)}
          title="Due date"
          style={{ width: 140, colorScheme: 'dark' }}
        />
        <button className="btn-primary" disabled={!draft.trim()} onClick={addDraft}>
          <IconPlus size={14} /> Add
        </button>
      </div>

      {/* Staged (AI-proposed) tasks */}
      {store.staged.length > 0 && (
        <div className="section" style={{ padding: 12, marginBottom: 18, borderColor: 'rgba(139,92,246,0.35)' }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--purple-secondary)', marginBottom: 8 }}>
            Omi suggests · {store.staged.length}
          </div>
          {store.staged.map((s) => (
            <div key={s.id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '6px 0' }}>
              <span style={{ flex: 1, fontSize: 13, color: 'var(--text-secondary)' }}>{s.description}</span>
              <button
                onClick={() => void store.acceptStaged(s.id)}
                style={{ fontSize: 12, color: 'var(--success)', padding: '3px 9px', background: 'rgba(16,185,129,0.12)', borderRadius: 8 }}
              >
                Add
              </button>
              <button
                onClick={() => void store.dismissStaged(s.id)}
                style={{ fontSize: 12, color: 'var(--text-quaternary)', padding: '3px 9px' }}
              >
                Dismiss
              </button>
            </div>
          ))}
        </div>
      )}

      {store.incomplete.length === 0 && !store.loading && (
        <EmptyState title="All clear" subtitle="New tasks from conversations and Ask Omi land here." />
      )}

      <TaskGroup title="Today" tasks={groups.today} accent="var(--text-primary)" />
      <TaskGroup title="Upcoming" tasks={groups.upcoming} />
      <TaskGroup title="No due date" tasks={groups.someday} />

      <button
        onClick={() => setShowCompleted((v) => !v)}
        style={{ fontSize: 12.5, color: 'var(--text-quaternary)', margin: '10px 0' }}
      >
        {showCompleted ? '▾' : '▸'} Completed ({store.completed.length})
      </button>
      {showCompleted && <TaskGroup title="" tasks={store.completed} completed />}
    </div>
  )
}

// Compact High/Medium/Low flag picker. Used on the add-input and inline on each task.
function PriorityPicker({
  value,
  onChange,
  compact
}: {
  value: string | null | undefined
  onChange: (p: Priority) => void
  compact?: boolean
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement | null>(null)
  const current = (value ?? 'medium') as Priority

  useEffect(() => {
    if (!open) return
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    window.addEventListener('mousedown', onDoc)
    return () => window.removeEventListener('mousedown', onDoc)
  }, [open])

  return (
    <div ref={ref} style={{ position: 'relative', flexShrink: 0 }}>
      <button
        onClick={() => setOpen((v) => !v)}
        title={`Priority: ${current}`}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 5,
          height: compact ? 22 : 34,
          padding: compact ? '0 7px' : '0 11px',
          borderRadius: compact ? 8 : 10,
          background: compact ? 'transparent' : 'var(--bg-tertiary)',
          border: compact ? 'none' : '1px solid var(--border)',
          color: priorityColor(current)
        }}
      >
        <IconFlag size={compact ? 12 : 13} filled={current === 'high'} />
        {!compact && (
          <span style={{ fontSize: 12.5, color: 'var(--text-secondary)', textTransform: 'capitalize' }}>{current}</span>
        )}
      </button>
      {open && (
        <div
          style={{
            position: 'absolute',
            top: 'calc(100% + 6px)',
            right: 0,
            zIndex: 40,
            background: 'var(--bg-raised)',
            border: '1px solid var(--border)',
            borderRadius: 12,
            padding: 5,
            boxShadow: 'var(--shadow-content)',
            minWidth: 132
          }}
        >
          {PRIORITIES.map((level) => {
            const selected = current === level
            return (
              <button
                key={level}
                onClick={() => {
                  onChange(level)
                  setOpen(false)
                }}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  width: '100%',
                  padding: '7px 9px',
                  borderRadius: 8,
                  background: selected ? priorityColor(level) : 'transparent',
                  color: selected ? '#fff' : 'var(--text-primary)'
                }}
                onMouseEnter={(e) => {
                  if (!selected) e.currentTarget.style.background = 'var(--bg-tertiary)'
                }}
                onMouseLeave={(e) => {
                  if (!selected) e.currentTarget.style.background = 'transparent'
                }}
              >
                <span style={{ color: selected ? '#fff' : priorityColor(level), display: 'inline-flex' }}>
                  <IconFlag size={12} filled={level === 'high'} />
                </span>
                <span style={{ fontSize: 13, textTransform: 'capitalize' }}>{level}</span>
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}

function TaskGroup({
  title,
  tasks,
  accent,
  completed
}: {
  title: string
  tasks: TaskActionItem[]
  accent?: string
  completed?: boolean
}) {
  const store = useTasks()
  if (tasks.length === 0) return null
  return (
    <div style={{ marginBottom: 18 }}>
      {title && (
        <div
          style={{
            fontSize: 13,
            fontWeight: 600,
            color: accent || 'var(--text-tertiary)',
            marginBottom: 7
          }}
        >
          {title} · {tasks.length}
        </div>
      )}
      <div className="section" style={{ overflow: 'hidden' }}>
        {tasks.map((t, i) => (
          <div
            key={t.id}
            tabIndex={completed ? undefined : 0}
            onKeyDown={(e) => {
              if (completed) return
              if (e.key === 'Tab') {
                e.preventDefault()
                void store.setIndent(t.id, (t.indent_level ?? 0) + (e.shiftKey ? -1 : 1))
              }
            }}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 11,
              padding: '11px 14px',
              paddingLeft: 14 + (t.indent_level ?? 0) * 28,
              borderBottom: i < tasks.length - 1 ? '1px solid var(--border)' : 'none',
              outline: 'none'
            }}
          >
            {(t.indent_level ?? 0) > 0 && (
              <span style={{ width: 2, alignSelf: 'stretch', background: 'var(--border-strong)', borderRadius: 1, marginRight: 2 }} />
            )}
            <button
              onClick={() => void store.toggle(t)}
              title={completed ? 'Reopen' : 'Complete'}
              style={{
                width: 18,
                height: 18,
                borderRadius: 9,
                flexShrink: 0,
                border: completed ? 'none' : '1.6px solid var(--text-quaternary)',
                background: completed ? 'var(--success)' : 'transparent',
                color: '#fff',
                fontSize: 11,
                lineHeight: '18px'
              }}
            >
              {completed ? '✓' : ''}
            </button>
            <span
              className="text-selectable"
              style={{
                flex: 1,
                fontSize: 13.5,
                color: completed ? 'var(--text-quaternary)' : 'var(--text-secondary)',
                textDecoration: completed ? 'line-through' : 'none',
                minWidth: 0
              }}
            >
              {t.description}
            </span>
            {!completed && <PriorityPicker compact value={t.priority} onChange={(p) => void store.setPriority(t.id, p)} />}
            {t.due_at && !completed && (
              <span style={{ fontSize: 11.5, color: 'var(--text-quaternary)', flexShrink: 0 }}>
                {new Date(t.due_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
              </span>
            )}
            <button
              onClick={() => void store.remove(t.id)}
              title="Delete"
              style={{ color: 'var(--text-quaternary)', padding: 2, flexShrink: 0 }}
              onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--error)')}
              onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--text-quaternary)')}
            >
              <IconTrash size={13} />
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}
