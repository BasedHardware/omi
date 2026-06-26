import React from 'react'
import ReactMarkdown from 'react-markdown'

export function Toggle({ on, onChange }: { on: boolean; onChange: (next: boolean) => void }) {
  return (
    <button
      className={`toggle ${on ? 'on' : ''}`}
      onClick={() => onChange(!on)}
      role="switch"
      aria-checked={on}
      style={{ WebkitAppRegion: 'no-drag' } as React.CSSProperties}
    />
  )
}

export function Markdown({ children }: { children: string }) {
  return (
    <div className="markdown text-selectable">
      <ReactMarkdown>{children}</ReactMarkdown>
    </div>
  )
}

export function Spinner({ size = 16 }: { size?: number }) {
  return <div className="spinner" style={{ width: size, height: size }} />
}

export function EmptyState({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="empty-state">
      <div style={{ fontSize: 15, color: 'var(--text-tertiary)', fontWeight: 500 }}>{title}</div>
      {subtitle && <div style={{ maxWidth: 360 }}>{subtitle}</div>}
    </div>
  )
}

export function SettingRow({
  label,
  description,
  children
}: {
  label: string
  description?: string
  children: React.ReactNode
}) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 18,
        padding: '13px 16px',
        borderBottom: '1px solid var(--border)'
      }}
    >
      <div style={{ minWidth: 0 }}>
        <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-secondary)' }}>{label}</div>
        {description && (
          <div style={{ fontSize: 12, color: 'var(--text-quaternary)', marginTop: 3, lineHeight: 1.4 }}>
            {description}
          </div>
        )}
      </div>
      <div style={{ flexShrink: 0, display: 'flex', alignItems: 'center', gap: 8 }}>{children}</div>
    </div>
  )
}

export function SectionCard({ title, children }: { title?: string; children: React.ReactNode }) {
  return (
    <div className="section" style={{ overflow: 'hidden', marginBottom: 18 }}>
      {title && (
        <div
          style={{
            padding: '12px 16px 10px',
            fontSize: 12,
            fontWeight: 600,
            textTransform: 'uppercase',
            letterSpacing: 0.6,
            color: 'var(--text-quaternary)',
            borderBottom: '1px solid var(--border)'
          }}
        >
          {title}
        </div>
      )}
      {children}
    </div>
  )
}

export function CategoryChip({ label }: { label: string }) {
  return (
    <span
      style={{
        display: 'inline-block',
        padding: '2px 9px',
        borderRadius: 9,
        background: 'rgba(139, 92, 246, 0.16)',
        border: '1px solid rgba(139, 92, 246, 0.35)',
        color: '#c4b5fd',
        fontSize: 11,
        fontWeight: 500,
        whiteSpace: 'nowrap'
      }}
    >
      {label}
    </span>
  )
}
