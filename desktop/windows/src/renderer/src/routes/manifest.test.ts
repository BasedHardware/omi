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

import { resolveRoute, navRoutes, panelRoutes, isNavActive, routeManifest } from './manifest'

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
