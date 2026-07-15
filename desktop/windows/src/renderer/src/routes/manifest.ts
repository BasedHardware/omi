import { memo, createElement } from 'react'
import type { ComponentType, ReactElement } from 'react'
import type { LucideIcon } from 'lucide-react'
import { House, GanttChartSquare, ListChecks, History, LayoutGrid } from 'lucide-react'
import { Home } from '../pages/Home'
import { Conversations } from '../pages/Conversations'
import { Memories } from '../pages/Memories'
import { Settings } from '../pages/Settings'
import { ConversationDetail } from '../pages/ConversationDetail'
import { Tasks } from '../pages/Tasks'
import { Goals } from '../pages/Goals'
import { Apps } from '../pages/Apps'
import { Rewind } from '../pages/Rewind'
import { LiveConversation } from '../pages/LiveConversation'
import { KnowledgeGraph } from '../pages/KnowledgeGraph'

// Single source of truth for the app's page routing. Both MainViews (what renders
// in the content area) and Sidebar (the nav rail) are driven off this array, so a
// new page is added by APPENDING one RouteEntry here — no edits to MainViews /
// Sidebar / App. This is a behavior-preserving encoding of the previous
// hardcoded routing; keep it that way.

export type RouteKind = 'panel' | 'exclusive' | 'redirect'

export interface RouteNav {
  label: string
  Icon: LucideIcon
  order: number
  // Extra pathnames that should light this nav item up (e.g. Tasks stays active
  // while viewing the legacy /goals alias).
  activeFor?: string[]
}

export interface RouteEntry {
  id: string
  kind: RouteKind
  // Exact-match pathname for panel + redirect entries.
  path?: string
  // Param matcher for exclusive routes: returns extracted params, or null if the
  // pathname doesn't match this entry.
  match?: (pathname: string) => Record<string, string> | null
  // Destination for kind: 'redirect'.
  redirectTo?: string
  // Panel page. Panels take no props and are memo-wrapped (see below).
  Component?: ComponentType
  // Exclusive routes render THEMSELVES from their matched params, rather than
  // handing a component + a loose props bag to the caller. That keeps the prop
  // contract statically checked: rename ConversationDetail's `conversationId` and
  // this file stops compiling. The obvious alternative — `ComponentType<any>` plus
  // a `propsFor` that returns Record<string, unknown> — type-checks happily while
  // passing the page an undefined prop at runtime.
  render?: (params: Record<string, string>) => ReactElement
  // Sidebar nav entry; absent for pages with no rail item (Memories/Goals/Settings).
  nav?: RouteNav
  // Ctrl+<key> jumps here. Independent of `nav` on purpose: Memories and Settings
  // have no rail item but DO have a shortcut, so this cannot be folded into RouteNav.
  // Mirrors macOS's Cmd+1..6 / Cmd+, (OmiApp.swift:163-214).
  shortcut?: string
  // Esc returns to Home from this page. macOS allows it from conversations /
  // memories / tasks / rewind only — NOT Settings, NOT Apps
  // (DesktopHomeView.swift:1037-1044, navigateHomeOnEscapeIfNeeded).
  escapeToHome?: boolean
}

// Every panel stays mounted (inactive ones hidden) so tab switches are instant.
// Pages take no props, so without memo they ALL re-render on every navigation
// (MainViews re-renders when the pathname changes) — reconciling heavy subtrees
// like the Memories brain map (an R3F scene) or large lists, which is what made
// tab switches lag. memo() makes a page re-render only from its OWN hooks/state,
// never from a parent navigation, so changing tabs just toggles visibility.
const HomePanel = memo(Home)
const ConversationsPanel = memo(Conversations)
const MemoriesPanel = memo(Memories)
const SettingsPanel = memo(Settings)
const TasksPanel = memo(Tasks)
const GoalsPanel = memo(Goals)
const AppsPanel = memo(Apps)
const RewindPanel = memo(Rewind)

export const routeManifest: RouteEntry[] = [
  // Redirects: legacy/blank routes fold into Home (Home merges the old Chat and
  // Record screens).
  { id: 'root-redirect', kind: 'redirect', path: '/', redirectTo: '/home' },
  { id: 'live-redirect', kind: 'redirect', path: '/live', redirectTo: '/home' },
  { id: 'chat-redirect', kind: 'redirect', path: '/chat', redirectTo: '/home' },

  // Exclusive full-screen routes (replace the whole panel grid). Order matters:
  // /conversations/live must be checked before the :id matcher, because 'live'
  // is itself a valid :id segment. resolveRoute iterates in array order, so this
  // ordering IS the precedence.
  {
    id: 'conversation-live',
    kind: 'exclusive',
    match: (pathname) => (pathname === '/conversations/live' ? {} : null),
    render: () => createElement(LiveConversation)
  },
  {
    id: 'conversation-detail',
    kind: 'exclusive',
    match: (pathname) => {
      const m = pathname.match(/^\/conversations\/([^/]+)$/)
      return m ? { id: m[1] } : null
    },
    // createElement, not JSX, so this stays a .ts module: a .tsx here would trip
    // react-refresh/only-export-components (the file exports data + helpers, not
    // just components). Type-checking is identical — rename ConversationDetail's
    // `conversationId` and this line stops compiling.
    render: (params) => createElement(ConversationDetail, { conversationId: params.id })
  },
  {
    // Full-screen interactive brain map (BrainGraph mounted with OrbitControls).
    // Reached from the expand affordance on the Memories inline Brain Map card.
    id: 'knowledge-graph',
    kind: 'exclusive',
    match: (pathname) => (pathname === '/knowledge-graph' ? {} : null),
    render: () => createElement(KnowledgeGraph)
  },

  // Panel routes (kept mounted; inactive ones hidden). Declaration order = DOM
  // order in the grid.
  {
    id: 'home',
    kind: 'panel',
    path: '/home',
    Component: HomePanel,
    nav: { label: 'Home', Icon: House, order: 0 },
    shortcut: '1'
  },
  {
    id: 'conversations',
    kind: 'panel',
    path: '/conversations',
    Component: ConversationsPanel,
    nav: { label: 'Conversations', Icon: GanttChartSquare, order: 1 },
    shortcut: '2',
    escapeToHome: true
  },
  {
    id: 'memories',
    kind: 'panel',
    path: '/memories',
    Component: MemoriesPanel,
    shortcut: '3',
    escapeToHome: true
  },
  { id: 'settings', kind: 'panel', path: '/settings', Component: SettingsPanel, shortcut: ',' },
  {
    id: 'tasks',
    kind: 'panel',
    path: '/tasks',
    Component: TasksPanel,
    nav: { label: 'Tasks', Icon: ListChecks, order: 2, activeFor: ['/goals'] },
    shortcut: '4',
    escapeToHome: true
  },
  { id: 'goals', kind: 'panel', path: '/goals', Component: GoalsPanel },
  {
    id: 'apps',
    kind: 'panel',
    path: '/apps',
    Component: AppsPanel,
    nav: { label: 'Apps', Icon: LayoutGrid, order: 4 },
    shortcut: '6'
  },
  {
    id: 'rewind',
    kind: 'panel',
    path: '/rewind',
    Component: RewindPanel,
    nav: { label: 'Rewind', Icon: History, order: 3 },
    shortcut: '5',
    escapeToHome: true
  }
]

// Home is the one page with no PageChromeBar and no Esc-to-home (it IS home).
export const HOME_PATH = '/home'

export type ResolveResult =
  | { entry: RouteEntry; params: Record<string, string> }
  | { redirectTo: string }

// Resolve a pathname to a redirect, an exclusive route (+ params), or a panel
// route. Returns undefined for an unknown pathname (MainViews then renders the
// panel grid with nothing active — a blank content area, as before).
export function resolveRoute(pathname: string): ResolveResult | undefined {
  for (const entry of routeManifest) {
    if (entry.kind === 'redirect') {
      if (entry.path === pathname) return { redirectTo: entry.redirectTo as string }
      continue
    }
    if (entry.kind === 'exclusive') {
      const params = entry.match?.(pathname)
      if (params) return { entry, params }
      continue
    }
    // panel
    if (entry.path === pathname) return { entry, params: {} }
  }
  return undefined
}

// Panel entries in declaration (DOM) order.
export function panelRoutes(): RouteEntry[] {
  return routeManifest.filter((e) => e.kind === 'panel')
}

// Nav entries, sorted by their declared order.
export function navRoutes(): RouteEntry[] {
  return routeManifest
    .filter((e) => e.nav)
    .sort((a, b) => (a.nav as RouteNav).order - (b.nav as RouteNav).order)
}

// Destination for a Ctrl+<key> press, or undefined if the key isn't bound.
export function pathForShortcut(key: string): string | undefined {
  return routeManifest.find((e) => e.shortcut === key)?.path
}

// Does Esc return Home from this pathname? Only the four pages macOS allows it on.
export function escapesToHome(pathname: string): boolean {
  return routeManifest.some((e) => e.path === pathname && e.escapeToHome === true)
}

// Every page except Home gets the PageChromeBar. Exclusive routes (a conversation
// detail, the live transcript) carry their own PageHeader with a contextual Back
// arrow, so they're excluded — a "Home" pill above their own back button would be
// the same double-affordance macOS avoids.
export function showsPageChrome(pathname: string): boolean {
  const resolved = resolveRoute(pathname)
  if (!resolved || !('entry' in resolved)) return false
  if (resolved.entry.kind !== 'panel') return false
  return resolved.entry.path !== HOME_PATH
}

// Exact-path match plus any activeFor aliases (e.g. Tasks lights up on /goals).
// NOTE: Sidebar unions this with react-router's NavLink isActive, which also
// matches sub-paths (so Conversations stays highlighted on /conversations/:id).
export function isNavActive(entry: RouteEntry, pathname: string): boolean {
  if (entry.path === pathname) return true
  return entry.nav?.activeFor?.includes(pathname) ?? false
}
