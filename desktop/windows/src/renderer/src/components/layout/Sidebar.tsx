import { useEffect, useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import {
  House,
  GanttChartSquare,
  ListChecks,
  LayoutGrid,
  History,
  Monitor,
  Mic,
  PanelLeftClose,
  PanelLeftOpen
} from 'lucide-react'
import { auth, onAuthStateChanged } from '../../lib/firebase'
import { getPreferences, onPreferencesChange, setPreferences } from '../../lib/preferences'
import { cn } from '../../lib/utils'
import { Orb } from '../orb/Orb'
import type { User } from 'firebase/auth'
import type { RewindSettings } from '../../../../shared/types'

const navItems = [
  { label: 'Home', to: '/home', Icon: House },
  { label: 'Conversations', to: '/conversations', Icon: GanttChartSquare },
  { label: 'Tasks', to: '/tasks', Icon: ListChecks },
  { label: 'Rewind', to: '/rewind', Icon: History },
  { label: 'Apps', to: '/apps', Icon: LayoutGrid }
]

const COLLAPSE_KEY = 'omi.sidebar.collapsed'

// Shared hover/selection background — matches .nav-active so an active tab and a
// hovered tab read as the same neutral grey.
const HOVER = 'hover:bg-[var(--nav-sel)]'

export function Sidebar(): React.JSX.Element {
  const [user, setUser] = useState<User | null>(null)
  const [prefName, setPrefName] = useState<string | undefined>(getPreferences().displayName)
  const [collapsed, setCollapsed] = useState<boolean>(
    () => localStorage.getItem(COLLAPSE_KEY) === '1'
  )
  const [rewind, setRewind] = useState<RewindSettings | null>(null)
  const { pathname } = useLocation()

  useEffect(() => onAuthStateChanged(auth, (u) => setUser(u)), [])

  // Keep the displayed name in sync with the editable Settings/onboarding name.
  useEffect(() => onPreferencesChange((p) => setPrefName(p.displayName)), [])

  useEffect(() => {
    localStorage.setItem(COLLAPSE_KEY, collapsed ? '1' : '0')
  }, [collapsed])

  useEffect(() => {
    void window.omi.rewindGetSettings().then(setRewind)
  }, [])

  const email = user?.email
  // Prefer the Google account's full name (stable "First Last"), then the
  // onboarding-entered name, then the email.
  const displayName = user?.displayName?.trim() || prefName?.trim() || email || 'Account'
  const photoURL = user?.photoURL
  const initial =
    (user?.displayName?.trim() || prefName?.trim() || email)?.[0]?.toUpperCase() ?? '?'

  // Screen-recording = the persistent Rewind capture setting (the toggle that
  // used to be a checkbox in Settings). Optimistic flip, reconcile from main.
  const screenOn = !!rewind?.captureEnabled
  const toggleScreen = (): void => {
    if (!rewind) return
    const next = { ...rewind, captureEnabled: !rewind.captureEnabled }
    setRewind(next)
    void window.omi.rewindSetSettings(next).then(setRewind)
  }

  // Microphone = always-on listening. The toggle reflects the `continuousRecording`
  // preference; flipping it starts/stops the capture window's ContinuousSessionHost
  // (which streams the mic to /v4/listen). Viewing the live transcript is a SEPARATE
  // affordance (the "New" button in Conversations / opening a conversation row) —
  // this switch only turns listening on and off.
  const [micOn, setMicOn] = useState<boolean>(() => !!getPreferences().continuousRecording)
  useEffect(() => onPreferencesChange((p) => setMicOn(!!p.continuousRecording)), [])
  const toggleMic = (): void => {
    setPreferences({ continuousRecording: !getPreferences().continuousRecording })
  }

  // The label/name text fades with opacity (and is width-clipped by flexbox) so
  // collapsing animates smoothly instead of popping. Row padding/alignment stay
  // constant in both states — only nav width and text opacity animate.
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
            'relative ml-auto h-4 w-7 shrink-0 rounded-full transition-colors duration-200',
            on ? 'bg-[color:var(--accent)]' : 'bg-white/15'
          )}
        >
          <span
            className={cn(
              'absolute top-0.5 h-3 w-3 rounded-full transition-all duration-200',
              on ? 'left-3.5 bg-[color:var(--accent-contrast)]' : 'left-0.5 bg-white'
            )}
          />
        </span>
      )}
    </button>
  )

  return (
    <nav
      className={cn(
        'slide-in-left relative z-50 flex h-full shrink-0 flex-col border-r border-line px-2 py-3',
        'transition-[width] duration-200 ease-out',
        collapsed ? 'w-16' : 'w-60'
      )}
    >
      {/* Top row: orb + logo (left, logo fades out when collapsed) + collapse
          toggle pinned right. The orb is the same component the bar mounts, but
          here it's the resting brand logo ONLY — pinned to the calm idle pose
          with its slow step-rest spin (user, 2026-07-12: the in-app logo should
          NOT mirror the bar's activity, just the regular slow-spin logo).

          Collapsed rail (w-16): the 22px orb and the ~28px collapse button can't
          sit side-by-side in the ~36px of header content width — the fixed-width
          orb canvas would overflow under the button. So when collapsed we stack
          them vertically (flex-col) with each on its own row, both centered by the
          base `items-center` (cross-axis in a column). Expanded stays a justified
          row, pixel-identical to before. */}
      <div
        className={cn(
          // Tuck the brand toward the true top-left. `-mt-1` lifts the header
          // ~4px closer under the drag strip; when expanded, `-ml-1.5` pulls the
          // row ~6px left into the nav's px-2 so the orb sits ~8px from the edge
          // (was ~14/16px). Only the left group moves — the collapse button
          // keeps its right inset, and the nav items below keep their left
          // rhythm (nav wrapper padding is untouched). Collapsed rail stays
          // center-aligned (no `-ml` there).
          'flex items-center px-1.5 py-1 -mt-1',
          collapsed ? 'flex-col gap-2' : 'justify-between -ml-1.5'
        )}
      >
        <div className="flex min-w-0 items-center gap-2.5">
          <Orb size={22} preset="compact" state="idle" />
          {/* Wordmark as text (crisp at every DPI, no network fetch). */}
          <span
            className={cn(
              'shrink-0 select-none overflow-hidden text-[15px] font-semibold lowercase tracking-tight text-white transition-opacity duration-200',
              collapsed ? 'pointer-events-none w-0 opacity-0' : 'w-auto opacity-100'
            )}
          >
            omi
          </span>
        </div>
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

      <div className="my-2 h-px w-full bg-white/[0.07]" />

      <div className="flex flex-1 flex-col gap-1 overflow-y-auto overflow-x-hidden">
        {navItems.map(({ label: text, to, Icon }) => (
          <NavLink
            key={to}
            to={to}
            title={collapsed ? text : undefined}
            className={({ isActive }) =>
              linkClass(isActive || (to === '/tasks' && pathname === '/goals'))
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
                </>
              )
            }}
          </NavLink>
        ))}
      </div>

      <div className="my-2 h-px w-full bg-white/[0.07]" />

      {/* Quick capture toggles, sitting just above the account row. */}
      <div className="flex flex-col gap-1">
        {toggleRow('Screen recording', Monitor, screenOn, toggleScreen)}
        {toggleRow('Microphone', Mic, micOn, toggleMic)}
      </div>

      <div className="my-2 h-px w-full bg-white/[0.07]" />

      {/* Account row → opens Settings (Sign out now lives in Settings). */}
      <NavLink
        to="/settings"
        title={collapsed ? displayName : undefined}
        className={({ isActive }) =>
          cn(
            'flex w-full items-center rounded-xl px-2.5 py-2 text-sm transition-colors duration-150',
            !collapsed && 'gap-3',
            isActive ? 'nav-active' : cn('text-white/60 hover:text-white/90', HOVER)
          )
        }
      >
        <div className="relative h-7 w-7 shrink-0 overflow-hidden rounded-full border border-line">
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
      </NavLink>
    </nav>
  )
}
