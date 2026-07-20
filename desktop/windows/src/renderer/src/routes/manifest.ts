import { memo, createElement } from 'react'
import type { ComponentType, ReactElement } from 'react'
import type { LucideIcon } from 'lucide-react'
import { GanttChartSquare, History, House, LayoutGrid, ListChecks } from 'lucide-react'
import { Apps } from '../pages/Apps'
import { ConversationDetail } from '../pages/ConversationDetail'
import { Conversations } from '../pages/Conversations'
import { Goals } from '../pages/Goals'
import { Home } from '../pages/Home'
import { LiveConversation } from '../pages/LiveConversation'
import { Memories } from '../pages/Memories'
import { Rewind } from '../pages/Rewind'
import { Settings } from '../pages/Settings'
import { Tasks } from '../pages/Tasks'

export type RouteKind = 'panel' | 'exclusive' | 'redirect'

export type RouteNav = {
  label: string
  Icon: LucideIcon
  order: number
  activeFor?: string[]
}

export type RouteEntry = {
  id: string
  kind: RouteKind
  path?: string
  match?: (pathname: string) => Record<string, string> | null
  redirectTo?: string
  Component?: ComponentType
  render?: (params: Record<string, string>) => ReactElement
  nav?: RouteNav
}

const HomePanel = memo(Home)
const ConversationsPanel = memo(Conversations)
const MemoriesPanel = memo(Memories)
const SettingsPanel = memo(Settings)
const TasksPanel = memo(Tasks)
const GoalsPanel = memo(Goals)
const AppsPanel = memo(Apps)
const RewindPanel = memo(Rewind)

export const routeManifest: RouteEntry[] = [
  { id: 'root', kind: 'redirect', path: '/', redirectTo: '/home' },
  { id: 'live', kind: 'redirect', path: '/live', redirectTo: '/home' },
  { id: 'chat', kind: 'redirect', path: '/chat', redirectTo: '/home' },
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
      const match = pathname.match(/^\/conversations\/([^/]+)$/)
      return match ? { id: match[1] } : null
    },
    render: (params) => createElement(ConversationDetail, { conversationId: params.id })
  },
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
    id: 'rewind',
    kind: 'panel',
    path: '/rewind',
    Component: RewindPanel,
    nav: { label: 'Rewind', Icon: History, order: 3 }
  },
  {
    id: 'apps',
    kind: 'panel',
    path: '/apps',
    Component: AppsPanel,
    nav: { label: 'Apps', Icon: LayoutGrid, order: 4 }
  }
]

export function resolveRoute(pathname: string):
  | { entry: RouteEntry; params: Record<string, string> }
  | { redirectTo: string }
  | undefined {
  for (const entry of routeManifest) {
    if (entry.kind === 'redirect' && entry.path === pathname) {
      return { redirectTo: entry.redirectTo as string }
    }
    if (entry.kind === 'exclusive') {
      const params = entry.match?.(pathname)
      if (params) return { entry, params }
    }
    if (entry.kind === 'panel' && entry.path === pathname) return { entry, params: {} }
  }
  return undefined
}

export function panelRoutes(): RouteEntry[] {
  return routeManifest.filter((entry) => entry.kind === 'panel')
}

export function navRoutes(): RouteEntry[] {
  return routeManifest
    .filter((entry) => entry.nav)
    .sort((left, right) => (left.nav?.order ?? 0) - (right.nav?.order ?? 0))
}

export function isNavActive(entry: RouteEntry, pathname: string): boolean {
  return entry.path === pathname || entry.nav?.activeFor?.includes(pathname) === true
}
