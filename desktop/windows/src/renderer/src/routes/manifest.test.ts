import { describe, it, expect, vi } from 'vitest'

// Mock the page modules so importing the manifest doesn't pull in heavy page
// subtrees (R3F brain map, etc.) — these tests exercise the manifest's routing
// logic, not the pages.
vi.mock('../pages/Home', () => ({ Home: () => null }))
vi.mock('../pages/Conversations', () => ({ Conversations: () => null }))
vi.mock('../pages/Memories', () => ({ Memories: () => null }))
vi.mock('../pages/Settings', () => ({ Settings: () => null }))
vi.mock('../pages/ConversationDetail', () => ({ ConversationDetail: () => null }))
vi.mock('../pages/Tasks', () => ({ Tasks: () => null }))
vi.mock('../pages/Goals', () => ({ Goals: () => null }))
vi.mock('../pages/Apps', () => ({ Apps: () => null }))
vi.mock('../pages/Rewind', () => ({ Rewind: () => null }))
vi.mock('../pages/LiveConversation', () => ({ LiveConversation: () => null }))
vi.mock('../pages/KnowledgeGraph', () => ({ KnowledgeGraph: () => null }))

import {
  resolveRoute,
  navRoutes,
  panelRoutes,
  isNavActive,
  routeManifest,
  pathForShortcut,
  escapesToHome,
  showsPageChrome
} from './manifest'

describe('nav model (macOS parity)', () => {
  // The exact Cmd+N mapping macOS binds in OmiApp.swift:163-214. Pinned as a table
  // because the pre-existing Windows hook had 3 and 4 SWAPPED (3=Tasks, 4=Memories)
  // — and, being dead code that was never called, nothing caught it.
  it.each([
    ['1', '/home'],
    ['2', '/conversations'],
    ['3', '/memories'],
    ['4', '/tasks'],
    ['5', '/rewind'],
    ['6', '/apps'],
    [',', '/settings']
  ])('Ctrl+%s navigates to %s', (key, path) => {
    expect(pathForShortcut(key)).toBe(path)
  })

  it('binds no other keys', () => {
    expect(pathForShortcut('7')).toBeUndefined()
    expect(pathForShortcut('k')).toBeUndefined() // macOS has no command palette
  })

  // DesktopHomeView.swift:1037-1044 — Esc goes Home from these four ONLY.
  it.each(['/conversations', '/memories', '/tasks', '/rewind'])('Esc returns Home from %s', (p) => {
    expect(escapesToHome(p)).toBe(true)
  })

  it.each(['/home', '/settings', '/apps'])('Esc does NOT return Home from %s', (p) => {
    expect(escapesToHome(p)).toBe(false)
  })

  // DesktopHomeView.swift:907-917 — every page but the dashboard wears the chrome.
  it.each(['/conversations', '/memories', '/tasks', '/rewind', '/apps', '/settings'])(
    'shows the PageChromeBar on %s',
    (p) => {
      expect(showsPageChrome(p)).toBe(true)
    }
  )

  it('does NOT show the PageChromeBar on Home (it IS home)', () => {
    expect(showsPageChrome('/home')).toBe(false)
  })

  it('does NOT show the PageChromeBar on exclusive routes (they carry their own Back)', () => {
    // A conversation detail / live transcript has a contextual back arrow in its
    // PageHeader; stacking a "Home" pill on top would be the double affordance
    // macOS avoids.
    expect(showsPageChrome('/conversations/abc123')).toBe(false)
    expect(showsPageChrome('/conversations/live')).toBe(false)
  })
})

describe('route manifest', () => {
  it('redirects /, /live, /chat to /home', () => {
    for (const p of ['/', '/live', '/chat']) {
      expect(resolveRoute(p)).toEqual({ redirectTo: '/home' })
    }
  })

  it('resolves /conversations/live to the live route BEFORE the :id matcher', () => {
    const r = resolveRoute('/conversations/live')
    expect(r && 'entry' in r ? r.entry.id : undefined).toBe('conversation-live')
  })

  it('resolves /conversations/:id to detail and extracts the id', () => {
    const r = resolveRoute('/conversations/abc123')
    expect(r && 'entry' in r ? r.entry.id : undefined).toBe('conversation-detail')
    if (r && 'entry' in r) {
      expect(r.params).toEqual({ id: 'abc123' })
    }
    // That the id reaches ConversationDetail's `conversationId` prop is asserted in
    // MainViews.test.tsx, where the route is actually rendered. It is also enforced
    // at COMPILE time now: the manifest entry renders <ConversationDetail
    // conversationId={params.id} /> itself, so renaming that prop breaks the build.
  })

  it('resolves /knowledge-graph to the full-screen brain-map route', () => {
    const r = resolveRoute('/knowledge-graph')
    expect(r && 'entry' in r ? r.entry.id : undefined).toBe('knowledge-graph')
    expect(r && 'entry' in r ? r.entry.kind : undefined).toBe('exclusive')
  })

  it('resolves a panel route', () => {
    const r = resolveRoute('/home')
    expect(r && 'entry' in r ? r.entry.id : undefined).toBe('home')
  })

  it('returns undefined for an unknown pathname', () => {
    expect(resolveRoute('/nope')).toBeUndefined()
  })

  it('navRoutes are Home, Conversations, Tasks, Rewind, Apps in nav order', () => {
    expect(navRoutes().map((e) => e.id)).toEqual([
      'home',
      'conversations',
      'tasks',
      'rewind',
      'apps'
    ])
  })

  it('panelRoutes preserve DOM order', () => {
    expect(panelRoutes().map((e) => e.id)).toEqual([
      'home',
      'conversations',
      'memories',
      'settings',
      'tasks',
      'goals',
      'apps',
      'rewind'
    ])
  })

  it('isNavActive covers the /goals -> Tasks legacy alias', () => {
    const tasks = routeManifest.find((e) => e.id === 'tasks')
    const home = routeManifest.find((e) => e.id === 'home')
    expect(tasks).toBeDefined()
    expect(home).toBeDefined()
    if (tasks) {
      expect(isNavActive(tasks, '/goals')).toBe(true)
      expect(isNavActive(tasks, '/tasks')).toBe(true)
    }
    if (home) {
      expect(isNavActive(home, '/goals')).toBe(false)
    }
  })
})
