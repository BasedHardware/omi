import React from 'react'
import type { ScoreData } from '../api/types'

// Semicircle productivity gauge, ported from DailyScoreWidget.swift (ScoreWidget).
// Color tiers use SwiftUI system colors: green #34C759 (>=80), lime #CCCC00 (60-79),
// orange #FF9500 (40-59), red #FF3B30 (<40); gray track when there are no tasks.

export type ScorePeriod = 'Today' | 'Last 7 days' | 'All time'

function ringColor(score: number, hasTasks: boolean): string {
  if (!hasTasks) return 'var(--bg-quaternary)'
  if (score >= 80) return '#34C759'
  if (score >= 60) return '#CCCC00'
  if (score >= 40) return '#FF9500'
  return '#FF3B30'
}

function arcPath(cx: number, cy: number, r: number, startDeg: number, endDeg: number): string {
  const toXY = (deg: number) => {
    const rad = (deg * Math.PI) / 180
    return [cx + r * Math.cos(rad), cy - r * Math.sin(rad)]
  }
  const [x1, y1] = toXY(startDeg)
  const [x2, y2] = toXY(endDeg)
  const large = Math.abs(endDeg - startDeg) > 180 ? 1 : 0
  const sweep = endDeg < startDeg ? 1 : 0
  return `M ${x1} ${y1} A ${r} ${r} 0 ${large} ${sweep} ${x2} ${y2}`
}

function emptyCopy(period?: ScorePeriod): string {
  if (period === 'Last 7 days') return 'No tasks this week'
  if (period === 'All time') return 'No tasks yet'
  return 'No tasks due today'
}

export function ScoreGauge({
  data,
  size = 180,
  period
}: {
  data?: ScoreData
  size?: number
  period?: ScorePeriod
}) {
  const score = Math.max(0, Math.min(100, data?.score ?? 0))
  const completed = data?.completedTasks ?? 0
  const total = data?.totalTasks ?? 0
  const hasTasks = total > 0
  const displayScore = hasTasks ? score : 0
  const stroke = Math.max(size * 0.085, 9)
  const r = (size - stroke) / 2
  const cx = size / 2
  const cy = size / 2
  const color = ringColor(displayScore, hasTasks)

  // Render one full semicircle and reveal it by animating strokeDashoffset
  // (the Swift app animates .trim with easeInOut 0.3s). Animating the offset
  //, rather than recomputing the arc endpoint, keeps the sweep smooth.
  const arcLength = Math.PI * r
  const fraction = displayScore / 100
  const offset = arcLength * (1 - fraction)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
      <div style={{ position: 'relative', width: size, height: size / 2 + 6 }}>
        <svg width={size} height={size / 2 + 6} style={{ overflow: 'visible' }}>
          <path d={arcPath(cx, cy, r, 180, 0)} fill="none" stroke="var(--bg-quaternary)" strokeWidth={stroke} strokeLinecap="round" />
          {hasTasks && (
            <path
              d={arcPath(cx, cy, r, 180, 0)}
              fill="none"
              stroke={color}
              strokeWidth={stroke}
              strokeLinecap="round"
              strokeDasharray={arcLength}
              strokeDashoffset={offset}
              style={{ transition: 'stroke-dashoffset 0.3s ease, stroke 0.3s ease' }}
            />
          )}
        </svg>
        <div
          className="tnum"
          style={{
            position: 'absolute',
            top: '52%',
            left: 0,
            right: 0,
            textAlign: 'center',
            fontSize: size * 0.2,
            fontWeight: 700
          }}
        >
          {Math.round(displayScore)}%
        </div>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4, marginTop: 4 }}>
        <div className="tnum" style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 12, color: 'var(--text-tertiary)' }}>
          {hasTasks ? (
            <>
              <svg width={13} height={13} viewBox="0 0 24 24" fill="none" style={{ flexShrink: 0 }} aria-hidden>
                <circle cx={12} cy={12} r={10} fill={color} />
                <path d="M7.5 12.2l3 3 6-6.4" stroke="#fff" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              {completed} of {total} tasks completed
            </>
          ) : (
            emptyCopy(period)
          )}
        </div>
        {period && <div style={{ fontSize: 10, color: 'var(--text-quaternary)' }}>{period}</div>}
      </div>
    </div>
  )
}
