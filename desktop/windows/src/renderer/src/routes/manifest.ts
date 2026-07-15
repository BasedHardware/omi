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

  // Panel routes (kept mounted; inactive ones hidden). Declaration order = DOM
  // order in the grid.
  {
    id: 'home',
    kind: 'panel',
    path: '/home',
    Component: HomePanel,
    nav: { label: 'Home', Icon: House, order: 0 }
  },
  {
    id: 'conversations',
    kind: 'panel',
    path: '/conversations',
    Component: ConversationsPanel,
    nav: { label: 'Conversations', Icon: GanttChartSquare, order: 1 }
  },
  { id: 'memories', kind: 'panel', path: '/memories', Component: MemoriesPanel },
  { id: 'settings', kind: 'panel', path: '/settings', Component: SettingsPanel },
  {
    id: 'tasks',
    kind: 'panel',
    path: '/tasks',
    Component: TasksPanel,
    nav: { label: 'Tasks', Icon: ListChecks, order: 2, activeFor: ['/goals'] }
  },
  { id: 'goals', kind: 'panel', path: '/goals', Component: GoalsPanel },
  {
    id: 'apps',
    kind: 'panel',
    path: '/apps',
    Component: AppsPanel,
    nav: { label: 'Apps', Icon: LayoutGrid, order: 4 }
  },
  {
    id: 'rewind',
    kind: 'panel',
    path: '/rewind',
    Component: RewindPanel,
    nav: { label: 'Rewind', Icon: History, order: 3 }
  }
]

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

// Exact-path match plus any activeFor aliases (e.g. Tasks lights up on /goals).
// NOTE: Sidebar unions this with react-router's NavLink isActive, which also
// matches sub-paths (so Conversations stays highlighted on /conversations/:id).
export function isNavActive(entry: RouteEntry, pathname: string): boolean {
  if (entry.path === pathname) return true
  return entry.nav?.activeFor?.includes(pathname) ?? false
}
