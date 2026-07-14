// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, cleanup, fireEvent, act } from '@testing-library/react'
import { MemoryRouter, useNavigate } from 'react-router-dom'
import { MainViews } from './MainViews'

// Stub the pages: this suite is about MOUNT SEMANTICS, not page content, and the
// real pages drag in heavy subtrees (the Memories brain map is an R3F scene).
// Each stub tags its DOM node so we can identify it and — crucially — compare
// node IDENTITY across navigations.
// A function DECLARATION, not a const: vi.mock factories are hoisted above the
// module body, so a `const stub = …` would still be in its temporal dead zone when
// the first factory runs (ReferenceError: Cannot access 'stub' before
// initialization). Declarations are initialized at instantiation, so they're safe.
function stub(name: string) {
  return function Page(): React.JSX.Element {
    return <div data-page={name} />
  }
}
vi.mock('../../pages/Home', () => ({ Home: stub('home') }))
vi.mock('../../pages/Conversations', () => ({ Conversations: stub('conversations') }))
vi.mock('../../pages/Memories', () => ({ Memories: stub('memories') }))
vi.mock('../../pages/Settings', () => ({ Settings: stub('settings') }))
vi.mock('../../pages/Tasks', () => ({ Tasks: stub('tasks') }))
vi.mock('../../pages/Goals', () => ({ Goals: stub('goals') }))
vi.mock('../../pages/Apps', () => ({ Apps: stub('apps') }))
vi.mock('../../pages/Rewind', () => ({ Rewind: stub('rewind') }))
vi.mock('../../pages/LiveConversation', () => ({ LiveConversation: stub('live') }))
vi.mock('../../pages/ConversationDetail', () => ({
  // Renders the prop, so we can assert the matched params actually reach the page.
  ConversationDetail: ({ conversationId }: { conversationId: string }) => (
    <div data-page="detail" data-id={conversationId} />
  )
}))

afterEach(cleanup)

// A real in-app navigation (the thing that must NOT remount panels), driven the
// same way the nav rail drives it — through the router, not by re-rendering.
function Harness({ to }: { to: string }): React.JSX.Element {
  const navigate = useNavigate()
  return (
    <>
      <button onClick={() => navigate(to)}>navigate</button>
      <MainViews />
    </>
  )
}

const renderAt = (path: string, to = '/tasks'): ReturnType<typeof render> =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <Harness to={to} />
    </MemoryRouter>
  )

const panel = (name: string): HTMLElement | null => document.querySelector(`[data-page="${name}"]`)
const isHidden = (name: string): boolean => !!panel(name)?.closest('div.hidden')

// Inactive panels are deliberately NOT mounted during the startup entrance
// animations — mounting all of them (incl. the R3F brain map) up front stalled the
// main thread. They hydrate on a 1800ms timer, after which every panel stays
// mounted for the rest of the session. So the "panels stay mounted" guarantee is a
// POST-hydration one, and a test that doesn't advance the clock is testing the
// pre-hydration window instead (where navigating away really does unmount).
const hydrate = (): void => {
  act(() => {
    vi.advanceTimersByTime(1800)
  })
}

describe('MainViews mount semantics', () => {
  it('keeps a visited panel MOUNTED (same DOM node) when navigating away, once hydrated', () => {
    // This is the entire reason panels render hidden instead of being swapped: if
    // a panel unmounted on navigation, its page state (scroll position, an
    // in-progress chat, the brain map's scene) would be destroyed. Comparing the
    // exact same element OBJECT is the only way to pin that down — an
    // "is in the document" check would still pass if React remounted it.
    vi.useFakeTimers()
    const { getByText } = renderAt('/home', '/tasks')
    hydrate()

    const homeNode = panel('home')
    expect(homeNode).not.toBeNull()
    expect(isHidden('home')).toBe(false)

    fireEvent.click(getByText('navigate'))

    expect(panel('home')).toBe(homeNode) // same node — never unmounted
    expect(isHidden('home')).toBe(true) // just hidden
    expect(isHidden('tasks')).toBe(false)
    vi.useRealTimers()
  })

  it('does not mount inactive panels until hydration (startup animations stay smooth)', () => {
    vi.useFakeTimers()
    renderAt('/home')
    expect(panel('home')).not.toBeNull() // active: mounts immediately
    expect(panel('memories')).toBeNull() // inactive: not yet — this is the point

    hydrate()
    expect(panel('memories')).not.toBeNull() // now mounted, hidden
    expect(isHidden('memories')).toBe(true)
    vi.useRealTimers()
  })

  it('renders the active panel immediately, without waiting for deferred hydration', () => {
    // Inactive panels only mount after the 1800ms hydrate timer. The ACTIVE one
    // must never wait on it, or the landing page would be blank at launch.
    renderAt('/home')
    expect(panel('home')).not.toBeNull()
    expect(isHidden('home')).toBe(false)
  })

  it('renders an exclusive route full-screen INSTEAD of the panel grid', () => {
    renderAt('/conversations/abc123')
    expect(panel('detail')).not.toBeNull()
    // The matched param must reach the page — this is what the old propsFor bag
    // could get wrong without failing typecheck.
    expect(panel('detail')?.getAttribute('data-id')).toBe('abc123')
    // The grid is gone entirely, not merely hidden.
    expect(panel('home')).toBeNull()
  })

  it('matches /conversations/live BEFORE the :id route ("live" is a valid id segment)', () => {
    renderAt('/conversations/live')
    expect(panel('live')).not.toBeNull()
    expect(panel('detail')).toBeNull()
  })

  it('renders the panel grid with nothing active for an unknown pathname', () => {
    vi.useFakeTimers()
    renderAt('/nope')
    hydrate()
    // Every panel is mounted (post-hydration) but none is shown — a blank content
    // area, which is what the pre-refactor code did too.
    expect(panel('home')).not.toBeNull()
    expect(isHidden('home')).toBe(true)
    expect(isHidden('tasks')).toBe(true)
    vi.useRealTimers()
  })
})
