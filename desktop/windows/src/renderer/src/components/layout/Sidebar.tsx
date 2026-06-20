import { useEffect, useState } from 'react'
import { NavLink, Link, useLocation, useNavigate } from 'react-router-dom'
import {
  House,
  GanttChartSquare,
  ListChecks,
  LayoutGrid,
  History,
  Brain,
  Lightbulb,
  Target,
  Monitor,
  Mic,
  PanelLeftClose,
  PanelLeftOpen,
  Settings,
  MessageCircle,
  ShieldAlert,
  Bluetooth,
  HelpCircle,
  User as UserIcon
} from 'lucide-react'
import { auth, onAuthStateChanged } from '../../lib/firebase'
import { getPreferences, onPreferencesChange, setPreferences } from '../../lib/preferences'
import { cn } from '../../lib/utils'
import { RecordingStatusBar } from '../recording/RecordingStatusBar'
import type { User } from 'firebase/auth'
import type { RewindSettings } from '../../../../shared/types'
import { loadObservations, type FocusStatus } from '../../lib/focusEngine'

const navItems = [
  { label: 'Dashboard', to: '/home', Icon: House },
  { label: 'Conversations', to: '/conversations', Icon: GanttChartSquare },
  { label: 'Chat', to: '/chat', Icon: MessageCircle },
  { label: 'Memories', to: '/memories', Icon: Brain },
  { label: 'Tasks', to: '/tasks', Icon: ListChecks },
  { label: 'Focus', to: '/focus', Icon: Target },
  { label: 'Rewind', to: '/rewind', Icon: History },
  { label: 'Insights', to: '/insights', Icon: Lightbulb },
  { label: 'Apps', to: '/apps', Icon: LayoutGrid },
]

const COLLAPSE_KEY = 'omi.sidebar.collapsed'

const HOVER = 'hover:bg-[var(--nav-sel)]'

const FOCUS_DOT: Record<FocusStatus, string> = {
  focused: 'bg-green-500',
  distracted: 'bg-orange-500',
  neutral: 'bg-white/25',
}

export function Sidebar(): React.JSX.Element {
  const [user, setUser] = useState<User | null>(null)
  const [prefName, setPrefName] = useState<string | undefined>(getPreferences().displayName)
  const [collapsed, setCollapsed] = useState<boolean>(
    () => localStorage.getItem(COLLAPSE_KEY) === '1'
  )
  const [rewind, setRewind] = useState<RewindSettings | null>(null)
  const [focusStatus, setFocusStatus] = useState<FocusStatus | null>(null)
  const [insightBadge, setInsightBadge] = useState(0)
  const { pathname } = useLocation()
  const navigate = useNavigate()

  useEffect(() => onAuthStateChanged(auth, (u) => setUser(u)), [])
  useEffect(() => onPreferencesChange((p) => setPrefName(p.displayName)), [])

  // Load latest focus observation from local storage for sidebar dot
  useEffect(() => {
    const obs = loadObservations()
    if (obs.length > 0) setFocusStatus(obs[0].status)
  }, [pathname]) // refresh when navigating

  // Insight unread badge: count insights newer than the last time the user
  // visited /insights. Cleared on entry to /insights.
  useEffect(() => {
    if (pathname === '/insights') {
      localStorage.setItem('omi.insights.lastVisited', String(Date.now()))
      setInsightBadge(0)
      return
    }
    const lastVisited = parseInt(localStorage.getItem('omi.insights.lastVisited') ?? '0', 10)
    void window.omi.insightRecent?.(50).then((list) => {
      if (!list) return
      const unread = (list as Array<{ ts: number }>).filter((ins) => ins.ts > lastVisited).length
      setInsightBadge(unread)
    })
  }, [pathname])

  // Ctrl+1–N: jump to the nth sidebar item
  useEffect(() => {
    const allItems = [...navItems, { to: '/settings', Icon: Settings, label: 'Settings' }]
    const handler = (e: KeyboardEvent): void => {
      if (!e.ctrlKey || e.altKey || e.metaKey || e.shiftKey) return
      const digit = parseInt(e.key, 10)
      if (isNaN(digit) || digit < 1) return
      const item = allItems[digit - 1]
      if (!item) return
      const tag = (document.activeElement as HTMLElement | null)?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return
      e.preventDefault()
      navigate(item.to)
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [navigate])

  useEffect(() => {
    localStorage.setItem(COLLAPSE_KEY, collapsed ? '1' : '0')
  }, [collapsed])

  useEffect(() => {
    void window.omi.rewindGetSettings().then(setRewind)
  }, [])

  const email = user?.email
  const displayName = user?.displayName?.trim() || prefName?.trim() || email || 'Account'
  const photoURL = user?.photoURL
  const initial =
    (user?.displayName?.trim() || prefName?.trim() || email)?.[0]?.toUpperCase() ?? '?'

  const screenOn = !!rewind?.captureEnabled
  const toggleScreen = (): void => {
    if (!rewind) return
    const next = { ...rewind, captureEnabled: !rewind.captureEnabled }
    setRewind(next)
    void window.omi.rewindSetSettings(next).then(setRewind)
  }

  const [micOn, setMicOn] = useState<boolean>(() => !!getPreferences().continuousRecording)
  useEffect(() => onPreferencesChange((p) => setMicOn(!!p.continuousRecording)), [])
  const toggleMic = (): void => {
    setPreferences({ continuousRecording: !getPreferences().continuousRecording })
  }

  const label = (text: string): React.JSX.Element => (
    <span
      className={cn(
        'min-w-0 flex-1 truncate whitespace-nowrap text-left transition-opacity duration-200',
        collapsed && 'pointer-events-none opacity-0'
      )}
    >
      {text}
    </span>
  )

  const linkClass = (active: boolean): string =>
    cn(
      'flex items-center gap-3 rounded-xl px-2.5 py-2 text-sm font-medium transition-[color] duration-150',
      active ? 'nav-active' : cn('text-white/50 hover:text-white/80', HOVER)
    )

  const toggleRow = (
    text: string,
    Icon: typeof Mic,
    on: boolean,
    onClick: () => void
  ): React.JSX.Element => (
    <button
      onClick={onClick}
      title={collapsed ? `${text}${on ? ' · on' : ''}` : undefined}
      aria-pressed={on}
      className={cn(
        'flex w-full items-center rounded-xl px-2.5 py-2 text-sm transition-colors duration-150',
        !collapsed && 'gap-3',
        on ? cn('text-white/90', HOVER) : cn('text-white/50 hover:text-white/80', HOVER)
      )}
    >
      <Icon
        className={cn('h-4 w-4 shrink-0', on && 'text-[color:var(--accent)]')}
        strokeWidth={1.75}
      />
      {label(text)}
      {!collapsed && (
        <span
          className={cn(
            'relative h-4 w-7 shrink-0 rounded-full transition-colors duration-200',
            on ? 'bg-[color:var(--accent)]' : 'bg-white/15'
          )}
        >
          <span
            className={cn(
              'absolute top-0.5 h-3 w-3 rounded-full bg-white transition-all duration-200',
              on ? 'left-3.5' : 'left-0.5'
            )}
          />
        </span>
      )}
    </button>
  )

  // Bottom utility links: Settings, Permissions, Device, Help
  const bottomLinks = [
    { label: 'Settings', to: '/settings', Icon: Settings },
    { label: 'Permissions', to: '/permissions', Icon: ShieldAlert },
    { label: 'Device', to: '/settings?tab=devices', Icon: Bluetooth },
    { label: 'Help from Founder', to: '/help', Icon: HelpCircle },
  ]

  return (
    <nav
      className={cn(
        'slide-in-left relative z-50 flex h-full shrink-0 flex-col border-r border-white/10 bg-[#0a0a0a] px-2 py-3',
        'transition-[width] duration-200 ease-out',
        collapsed ? 'w-16' : 'w-60'
      )}
    >
      {/* Top row: logo + collapse toggle */}
      <div className="flex items-center justify-between px-1.5 py-1">
        <img
          src="https://personas.omi.me/omilogo.png"
          alt="omi"
          className={cn(
            'h-4 shrink-0 overflow-hidden transition-opacity duration-200',
            collapsed ? 'pointer-events-none w-0 opacity-0' : 'w-auto opacity-100'
          )}
        />
        <button
          onClick={() => setCollapsed((c) => !c)}
          title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          className={cn(
            'shrink-0 rounded-lg p-1.5 text-white/40 transition-colors hover:text-white/80',
            HOVER
          )}
        >
          {collapsed ? (
            <PanelLeftOpen className="h-4 w-4" strokeWidth={1.75} />
          ) : (
            <PanelLeftClose className="h-4 w-4" strokeWidth={1.75} />
          )}
        </button>
      </div>

      <div className="my-2 h-px w-full bg-white/10" />

      {/* Main nav items */}
      <div className="flex flex-1 flex-col gap-1 overflow-y-auto overflow-x-hidden">
        {navItems.map(({ label: text, to, Icon }) => (
          <NavLink
            key={to}
            to={to}
            title={collapsed ? text : undefined}
            className={({ isActive }) =>
              linkClass(
                isActive ||
                (to === '/tasks' && pathname === '/goals') ||
                (to === '/home' && pathname === '/chat-legacy')
              )
            }
          >
            {({ isActive }) => {
              const active = isActive || (to === '/tasks' && pathname === '/goals')
              return (
                <>
                  <Icon
                    className={cn(
                      'h-4 w-4 shrink-0 transition-colors duration-150',
                      active ? 'text-[color:var(--accent)]' : 'text-white/50'
                    )}
                    strokeWidth={1.75}
                  />
                  {label(text)}
                  {/* Focus status dot */}
                  {to === '/focus' && focusStatus && !collapsed && (
                    <span className={cn('h-2 w-2 shrink-0 rounded-full', FOCUS_DOT[focusStatus])} />
                  )}
                  {/* Insight unread badge */}
                  {to === '/insights' && insightBadge > 0 && !collapsed && (
                    <span className="flex h-4 min-w-[1rem] items-center justify-center rounded-full bg-[color:var(--accent)] px-1 text-[10px] font-bold leading-none text-white">
                      {insightBadge > 99 ? '99+' : insightBadge}
                    </span>
                  )}
                  {/* Rewind pulse dot when screen or mic capture is active */}
                  {to === '/rewind' && (screenOn || micOn) && !collapsed && (
                    <span className="h-1.5 w-1.5 shrink-0 animate-pulse rounded-full bg-[color:var(--accent)]" />
                  )}
                </>
              )
            }}
          </NavLink>
        ))}

        {/* Persona link */}
        <NavLink
          to="/persona"
          title={collapsed ? 'AI Persona' : undefined}
          className={({ isActive }) => linkClass(isActive)}
        >
          {({ isActive }) => (
            <>
              <UserIcon
                className={cn(
                  'h-4 w-4 shrink-0 transition-colors duration-150',
                  isActive ? 'text-[color:var(--accent)]' : 'text-white/50'
                )}
                strokeWidth={1.75}
              />
              {label('Persona')}
            </>
          )}
        </NavLink>
      </div>

      <div className="my-2 h-px w-full bg-white/10" />

      {/* Recording status */}
      <RecordingStatusBar collapsed={collapsed} />

      {/* Quick capture toggles */}
      <div className="flex flex-col gap-1">
        {toggleRow('Screen recording', Monitor, screenOn, toggleScreen)}
        {toggleRow('Microphone', Mic, micOn, toggleMic)}
      </div>

      <div className="my-2 h-px w-full bg-white/10" />

      {/* Bottom utility links (Settings, Permissions, Device, Help) */}
      <div className="flex flex-col gap-0.5">
        {bottomLinks.map(({ label: text, to, Icon }) => {
          const isSettings = to === '/settings' && pathname === '/settings'
          const isPermissions = to === '/permissions' && pathname === '/permissions'
          const isHelp = to === '/help' && pathname === '/help'
          const active = isSettings || isPermissions || isHelp
          return (
            <Link
              key={to}
              to={to}
              title={collapsed ? text : undefined}
              className={cn(
                'flex items-center rounded-xl px-2.5 py-1.5 text-sm transition-colors duration-150',
                !collapsed && 'gap-3',
                active ? 'nav-active' : cn('text-white/40 hover:text-white/70', HOVER)
              )}
            >
              <Icon className="h-4 w-4 shrink-0" strokeWidth={1.75} />
              {label(text)}
            </Link>
          )
        })}
      </div>

      <div className="my-2 h-px w-full bg-white/10" />

      {/* Account row */}
      <Link
        to="/settings"
        title={collapsed ? displayName : undefined}
        className={cn(
          'flex w-full items-center rounded-xl px-2.5 py-2 text-sm transition-colors duration-150 text-white/60 hover:text-white/90',
          !collapsed && 'gap-3',
          HOVER
        )}
      >
        <div className="relative h-7 w-7 shrink-0 overflow-hidden rounded-lg border border-white/10">
          <img
            src={photoURL ?? ''}
            alt=""
            className={cn('h-full w-full object-cover', photoURL ? 'block' : 'hidden')}
            referrerPolicy="no-referrer"
            onError={(e) => {
              const el = e.currentTarget
              el.classList.add('hidden')
              el.nextElementSibling?.classList.remove('hidden')
            }}
          />
          <div
            className={cn(
              'flex h-full w-full items-center justify-center bg-white/10 text-[11px] font-semibold text-white',
              photoURL ? 'hidden' : ''
            )}
          >
            {initial}
          </div>
        </div>
        {label(displayName)}
      </Link>
    </nav>
  )
}
