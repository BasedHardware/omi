import React, { useEffect, useState } from 'react'
import { EmptyState, Toggle } from '../../components/ui'
import { clockTime } from '../../lib/format'
import { useSettings } from '../../stores/settings'
import type { FocusSession, FocusStatus } from '../../../../shared/types'

// Inline SF-Symbols-style icons for the focus banner and stat cards.
type SvgProps = { size?: number }
const svgBase = (size: number) => ({
  width: size,
  height: size,
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.8,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const
})
const IconEye = ({ size = 16 }: SvgProps) => (
  <svg {...svgBase(size)}>
    <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7z" />
    <circle cx="12" cy="12" r="3" />
  </svg>
)
const IconEyeSlash = ({ size = 16 }: SvgProps) => (
  <svg {...svgBase(size)}>
    <path d="M2 12s3.5-7 10-7c1.7 0 3.2.5 4.5 1.2M22 12s-3.5 7-10 7c-1.7 0-3.2-.5-4.5-1.2" />
    <path d="M9.9 9.9a3 3 0 0 0 4.2 4.2" />
    <path d="M3 3l18 18" />
  </svg>
)
const IconPie = ({ size = 16 }: SvgProps) => (
  <svg {...svgBase(size)}>
    <path d="M12 3v9l6.5 6.5" />
    <path d="M12 3a9 9 0 1 0 9 9h-9" />
  </svg>
)
const IconClock = ({ size = 16 }: SvgProps) => (
  <svg {...svgBase(size)}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 7v5l3 2" />
  </svg>
)

interface Summary {
  focusedMinutes: number
  distractedMinutes: number
  focusRate: number
  sessions: number
  topDistractions: { app: string; minutes: number }[]
}

export function FocusPage() {
  const { settings, update } = useSettings()
  const [status, setStatus] = useState<FocusStatus | null>(null)
  const [sessions, setSessions] = useState<FocusSession[]>([])
  const [summary, setSummary] = useState<Summary | null>(null)

  const refresh = () => {
    void window.omi.focus.sessions().then((s) => setSessions(s as FocusSession[]))
    void window.omi.focus.summary().then((s) => setSummary(s as Summary))
    void window.omi.focus.status().then((s) => setStatus(s as FocusStatus))
  }

  useEffect(() => {
    refresh()
    const unsub = window.omi.focus.onStatus((s) => {
      setStatus(s as FocusStatus)
      refresh()
    })
    return unsub
  }, [])

  if (!settings) return null
  const focused = status?.current === 'focused'

  return (
    <div style={{ height: '100%', overflowY: 'auto', padding: '44px 26px 26px' }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 16 }}>
        <div>
          <div style={{ fontSize: 19, fontWeight: 700 }}>Focus</div>
          <div style={{ fontSize: 12.5, color: 'var(--text-quaternary)', marginTop: 2 }}>
            Omi watches what's on screen and nudges you with a glow when you drift
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 12.5, color: 'var(--text-tertiary)' }}>
            {settings.focusEnabled
              ? `Monitoring · ${summary?.sessions ?? 0} session${(summary?.sessions ?? 0) === 1 ? '' : 's'} today`
              : 'Off'}
          </span>
          <Toggle
            on={settings.focusEnabled}
            onChange={(v) => void update({ focusEnabled: v, rewindEnabled: v ? true : settings.rewindEnabled })}
          />
        </div>
      </div>

      {!settings.focusEnabled ? (
        <div className="section" style={{ padding: 20, lineHeight: 1.6 }}>
          <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 6 }}>Focus monitoring is off</div>
          <div style={{ fontSize: 13, color: 'var(--text-tertiary)' }}>
            When on, Omi periodically checks whether your screen shows focused work or a distraction (social media,
            video, games). On a slip it flashes a red glow around your screen; when you get back to work, a green
            one. Uses the same on-device screen capture as Rewind.
          </div>
          <button
            className="btn-primary"
            style={{ marginTop: 14 }}
            onClick={() => void update({ focusEnabled: true, rewindEnabled: true })}
          >
            Enable focus monitoring
          </button>
        </div>
      ) : (
        <>
          {/* Current status banner, 56px tinted eye disc, ported from FocusPage.swift currentStatusBanner */}
          {(() => {
            const accent = !status?.current ? 'var(--success)' : focused ? 'var(--success)' : 'var(--warning)'
            const accentRgb = !status?.current ? '16,185,129' : focused ? '16,185,129' : '245,158,11'
            return (
              <div
                style={{
                  padding: 20,
                  marginBottom: 16,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 16,
                  borderRadius: 16,
                  background: `rgba(${accentRgb},0.08)`,
                  border: `1px solid rgba(${accentRgb},0.2)`
                }}
              >
                <div
                  style={{
                    width: 56,
                    height: 56,
                    borderRadius: 28,
                    flexShrink: 0,
                    background: `rgba(${accentRgb},0.2)`,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    color: accent
                  }}
                >
                  {focused || !status?.current ? <IconEye size={24} /> : <IconEyeSlash size={24} />}
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 20, fontWeight: 700, color: 'var(--text-primary)' }}>
                    {status?.current ? (focused ? 'Focused' : 'Distracted') : 'Waiting to analyze…'}
                  </div>
                  {status?.currentApp && (
                    <div style={{ fontSize: 14, color: 'var(--text-secondary)', marginTop: 2 }}>{status.currentApp}</div>
                  )}
                </div>
                {focused && (
                  <span
                    style={{
                      width: 12,
                      height: 12,
                      borderRadius: 6,
                      background: 'var(--success)',
                      opacity: 0.8,
                      animation: 'pulse 1.8s ease-in-out infinite'
                    }}
                  />
                )}
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>Glow</span>
                  <Toggle on={settings.focusGlow} onChange={(v) => void update({ focusGlow: v })} />
                </div>
              </div>
            )
          })()}

          {/* Today's summary */}
          <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-quaternary)', textTransform: 'uppercase', letterSpacing: 0.6, marginBottom: 8 }}>
            Today's Summary
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10, marginBottom: 18 }}>
            <StatCard label="Focus Time" value={`${summary?.focusedMinutes ?? 0}`} unit="min" color="var(--success)" icon={<IconEye size={15} />} />
            <StatCard label="Distracted" value={`${summary?.distractedMinutes ?? 0}`} unit="min" color="var(--warning)" icon={<IconEyeSlash size={15} />} />
            <StatCard label="Focus Rate" value={`${summary?.focusRate ?? 0}`} unit="%" color="var(--purple-secondary)" icon={<IconPie size={15} />} />
            <StatCard label="Sessions" value={`${summary?.sessions ?? 0}`} unit="" color="var(--info)" icon={<IconClock size={15} />} />
          </div>

          {(summary?.topDistractions.length ?? 0) > 0 && (
            <>
              <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-quaternary)', textTransform: 'uppercase', letterSpacing: 0.6, marginBottom: 8 }}>
                Top Distractions
              </div>
              <div className="section" style={{ overflow: 'hidden', marginBottom: 18 }}>
                {summary!.topDistractions.map((d, i) => (
                  <div key={i} style={{ display: 'flex', justifyContent: 'space-between', padding: '10px 14px', borderBottom: i < summary!.topDistractions.length - 1 ? '1px solid var(--border)' : 'none' }}>
                    <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>{d.app}</span>
                    <span style={{ fontSize: 12.5, color: 'var(--warning)' }}>{d.minutes}m</span>
                  </div>
                ))}
              </div>
            </>
          )}

          {/* Session history */}
          <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-quaternary)', textTransform: 'uppercase', letterSpacing: 0.6, marginBottom: 8 }}>
            Sessions
          </div>
          {sessions.length === 0 ? (
            <EmptyState title="No sessions yet" subtitle="Focus checks run every minute or so while you work." />
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {sessions.slice(0, 60).map((s) => (
                <div key={s.id} className="section" style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '9px 13px' }}>
                  <span style={{ width: 9, height: 9, borderRadius: 5, background: s.status === 'focused' ? 'var(--success)' : 'var(--warning)', flexShrink: 0 }} />
                  <span style={{ fontSize: 13, color: 'var(--text-secondary)', minWidth: 90 }}>{s.appOrSite}</span>
                  <span style={{ flex: 1, fontSize: 12, color: 'var(--text-quaternary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {s.message || s.description}
                  </span>
                  <span style={{ fontSize: 11.5, color: 'var(--text-quaternary)' }}>{clockTime(new Date(s.ts).toISOString())}</span>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}

function StatCard({
  label,
  value,
  unit,
  color,
  icon
}: {
  label: string
  value: string
  unit?: string
  color: string
  icon?: React.ReactNode
}) {
  return (
    <div className="card" style={{ padding: '12px 14px' }}>
      <div style={{ color, marginBottom: 6, display: 'inline-flex' }}>{icon}</div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 3 }}>
        <span className="tnum" style={{ fontSize: 22, fontWeight: 700, color }}>
          {value}
        </span>
        {unit ? <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-tertiary)' }}>{unit}</span> : null}
      </div>
      <div style={{ fontSize: 11.5, color: 'var(--text-quaternary)', marginTop: 2 }}>{label}</div>
    </div>
  )
}
