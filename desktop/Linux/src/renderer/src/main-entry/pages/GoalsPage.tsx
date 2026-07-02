import React, { useEffect, useRef, useState } from 'react'
import { IconPlus, IconTrash } from '../../components/Icons'
import { EmptyState, Spinner } from '../../components/ui'
import { goalEmoji, goalProgress, progressColor, useGoals } from '../../stores/goals'
import type { Goal } from '../../api/types'

export function GoalsPage() {
  const store = useGoals()
  const [showCreate, setShowCreate] = useState(false)

  useEffect(() => {
    void store.load()
  }, [])

  return (
    <div style={{ height: '100%', overflowY: 'auto', padding: '44px 26px 26px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <div>
          <div style={{ fontSize: 19, fontWeight: 700 }}>Goals</div>
          <div style={{ fontSize: 12.5, color: 'var(--text-quaternary)', marginTop: 2 }}>
            Track what you're working toward, drag a bar to update progress
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {store.loading && <Spinner size={15} />}
          <button className="btn-primary" onClick={() => setShowCreate(true)}>
            <IconPlus size={14} /> Add goal
          </button>
        </div>
      </div>

      {store.goals.length === 0 && !store.loading ? (
        <EmptyState title="No goals yet" subtitle="Add a goal to start tracking progress. Boolean (done/not done) or numeric targets." />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12, maxWidth: 720 }}>
          {store.goals.map((g) => (
            <GoalRow key={g.id} goal={g} />
          ))}
        </div>
      )}

      {showCreate && <CreateGoalSheet onClose={() => setShowCreate(false)} />}
    </div>
  )
}

function GoalRow({ goal }: { goal: Goal }) {
  const store = useGoals()
  const pct = goalProgress(goal)
  const color = progressColor(pct)
  const barRef = useRef<HTMLDivElement | null>(null)
  const [dragPct, setDragPct] = useState<number | null>(null)
  const shown = dragPct ?? pct

  const onDrag = (clientX: number) => {
    const el = barRef.current
    if (!el) return
    const rect = el.getBoundingClientRect()
    const frac = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width))
    setDragPct(frac * 100)
  }

  const commit = () => {
    if (dragPct === null) return
    const min = goal.min_value ?? 0
    const target = goal.target_value ?? 1
    const value = Math.round(min + (dragPct / 100) * (target - min))
    setDragPct(null)
    void store.setProgress(goal.id, value)
  }

  const isBoolean = goal.goal_type === 'boolean'

  return (
    <div
      style={{
        padding: '12px 14px',
        borderRadius: 16,
        background: 'rgba(37, 37, 37, 0.72)',
        border: '1px solid var(--border)',
        display: 'flex',
        gap: 12,
        alignItems: 'center'
      }}
      onMouseEnter={(e) => (e.currentTarget.style.background = 'rgba(37, 37, 37, 0.9)')}
      onMouseLeave={(e) => (e.currentTarget.style.background = 'rgba(37, 37, 37, 0.72)')}
    >
      <div
        style={{
          width: 36,
          height: 36,
          borderRadius: 12,
          background: 'rgba(31, 31, 37, 0.9)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: 16,
          flexShrink: 0
        }}
      >
        {goalEmoji(goal.title)}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 6 }}>
          <span style={{ fontSize: 13, fontWeight: 500, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {goal.title}
          </span>
          <span
            className="tnum"
            style={{
              fontSize: 11.5,
              fontWeight: dragPct !== null ? 600 : 400,
              color: dragPct !== null ? 'var(--text-primary)' : 'var(--text-quaternary)',
              transition: 'color 0.15s ease'
            }}
          >
            {isBoolean
              ? (goal.current_value ?? 0) >= 1
                ? 'Done'
                : 'Not done'
              : `${Math.round((shown / 100) * ((goal.target_value ?? 1) - (goal.min_value ?? 0)) + (goal.min_value ?? 0))}/${goal.target_value ?? 1}${goal.unit ? ' ' + goal.unit : ''}`}
          </span>
        </div>
        {isBoolean ? (
          <button
            className={`toggle ${(goal.current_value ?? 0) >= 1 ? 'on' : ''}`}
            onClick={() => store.setProgress(goal.id, (goal.current_value ?? 0) >= 1 ? 0 : 1)}
          />
        ) : (
          <div
            ref={barRef}
            onMouseDown={(e) => {
              onDrag(e.clientX)
              const move = (ev: MouseEvent) => onDrag(ev.clientX)
              const up = () => {
                window.removeEventListener('mousemove', move)
                window.removeEventListener('mouseup', up)
                commit()
              }
              window.addEventListener('mousemove', move)
              window.addEventListener('mouseup', up)
            }}
            style={{ height: dragPct === null ? 6 : 8, borderRadius: 3, background: 'rgba(255,255,255,0.12)', cursor: 'pointer', position: 'relative', transition: 'height 0.15s ease' }}
          >
            <div style={{ width: `${shown}%`, height: '100%', borderRadius: 3, background: color, transition: dragPct === null ? 'width 0.2s ease' : 'none' }} />
            {/* 14px white drag thumb, like the Mac GoalsWidget slider knob. */}
            <div
              style={{
                position: 'absolute',
                top: '50%',
                left: `${shown}%`,
                width: 14,
                height: 14,
                borderRadius: 7,
                background: '#fff',
                boxShadow: '0 1px 4px rgba(0,0,0,0.35)',
                transform: `translate(-50%, -50%) scale(${dragPct === null ? 0.85 : 1})`,
                opacity: dragPct === null ? 0 : 1,
                pointerEvents: 'none',
                transition: dragPct === null ? 'opacity 0.15s ease, transform 0.15s ease' : 'none'
              }}
            />
          </div>
        )}
      </div>
      <button
        onClick={() => store.remove(goal.id)}
        title="Delete goal"
        style={{ color: 'var(--text-quaternary)', padding: 4, flexShrink: 0 }}
        onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--error)')}
        onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--text-quaternary)')}
      >
        <IconTrash size={14} />
      </button>
    </div>
  )
}

function CreateGoalSheet({ onClose }: { onClose: () => void }) {
  const store = useGoals()
  const [title, setTitle] = useState('')
  const [type, setType] = useState<'boolean' | 'numeric'>('numeric')
  const [current, setCurrent] = useState('0')
  const [target, setTarget] = useState('10')
  const [unit, setUnit] = useState('')
  const [saving, setSaving] = useState(false)

  const save = async () => {
    if (!title.trim()) return
    setSaving(true)
    await store.create({
      title: title.trim(),
      goalType: type,
      current: type === 'boolean' ? 0 : parseFloat(current) || 0,
      target: type === 'boolean' ? 1 : parseFloat(target) || 1,
      unit: unit.trim() || undefined
    })
    setSaving(false)
    onClose()
  }

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.45)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 100
      }}
      onClick={onClose}
    >
      <div className="card" style={{ width: 400, padding: 20, background: 'var(--bg-raised)' }} onClick={(e) => e.stopPropagation()}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
          <span style={{ fontSize: 24 }}>{goalEmoji(title)}</span>
          <span style={{ fontSize: 16, fontWeight: 700 }}>New goal</span>
        </div>
        <input autoFocus placeholder="Goal title" value={title} onChange={(e) => setTitle(e.target.value)} style={{ width: '100%', marginBottom: 12 }} />
        <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
          <button className={`chip ${type === 'numeric' ? 'active' : ''}`} onClick={() => setType('numeric')}>
            Numeric
          </button>
          <button className={`chip ${type === 'boolean' ? 'active' : ''}`} onClick={() => setType('boolean')}>
            Done / not done
          </button>
        </div>
        {type === 'numeric' && (
          <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
            <label style={{ flex: 1, fontSize: 12, color: 'var(--text-tertiary)' }}>
              Current
              <input type="number" value={current} onChange={(e) => setCurrent(e.target.value)} style={{ width: '100%', marginTop: 4 }} />
            </label>
            <label style={{ flex: 1, fontSize: 12, color: 'var(--text-tertiary)' }}>
              Target
              <input type="number" value={target} onChange={(e) => setTarget(e.target.value)} style={{ width: '100%', marginTop: 4 }} />
            </label>
            <label style={{ flex: 1, fontSize: 12, color: 'var(--text-tertiary)' }}>
              Unit
              <input placeholder="e.g. $" value={unit} onChange={(e) => setUnit(e.target.value)} style={{ width: '100%', marginTop: 4 }} />
            </label>
          </div>
        )}
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <button className="btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button className="btn-primary" onClick={save} disabled={!title.trim() || saving}>
            {saving ? 'Saving…' : 'Add goal'}
          </button>
        </div>
      </div>
    </div>
  )
}
