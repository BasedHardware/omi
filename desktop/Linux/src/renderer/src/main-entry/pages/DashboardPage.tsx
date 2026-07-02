import React, { useEffect, useState } from 'react'
import { api } from '../../api/client'
import type { Goal, ScoreResponse } from '../../api/types'
import { CategoryChip } from '../../components/ui'
import { ScoreGauge } from '../../components/ScoreGauge'
import type { ScorePeriod } from '../../components/ScoreGauge'
import { greeting, timeAgo } from '../../lib/format'
import { useAuth } from '../../stores/auth'
import { useConversations } from '../../stores/conversations'
import { goalEmoji, goalProgress, progressColor } from '../../stores/goals'
import { useMemories } from '../../stores/memories'
import { useTasks } from '../../stores/tasks'
import type { Page } from '../App'

const SCORE_PERIOD: Record<'daily' | 'weekly' | 'overall', ScorePeriod> = {
  daily: 'Today',
  weekly: 'Last 7 days',
  overall: 'All time'
}

export function DashboardPage({ onNavigate }: { onNavigate: (p: Page) => void }) {
  const auth = useAuth((s) => s.state)
  const tasks = useTasks()
  const conversations = useConversations()
  const memories = useMemories()
  const [goals, setGoals] = useState<Goal[]>([])
  const [scores, setScores] = useState<ScoreResponse | null>(null)
  const [scoreTab, setScoreTab] = useState<'daily' | 'weekly' | 'overall'>('daily')

  useEffect(() => {
    void tasks.load()
    void conversations.load()
    void memories.load()
    api.listGoals().then(setGoals).catch(() => {})
    api.getScores().then(setScores).catch(() => {})
  }, [])

  const today = new Date().toDateString()
  const todayTasks = tasks.incomplete.slice(0, 6)

  return (
    <div style={{ height: '100%', overflowY: 'auto', padding: '32px 30px 28px' }}>
      <div className="page-title" style={{ marginBottom: 4 }}>
        {greeting(auth?.name)}
      </div>
      <div style={{ fontSize: 13, color: 'var(--text-quaternary)', marginBottom: 24 }}>
        {new Date().toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' })}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 20 }}>
        {/* Daily score */}
        <div className="card" style={{ padding: '20px 22px', minHeight: 170 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
            <span style={{ fontSize: 16, fontWeight: 600 }}>Daily Score</span>
            <div style={{ display: 'flex', gap: 5 }}>
              {(['daily', 'weekly', 'overall'] as const).map((t) => (
                <button
                  key={t}
                  className={`chip ${scoreTab === t ? 'active' : ''}`}
                  style={{ fontSize: 11, padding: '2px 9px' }}
                  onClick={() => setScoreTab(t)}
                >
                  {t === 'daily' ? 'Today' : t === 'weekly' ? 'Week' : 'All'}
                </button>
              ))}
            </div>
          </div>
          <div style={{ display: 'flex', justifyContent: 'center', paddingTop: 8 }}>
            <ScoreGauge data={scores?.[scoreTab]} size={170} period={SCORE_PERIOD[scoreTab]} />
          </div>
        </div>

        {/* Today's Tasks */}
        <DashCard title="Today's Tasks" action="View all" onAction={() => onNavigate('tasks')}>
          {todayTasks.length === 0 ? (
            <div style={{ color: 'var(--text-quaternary)', fontSize: 13, padding: '14px 0' }}>
              Nothing pending. Ask Omi to plan your day.
            </div>
          ) : (
            todayTasks.map((t) => {
              const done = !!t.completed
              return (
                <div
                  key={t.id}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 12,
                    borderRadius: 14,
                    background: 'rgba(37,37,37,0.45)',
                    padding: '10px 12px',
                    marginBottom: 8
                  }}
                >
                  <button
                    onClick={() => tasks.toggle(t)}
                    style={{
                      width: 18,
                      height: 18,
                      borderRadius: 9,
                      border: done ? 'none' : '1.6px solid var(--text-tertiary)',
                      background: done ? 'var(--purple-primary)' : 'transparent',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      flexShrink: 0
                    }}
                    title="Complete"
                  >
                    {done && (
                      <svg width={11} height={11} viewBox="0 0 24 24" fill="none" aria-hidden>
                        <path d="M5 12.5l4.5 4.5L19 7" stroke="#fff" strokeWidth={2.6} strokeLinecap="round" strokeLinejoin="round" />
                      </svg>
                    )}
                  </button>
                  <span
                    style={{
                      fontSize: 13,
                      color: done ? 'var(--text-quaternary)' : 'var(--text-secondary)',
                      textDecoration: done ? 'line-through' : 'none',
                      flex: 1,
                      minWidth: 0
                    }}
                  >
                    {t.description}
                  </span>
                  {t.due_at && (
                    <span
                      style={{
                        fontSize: 11,
                        color: new Date(t.due_at) < new Date() ? 'var(--error)' : 'var(--text-quaternary)'
                      }}
                    >
                      {new Date(t.due_at).toDateString() === today
                        ? 'Today'
                        : new Date(t.due_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
                    </span>
                  )}
                </div>
              )
            })
          )}
        </DashCard>

        {/* Recent Conversations */}
        <DashCard title="Recent Conversations" action="View All" onAction={() => onNavigate('conversations')}>
          {conversations.items.slice(0, 5).map((c) => (
            <div key={c.id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '7px 0' }}>
              <span style={{ fontSize: 16 }}>{c.structured?.emoji || '💬'}</span>
              <span
                style={{
                  fontSize: 13,
                  color: 'var(--text-secondary)',
                  flex: 1,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap'
                }}
              >
                {c.structured?.title || 'Untitled conversation'}
              </span>
              <span style={{ fontSize: 11, color: 'var(--text-quaternary)', flexShrink: 0 }}>
                {timeAgo(c.created_at)}
              </span>
            </div>
          ))}
          {conversations.items.length === 0 && (
            <div style={{ color: 'var(--text-quaternary)', fontSize: 13, padding: '14px 0' }}>
              Start recording to capture your first conversation.
            </div>
          )}
        </DashCard>

        {/* Goals */}
        <DashCard title="Goals">
          {goals.length === 0 ? (
            <div style={{ color: 'var(--text-quaternary)', fontSize: 13, padding: '14px 0' }}>
              No goals yet, create them from chat.
            </div>
          ) : (
            goals.slice(0, 4).map((g) => {
              const pct = goalProgress(g)
              const target = Math.round(g.target_value ?? 1)
              const current = Math.round(g.current_value ?? 0)
              return (
                <div key={g.id} style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '7px 0' }}>
                  <div
                    style={{
                      width: 36,
                      height: 36,
                      borderRadius: 12,
                      background: 'var(--bg-raised)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      fontSize: 16,
                      flexShrink: 0
                    }}
                  >
                    {goalEmoji(g.title)}
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 8, marginBottom: 7 }}>
                      <span
                        style={{
                          fontSize: 13,
                          fontWeight: 500,
                          color: 'var(--text-primary)',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap'
                        }}
                      >
                        {g.title}
                      </span>
                      <span className="tnum" style={{ fontSize: 11, color: 'var(--text-tertiary)', flexShrink: 0 }}>
                        {current}/{target}
                      </span>
                    </div>
                    <div style={{ height: 6, borderRadius: 3, background: 'rgba(255,255,255,0.12)' }}>
                      <div
                        style={{
                          width: `${pct}%`,
                          height: '100%',
                          borderRadius: 3,
                          background: progressColor(pct),
                          transition: 'width 0.3s ease'
                        }}
                      />
                    </div>
                  </div>
                </div>
              )
            })
          )}
        </DashCard>

        {/* Memories */}
        <DashCard title="Memories" action="View all" onAction={() => onNavigate('memories')}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, padding: '4px 0 10px' }}>
            <span style={{ fontSize: 30, fontWeight: 700 }}>{memories.items.length}</span>
            <span style={{ fontSize: 12, color: 'var(--text-quaternary)' }}>things Omi remembers about you</span>
          </div>
          {memories.items.slice(0, 3).map((m) => (
            <div key={m.id} style={{ display: 'flex', gap: 8, padding: '6px 0', alignItems: 'flex-start' }}>
              <CategoryChip label={m.category || 'memory'} />
              <span
                style={{
                  fontSize: 12.5,
                  color: 'var(--text-tertiary)',
                  overflow: 'hidden',
                  display: '-webkit-box',
                  WebkitLineClamp: 2,
                  WebkitBoxOrient: 'vertical'
                }}
              >
                {m.content}
              </span>
            </div>
          ))}
        </DashCard>
      </div>
    </div>
  )
}

function DashCard({
  title,
  action,
  onAction,
  children
}: {
  title: string
  action?: string
  onAction?: () => void
  children: React.ReactNode
}) {
  return (
    <div className="card" style={{ padding: '20px 22px', minHeight: 170 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
        <span style={{ fontSize: 16, fontWeight: 600 }}>{title}</span>
        {action && (
          <button onClick={onAction} style={{ fontSize: 12, color: 'var(--purple-secondary)' }}>
            {action}
          </button>
        )}
      </div>
      {children}
    </div>
  )
}
