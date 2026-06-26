import React, { useEffect, useRef, useState } from 'react'
import herologo from '../assets/herologo.png'
import deviceImg from '../assets/omi-with-rope-no-padding.webp'
import {
  IconApps,
  IconConversations,
  IconDashboard,
  IconFocus,
  IconGoals,
  IconGraph,
  IconHelp,
  IconInsights,
  IconMemories,
  IconRewind,
  IconSettings,
  IconSidebar,
  IconTasks
} from '../components/Icons'
import { useAuth } from '../stores/auth'
import { useLive } from '../stores/conversations'
import { useProactive } from '../stores/proactive'
import { useSettings } from '../stores/settings'
import type { Page } from './App'

// Sidebar mirrors SidebarView.swift: 260px expanded / 64px collapsed, same item
// order (Dashboard, Conversations, Memories, Tasks, Rewind, Apps), audio-level
// bars on Conversations while recording, pulsing dot on Rewind while capturing.

type NavItem = { page: Page; label: string; icon: React.FC<{ size?: number }> }

// Local persona icon (Icons.tsx is off-limits here); same stroke style as the shared set.
const IconPersona: React.FC<{ size?: number }> = ({ size = 17 }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={2}
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <circle cx="12" cy="8" r="4" />
    <path d="M4 21a8 8 0 0 1 16 0" />
  </svg>
)

// Primary nav matches SidebarView.swift mainItems exactly (order + set).
const PRIMARY_NAV: NavItem[] = [
  { page: 'dashboard', label: 'Dashboard', icon: IconDashboard },
  { page: 'conversations', label: 'Conversations', icon: IconConversations },
  { page: 'chat', label: 'Chat', icon: IconConversations },
  { page: 'memories', label: 'Memories', icon: IconMemories },
  { page: 'tasks', label: 'Tasks', icon: IconTasks },
  { page: 'rewind', label: 'Rewind', icon: IconRewind },
  { page: 'apps', label: 'Apps', icon: IconApps }
]

// Secondary pages that exist on Mac but aren't in its primary sidebar list.
const SECONDARY_NAV: NavItem[] = [
  { page: 'goals', label: 'Goals', icon: IconGoals },
  { page: 'focus', label: 'Focus', icon: IconFocus },
  { page: 'insights', label: 'Insights', icon: IconInsights },
  { page: 'graph', label: 'Graph', icon: IconGraph },
  { page: 'persona', label: 'AI Persona', icon: IconPersona }
]

const NAV: NavItem[] = [...PRIMARY_NAV, ...SECONDARY_NAV]

function AudioBars({ level }: { level: number }) {
  // sqrt boost so quiet speech still moves the bars (matches SidebarAudioBar.swift)
  const boosted = Math.sqrt(Math.max(0, level))
  const heights = [0.5, 1, 0.7, 0.9].map((f) => Math.max(4, Math.min(14, 4 + boosted * 40 * f)))
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 2, height: 14 }}>
      {heights.map((h, i) => (
        <div
          key={i}
          style={{
            width: 3,
            height: h,
            borderRadius: 2,
            background: 'var(--success)',
            transition: 'height 0.1s ease'
          }}
        />
      ))}
    </div>
  )
}

export function Sidebar({ page, onNavigate }: { page: Page; onNavigate: (p: Page) => void }) {
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem('sidebarCollapsed') === '1')
  const [promoDismissed, setPromoDismissed] = useState(() => localStorage.getItem('promoDismissed') === '1')
  const [menuOpen, setMenuOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement | null>(null)
  const auth = useAuth((s) => s.state)
  const signOut = useAuth((s) => s.signOut)
  const live = useLive()
  const unreadInsights = useProactive((s) => s.status?.unread ?? 0)
  const { settings, update } = useSettings()

  useEffect(() => {
    localStorage.setItem('sidebarCollapsed', collapsed ? '1' : '0')
  }, [collapsed])

  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false)
    }
    window.addEventListener('mousedown', close)
    return () => window.removeEventListener('mousedown', close)
  }, [])

  const initials = (auth?.name || auth?.email || 'U')
    .split(' ')
    .map((p) => p[0])
    .slice(0, 2)
    .join('')
    .toUpperCase()

  return (
    <div
      style={{
        width: collapsed ? 64 : 260,
        transition: 'width 0.32s cubic-bezier(0.2, 0.8, 0.2, 1)',
        display: 'flex',
        flexDirection: 'column',
        padding: '12px 10px 12px',
        flexShrink: 0,
        height: '100%'
      }}
    >
      {/* Header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          padding: '4px 6px 14px',
          justifyContent: collapsed ? 'center' : 'flex-start'
        }}
      >
        <img src={herologo} width={20} height={20} style={{ borderRadius: 5 }} alt="omi" />
        {!collapsed && (
          <span style={{ fontSize: 22, fontWeight: 700, letterSpacing: -0.5, flex: 1 }}>omi</span>
        )}
        {!collapsed && (
          <button
            onClick={() => setCollapsed(true)}
            style={{ color: 'var(--text-quaternary)', padding: 4, WebkitAppRegion: 'no-drag' } as React.CSSProperties}
            title="Collapse sidebar"
          >
            <IconSidebar />
          </button>
        )}
      </div>
      {collapsed && (
        <button
          onClick={() => setCollapsed(false)}
          style={{ color: 'var(--text-quaternary)', padding: '0 0 10px', WebkitAppRegion: 'no-drag' } as React.CSSProperties}
          title="Expand sidebar"
        >
          <IconSidebar />
        </button>
      )}

      {/* Nav */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        {NAV.map(({ page: p, label, icon: Icon }) => {
          const selected = page === p
          const firstSecondary = !collapsed && p === SECONDARY_NAV[0].page
          return (
            <React.Fragment key={p}>
            {firstSecondary && <div style={{ height: 1, background: 'rgba(37,37,37,0.6)', margin: '8px 8px' }} />}
            <button
              key={p}
              onClick={() => onNavigate(p)}
              title={label}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                padding: collapsed ? '11px 0' : '11px 12px',
                justifyContent: collapsed ? 'center' : 'flex-start',
                borderRadius: 14,
                background: selected ? 'var(--bg-secondary)' : 'transparent',
                color: selected ? 'var(--text-primary)' : 'var(--text-tertiary)',
                fontSize: 14,
                fontWeight: selected ? 500 : 400,
                transition: 'background 0.12s ease'
              }}
              onMouseEnter={(e) => {
                if (!selected) e.currentTarget.style.background = 'rgba(37, 37, 37, 0.75)'
              }}
              onMouseLeave={(e) => {
                if (!selected) e.currentTarget.style.background = 'transparent'
              }}
            >
              <span style={{ width: 20, display: 'inline-flex', justifyContent: 'center', flexShrink: 0 }}>
                <Icon size={17} />
              </span>
              {!collapsed && <span style={{ flex: 1, textAlign: 'left' }}>{label}</span>}
              {!collapsed && p === 'conversations' && live.status === 'recording' && <AudioBars level={live.level} />}
              {!collapsed && p === 'rewind' && settings?.rewindEnabled && (
                <span
                  style={{
                    width: 8,
                    height: 8,
                    borderRadius: 4,
                    background: 'var(--purple-primary)',
                    animation: 'pulse 1.6s ease-in-out infinite'
                  }}
                />
              )}
              {!collapsed && p === 'insights' && unreadInsights > 0 && (
                <span
                  style={{
                    minWidth: 18,
                    height: 18,
                    padding: '0 5px',
                    borderRadius: 9,
                    background: 'var(--purple-primary)',
                    color: '#fff',
                    fontSize: 11,
                    fontWeight: 600,
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center'
                  }}
                >
                  {unreadInsights}
                </span>
              )}
            </button>
            </React.Fragment>
          )
        })}
      </div>

      <div style={{ flex: 1 }} />

      {/* Status rows */}
      {!collapsed && settings && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 2, padding: '0 6px 10px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 6px' }}>
            <span
              style={{
                width: 7,
                height: 7,
                borderRadius: 4,
                background: settings.rewindEnabled ? 'var(--success)' : 'var(--text-quaternary)'
              }}
            />
            <span style={{ fontSize: 12, color: 'var(--text-tertiary)', flex: 1 }}>Screen Capture</span>
            <span
              className={`toggle ${settings.rewindEnabled ? 'on' : ''}`}
              onClick={() => update({ rewindEnabled: !settings.rewindEnabled })}
              style={{ cursor: 'pointer' }}
            />
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 6px' }}>
            <span
              style={{
                width: 7,
                height: 7,
                borderRadius: 4,
                background: live.status === 'recording' ? 'var(--success)' : 'var(--text-quaternary)'
              }}
            />
            <span style={{ fontSize: 12, color: 'var(--text-tertiary)', flex: 1 }}>Microphone</span>
            <span style={{ fontSize: 11, color: 'var(--text-quaternary)' }}>
              {live.status === 'recording' ? 'live' : 'idle'}
            </span>
          </div>
        </div>
      )}

      {/* Get omi promo */}
      {!collapsed && !promoDismissed && (
        <div
          className="section"
          style={{ display: 'flex', alignItems: 'center', gap: 10, padding: 10, marginBottom: 12, position: 'relative' }}
        >
          <img src={deviceImg} width={24} height={24} style={{ objectFit: 'contain' }} alt="omi device" />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 13, fontWeight: 600 }}>Get omi Device</div>
            <div style={{ fontSize: 11, color: 'var(--text-quaternary)' }}>Your wearable AI companion</div>
          </div>
          <button
            onClick={() => {
              setPromoDismissed(true)
              localStorage.setItem('promoDismissed', '1')
            }}
            style={{ color: 'var(--text-quaternary)', fontSize: 11, padding: 2 }}
            title="Dismiss"
          >
            ✕
          </button>
        </div>
      )}

      {!collapsed && <div style={{ height: 1, background: 'rgba(37, 37, 37, 0.5)', margin: '0 6px 10px' }} />}

      {/* Profile */}
      <div ref={menuRef} style={{ position: 'relative' }}>
        <button
          onClick={() => setMenuOpen((v) => !v)}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 9,
            width: '100%',
            padding: collapsed ? '6px 0' : '6px 6px',
            justifyContent: collapsed ? 'center' : 'flex-start',
            borderRadius: 12
          }}
        >
          <span
            style={{
              width: 30,
              height: 30,
              borderRadius: 15,
              background: 'var(--purple-primary)',
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: 11,
              fontWeight: 600,
              flexShrink: 0
            }}
          >
            {initials}
          </span>
          {!collapsed && (
            <span
              style={{
                fontSize: 13,
                fontWeight: 500,
                color: 'var(--text-secondary)',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap'
              }}
            >
              {auth?.name || auth?.email || 'Account'}
            </span>
          )}
        </button>
        {menuOpen && (
          <div
            className="card"
            style={{
              position: 'absolute',
              bottom: 44,
              left: 0,
              width: 220,
              padding: 6,
              zIndex: 60,
              background: 'var(--bg-primary)'
            }}
          >
            {[
              { label: 'Refer a Friend', action: () => window.omi.system.openExternal('https://www.omi.me') },
              { label: 'Join Discord', action: () => window.omi.system.openExternal('https://discord.gg/omi') },
              { label: 'Settings', action: () => onNavigate('settings') },
              { label: 'Help', action: () => onNavigate('help') },
              { label: 'Sign Out', action: () => signOut() }
            ].map((item) => (
              <button
                key={item.label}
                onClick={() => {
                  setMenuOpen(false)
                  item.action()
                }}
                style={{
                  display: 'block',
                  width: '100%',
                  textAlign: 'left',
                  padding: '8px 10px',
                  borderRadius: 8,
                  fontSize: 13,
                  color: item.label === 'Sign Out' ? 'var(--error)' : 'var(--text-secondary)'
                }}
                onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--bg-tertiary)')}
                onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
              >
                {item.label}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Settings + Help shortcuts */}
      {!collapsed && (
        <div style={{ display: 'flex', gap: 2, marginTop: 8 }}>
          <button
            onClick={() => onNavigate('settings')}
            title="Settings"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              padding: '8px 12px',
              borderRadius: 12,
              color: page === 'settings' ? 'var(--text-primary)' : 'var(--text-quaternary)',
              fontSize: 13,
              flex: 1
            }}
          >
            <IconSettings size={15} /> Settings
          </button>
          <button
            onClick={() => onNavigate('help')}
            title="Help"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              padding: '8px 12px',
              borderRadius: 12,
              color: page === 'help' ? 'var(--text-primary)' : 'var(--text-quaternary)',
              fontSize: 13
            }}
          >
            <IconHelp size={15} />
          </button>
        </div>
      )}
    </div>
  )
}
