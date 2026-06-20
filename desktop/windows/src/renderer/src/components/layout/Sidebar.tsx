import { useEffect, useRef, useState } from 'react'
import { audioAnalyser } from '../../lib/audioAnalyser'
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
  MicOff,
  PanelLeftClose,
  PanelLeftOpen,
  Settings,
  MessageCircle,
  ShieldAlert,
  Bluetooth,
  HelpCircle,
  User as UserIcon,
  Loader2,
  ChevronRight,
  X,
  Download,
  Gift,
  MoreHorizontal,
  Lock,
} from 'lucide-react'
import { auth, onAuthStateChanged } from '../../lib/firebase'
import { getPreferences, onPreferencesChange, setPreferences } from '../../lib/preferences'
import { cn } from '../../lib/utils'
import { RecordingStatusBar } from '../recording/RecordingStatusBar'
import { liveConversation, type LiveStatus } from '../../lib/liveConversation'
import type { User } from 'firebase/auth'
import type { RewindSettings } from '../../../../shared/types'
import { loadObservations, type FocusStatus } from '../../lib/focusEngine'

const navItems = [
  { label: 'Dashboard', to: '/home', Icon: House, tier: 5 },
  { label: 'Conversations', to: '/conversations', Icon: GanttChartSquare, tier: 1 },
  { label: 'Chat', to: '/chat', Icon: MessageCircle, tier: 4 },
  { label: 'Memories', to: '/memories', Icon: Brain, tier: 2 },
  { label: 'Tasks', to: '/tasks', Icon: ListChecks, tier: 3 },
  { label: 'Focus', to: '/focus', Icon: Target, tier: 0 },
  { label: 'Rewind', to: '/rewind', Icon: History, tier: 1 },
  { label: 'Insights', to: '/insights', Icon: Lightbulb, tier: 0 },
  { label: 'Apps', to: '/apps', Icon: LayoutGrid, tier: 6 },
]

const TIER_KEY = 'omi.tier.level'

const COLLAPSE_KEY = 'omi.sidebar.collapsed'
const LAST_DEVICE_KEY = 'omi.ble.lastDevice.v1'
const GET_OMI_DISMISSED_KEY = 'omi.sidebar.getOmiDismissed'

const HOVER = 'hover:bg-[var(--nav-sel)]'

const FOCUS_DOT: Record<FocusStatus, string> = {
  focused: 'bg-green-500',
  distracted: 'bg-orange-500',
  neutral: 'bg-white/25',
}

const BAR_MIN = 0.15
const BAR_GAIN = 3.5
const BAR_SMOOTH = 0.35
const FLOOR_DECAY = 0.002
const FLOOR_MARGIN = 0.04

/** 4 bars driven by real mic AnalyserNode amplitude — mirrors macOS AudioLevelNavItem. */
function AudioBars(): React.JSX.Element {
  const barsRef = useRef<Array<HTMLSpanElement | null>>([null, null, null, null])
  const scalesRef = useRef<number[]>([BAR_MIN, BAR_MIN, BAR_MIN, BAR_MIN])
  const floorRef = useRef(0)
  const dataRef = useRef<Uint8Array>(new Uint8Array(16))

  useEffect(() => {
    let raf = 0
    const tick = (): void => {
      const analyserNode = audioAnalyser.get()
      const bars = barsRef.current
      if (analyserNode) {
        if (dataRef.current.length !== analyserNode.frequencyBinCount) {
          dataRef.current = new Uint8Array(analyserNode.frequencyBinCount)
        }
        analyserNode.getByteFrequencyData(dataRef.current as Uint8Array<ArrayBuffer>)
        const d = dataRef.current
        const avg = d.reduce((s, v) => s + v / 255, 0) / d.length
        floorRef.current =
          avg > floorRef.current ? avg : Math.max(0, floorRef.current - FLOOR_DECAY)
        const floor = Math.max(0, floorRef.current - FLOOR_MARGIN)
        const bucketSize = Math.max(1, Math.floor(d.length / 4))
        for (let i = 0; i < 4; i++) {
          const s = i * bucketSize
          const e = Math.min(s + bucketSize, d.length)
          let sum = 0
          for (let j = s; j < e; j++) sum += d[j] / 255
          const raw = sum / (e - s)
          const v = Math.min(1, Math.max(0, (raw - floor) * BAR_GAIN))
          const target = BAR_MIN + v * (1 - BAR_MIN)
          const next = (scalesRef.current[i] ?? BAR_MIN) + (target - (scalesRef.current[i] ?? BAR_MIN)) * BAR_SMOOTH
          scalesRef.current[i] = next
          if (bars[i]) bars[i]!.style.transform = `scaleY(${next})`
        }
      } else {
        for (let i = 0; i < 4; i++) {
          const next = (scalesRef.current[i] ?? BAR_MIN) + (BAR_MIN - (scalesRef.current[i] ?? BAR_MIN)) * 0.1
          scalesRef.current[i] = next
          if (bars[i]) bars[i]!.style.transform = `scaleY(${next})`
        }
      }
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [])

  return (
    <div className="flex h-4 shrink-0 items-end gap-[2px]">
      {([0, 1, 2, 3] as const).map((i) => (
        <span
          key={i}
          ref={(el) => { barsRef.current[i] = el }}
          className="w-[2px] origin-bottom rounded-sm bg-[color:var(--accent)]"
          style={{ height: '100%', transform: `scaleY(${BAR_MIN})` }}
        />
      ))}
    </div>
  )
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
  const [liveStatus, setLiveStatus] = useState<LiveStatus>(() => liveConversation.getStatus())
  const [micPermission, setMicPermission] = useState<PermissionState | null>(null)
  const [loadingNav, setLoadingNav] = useState<string | null>(null)
  const [pairedDevice, setPairedDevice] = useState<{
    name: string
    id: string
    seenAt: number
  } | null>(null)
  const [showGetOmi, setShowGetOmi] = useState(
    () => localStorage.getItem(GET_OMI_DISMISSED_KEY) !== '1'
  )
  const [updateVersion, setUpdateVersion] = useState<string | null>(null)
  const [profileMenuOpen, setProfileMenuOpen] = useState(false)
  const [tierLevel, setTierLevel] = useState<number>(() => {
    const v = parseInt(localStorage.getItem(TIER_KEY) ?? '', 10)
    return isNaN(v) ? 99 : v
  })
  const profileMenuRef = useRef<HTMLDivElement>(null)
  const loadingNavTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const { pathname } = useLocation()
  const navigate = useNavigate()

  useEffect(() => onAuthStateChanged(auth, (u) => setUser(u)), [])
  useEffect(() => onPreferencesChange((p) => setPrefName(p.displayName)), [])

  // Load latest focus observation from local storage for sidebar dot
  useEffect(() => {
    const obs = loadObservations()
    if (obs.length > 0) setFocusStatus(obs[0].status)
  }, [pathname]) // refresh when navigating

  // Live conversation status — drives AudioBars on Conversations nav item
  useEffect(() => liveConversation.subscribe(() => setLiveStatus(liveConversation.getStatus())), [])

  // Mic permission — shown in permission status section
  useEffect(() => {
    if (!navigator.permissions) return
    navigator.permissions
      .query({ name: 'microphone' as PermissionName })
      .then((status) => {
        setMicPermission(status.state)
        status.addEventListener('change', () => setMicPermission(status.state))
      })
      .catch(() => {})
  }, [])

  // Load last-paired BLE device from localStorage (saved by DevicesTab on each connect)
  useEffect(() => {
    const raw = localStorage.getItem(LAST_DEVICE_KEY)
    if (raw) {
      try {
        setPairedDevice(JSON.parse(raw) as { name: string; id: string; seenAt: number })
      } catch {}
    }
    // Re-check when the user returns to the app (e.g. after pairing in DevicesTab)
    const onStorage = (e: StorageEvent): void => {
      if (e.key !== LAST_DEVICE_KEY) return
      const val = e.newValue
      if (!val) { setPairedDevice(null); return }
      try { setPairedDevice(JSON.parse(val)) } catch {}
    }
    window.addEventListener('storage', onStorage)
    return () => window.removeEventListener('storage', onStorage)
  }, [])

  // Sync tier level from localStorage — set by the onboarding flow
  useEffect(() => {
    const onStorage = (e: StorageEvent): void => {
      if (e.key !== TIER_KEY) return
      const v = parseInt(e.newValue ?? '', 10)
      setTierLevel(isNaN(v) ? 99 : v)
    }
    window.addEventListener('storage', onStorage)
    return () => window.removeEventListener('storage', onStorage)
  }, [])

  // Check for updates via GitHub releases API — mirrors macOS Sparkle check.
  // Compares current app version (semver) to the latest windows-tagged release.
  useEffect(() => {
    void (async () => {
      const current = await window.omi.getAppVersion?.()
      if (!current) return
      try {
        const res = await fetch('https://api.github.com/repos/BasedHardware/omi/releases/latest')
        if (!res.ok) return
        const data = (await res.json()) as { tag_name?: string }
        const tag = data.tag_name ?? ''
        if (!tag.toLowerCase().includes('windows')) return
        const latest = tag.replace(/^v/i, '').replace(/-windows.*/i, '')
        if (latest && latest !== current && latest > current) setUpdateVersion(latest)
      } catch {}
    })()
  }, [])

  // Close profile menu when clicking outside it
  useEffect(() => {
    if (!profileMenuOpen) return
    const handler = (e: MouseEvent): void => {
      if (profileMenuRef.current && !profileMenuRef.current.contains(e.target as Node)) {
        setProfileMenuOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [profileMenuOpen])

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

  // Clear loadingNav when navigation completes
  useEffect(() => {
    if (loadingNav && pathname === loadingNav) {
      const t = setTimeout(() => setLoadingNav(null), 600)
      return () => clearTimeout(t)
    }
    return undefined
  }, [pathname, loadingNav])

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

  const handleNavClick = (to: string): void => {
    if (pathname !== to) {
      if (loadingNavTimerRef.current) clearTimeout(loadingNavTimerRef.current)
      setLoadingNav(to)
      loadingNavTimerRef.current = setTimeout(() => setLoadingNav(null), 3000)
    }
  }

  const dismissGetOmi = (e: React.MouseEvent): void => {
    e.stopPropagation()
    e.preventDefault()
    localStorage.setItem(GET_OMI_DISMISSED_KEY, '1')
    setShowGetOmi(false)
  }

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

  // Device connection freshness: if seenAt is within last 60 minutes, treat as "recently connected"
  const deviceIsRecent =
    pairedDevice != null && Date.now() - pairedDevice.seenAt < 60 * 60 * 1000

  // Mic permission: show row when denied (shows Grant button) or when 'prompt' (not yet granted)
  const showMicPermissionRow = micPermission === 'denied'

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
        {navItems.map(({ label: text, to, Icon, tier }) => {
          const isLive = to === '/conversations' && (liveStatus === 'live' || liveStatus === 'connecting')
          const isLocked = tier > 0 && tierLevel < tier
          return (
            <NavLink
              key={to}
              to={to}
              title={collapsed ? (isLocked ? `${text} (unlocks at Tier ${tier})` : text) : undefined}
              onClick={() => handleNavClick(to)}
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
                const isLoading = loadingNav === to
                return (
                  <>
                    {isLoading ? (
                      <Loader2
                        className="h-4 w-4 shrink-0 animate-spin text-[color:var(--accent)]"
                        strokeWidth={1.75}
                      />
                    ) : isLive ? (
                      <AudioBars />
                    ) : (
                      <Icon
                        className={cn(
                          'h-4 w-4 shrink-0 transition-colors duration-150',
                          active ? 'text-[color:var(--accent)]' : 'text-white/50'
                        )}
                        strokeWidth={1.75}
                      />
                    )}
                    {label(text)}
                    {/* Tier lock icon — shown during onboarding tier flow */}
                    {isLocked && !collapsed && (
                      <span title={`Unlocks at Tier ${tier}`}>
                        <Lock className="h-3 w-3 shrink-0 text-white/25" strokeWidth={2} />
                      </span>
                    )}
                    {/* Focus status dot */}
                    {!isLocked && to === '/focus' && focusStatus && !collapsed && (
                      <span className={cn('h-2 w-2 shrink-0 rounded-full', FOCUS_DOT[focusStatus])} />
                    )}
                    {/* Insight unread badge */}
                    {!isLocked && to === '/insights' && insightBadge > 0 && !collapsed && (
                      <span className="flex h-4 min-w-[1rem] items-center justify-center rounded-full bg-[color:var(--accent)] px-1 text-[10px] font-bold leading-none text-white">
                        {insightBadge > 99 ? '99+' : insightBadge}
                      </span>
                    )}
                    {/* Rewind pulse dot when screen or mic capture is active */}
                    {!isLocked && to === '/rewind' && (screenOn || micOn) && !collapsed && (
                      <span className="h-1.5 w-1.5 shrink-0 animate-pulse rounded-full bg-[color:var(--accent)]" />
                    )}
                  </>
                )
              }}
            </NavLink>
          )
        })}

        {/* Persona link */}
        <NavLink
          to="/persona"
          title={collapsed ? 'AI Persona' : undefined}
          onClick={() => handleNavClick('/persona')}
          className={({ isActive }) => linkClass(isActive)}
        >
          {({ isActive }) => (
            <>
              {loadingNav === '/persona' ? (
                <Loader2
                  className="h-4 w-4 shrink-0 animate-spin text-[color:var(--accent)]"
                  strokeWidth={1.75}
                />
              ) : (
                <UserIcon
                  className={cn(
                    'h-4 w-4 shrink-0 transition-colors duration-150',
                    isActive ? 'text-[color:var(--accent)]' : 'text-white/50'
                  )}
                  strokeWidth={1.75}
                />
              )}
              {label('Persona')}
            </>
          )}
        </NavLink>
      </div>

      {/* ── Widgets section (macOS parity) ──────────────────────────────── */}

      {/* Device status widget: shown when a BLE device has been paired */}
      {pairedDevice && (
        <button
          onClick={() => navigate('/settings?tab=devices')}
          title={collapsed ? pairedDevice.name : undefined}
          className={cn(
            'mt-2 flex w-full items-center rounded-xl border px-3 py-2.5 text-left transition-colors duration-150',
            !collapsed && 'gap-3',
            deviceIsRecent
              ? 'border-green-500/25 bg-white/[0.04] hover:bg-white/[0.07]'
              : 'border-white/10 bg-white/[0.03] hover:bg-white/[0.06]'
          )}
        >
          {/* Device icon with connection dot */}
          <div className="relative shrink-0">
            <Bluetooth
              className={cn(
                'h-4 w-4',
                deviceIsRecent ? 'text-[color:var(--accent)]' : 'text-white/40'
              )}
              strokeWidth={1.75}
            />
            <span
              className={cn(
                'absolute -bottom-0.5 -right-0.5 h-1.5 w-1.5 rounded-full ring-1 ring-[#0a0a0a]',
                deviceIsRecent ? 'bg-green-500' : 'bg-orange-400'
              )}
            />
          </div>
          {!collapsed && (
            <>
              <div className="min-w-0 flex-1">
                <p className="truncate text-xs font-semibold text-white/80">{pairedDevice.name}</p>
                <p className={cn('text-[10px]', deviceIsRecent ? 'text-green-500' : 'text-orange-400')}>
                  {deviceIsRecent ? 'Connected' : 'Last paired'}
                </p>
              </div>
              <ChevronRight className="h-3 w-3 shrink-0 text-white/25" strokeWidth={2} />
            </>
          )}
        </button>
      )}

      {/* Get Omi promo widget: shown when no device paired and not dismissed */}
      {!pairedDevice && showGetOmi && (
        <div
          className={cn(
            'mt-2 flex w-full items-center rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2.5',
            !collapsed && 'gap-3'
          )}
        >
          <Bluetooth
            className="h-4 w-4 shrink-0 text-[color:var(--accent)]"
            strokeWidth={1.75}
          />
          {!collapsed && (
            <>
              <button
                onClick={() => window.omi.openExternal?.('https://www.omi.me')}
                className="min-w-0 flex-1 text-left"
              >
                <p className="truncate text-xs font-semibold text-white/80">Get Omi Device</p>
                <p className="text-[10px] text-white/35">Your wearable AI companion</p>
              </button>
              <button
                onClick={dismissGetOmi}
                className="shrink-0 rounded-md p-1 text-white/30 transition-colors hover:bg-white/10 hover:text-white/60"
                title="Dismiss"
              >
                <X className="h-3 w-3" strokeWidth={2} />
              </button>
            </>
          )}
        </div>
      )}

      {/* Mic permission row: shown when mic is denied */}
      {showMicPermissionRow && (
        <div
          className={cn(
            'mt-2 flex w-full items-center rounded-xl border border-red-500/20 bg-red-500/[0.06] px-3 py-2',
            !collapsed && 'gap-3'
          )}
          title={collapsed ? 'Microphone permission denied' : undefined}
        >
          <MicOff className="h-4 w-4 shrink-0 text-red-400" strokeWidth={1.75} />
          {!collapsed && (
            <>
              <span className="min-w-0 flex-1 truncate text-xs text-white/60">Microphone</span>
              <button
                onClick={() => navigate('/permissions')}
                className="shrink-0 rounded-md bg-red-500/70 px-2 py-0.5 text-[11px] font-semibold text-white transition-colors hover:bg-red-500"
              >
                Grant
              </button>
            </>
          )}
        </div>
      )}

      {/* Update available widget — mirrors macOS pulsing purple card */}
      {updateVersion && (
        <button
          onClick={() => window.omi.checkForUpdates?.()}
          title={collapsed ? `Update available: v${updateVersion}` : undefined}
          className={cn(
            'mt-2 flex w-full items-center rounded-xl bg-[color:var(--accent)] px-3 py-2.5 transition-all duration-150 hover:brightness-110 active:scale-[0.98]',
            !collapsed && 'gap-3',
            'sidebar-update-glow'
          )}
        >
          <Download className="h-4 w-4 shrink-0 text-white" strokeWidth={1.75} />
          {!collapsed && (
            <div className="min-w-0 flex-1 text-left">
              <p className="truncate text-xs font-semibold text-white">Update Available</p>
              <p className="text-[10px] text-white/75">v{updateVersion}</p>
            </div>
          )}
          {!collapsed && <ChevronRight className="h-3 w-3 shrink-0 text-white/70" strokeWidth={2} />}
        </button>
      )}

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

      {/* Account row + profile menu popover — mirrors macOS profileMenuButton */}
      <div ref={profileMenuRef} className="relative">
        {/* Profile popover */}
        {profileMenuOpen && !collapsed && (
          <div className="absolute bottom-full left-0 right-0 mb-1 overflow-hidden rounded-xl border border-white/10 bg-[#0f0f0f] py-1 shadow-xl">
            <button
              onClick={() => { setProfileMenuOpen(false); window.omi.openExternal?.('https://affiliate.omi.me') }}
              className="flex w-full items-center gap-3 px-3 py-2 text-sm text-white/70 transition-colors hover:bg-white/8 hover:text-white/90"
            >
              <Gift className="h-4 w-4 shrink-0 text-[color:var(--accent)]" strokeWidth={1.75} />
              Refer a Friend
            </button>
            <button
              onClick={() => { setProfileMenuOpen(false); window.omi.openExternal?.('https://discord.com/invite/8MP3b9ymvx') }}
              className="flex w-full items-center gap-3 px-3 py-2 text-sm text-white/70 transition-colors hover:bg-white/8 hover:text-white/90"
            >
              <MessageCircle className="h-4 w-4 shrink-0 text-[#5865F2]" strokeWidth={1.75} />
              Discord
            </button>
            <div className="mx-3 my-1 h-px bg-white/8" />
            <Link
              to="/settings"
              onClick={() => setProfileMenuOpen(false)}
              className="flex w-full items-center gap-3 px-3 py-2 text-sm text-white/70 transition-colors hover:bg-white/8 hover:text-white/90"
            >
              <Settings className="h-4 w-4 shrink-0 text-white/40" strokeWidth={1.75} />
              Settings
            </Link>
          </div>
        )}

        <button
          onClick={() => (collapsed ? navigate('/settings') : setProfileMenuOpen((o) => !o))}
          title={collapsed ? displayName : undefined}
          className={cn(
            'flex w-full items-center rounded-xl px-2.5 py-2 text-sm transition-colors duration-150 text-white/60 hover:text-white/90',
            !collapsed && 'gap-3',
            profileMenuOpen ? 'bg-[var(--nav-sel)] text-white/90' : HOVER
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
          {!collapsed && (
            <>
              {label(displayName)}
              <MoreHorizontal className="h-4 w-4 shrink-0 text-white/30" strokeWidth={1.75} />
            </>
          )}
        </button>
      </div>
    </nav>
  )
}
