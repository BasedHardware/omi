// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from 'vitest'

// The card's only I/O: Firebase auth (name/uid) and the Python-backend client.
const { get, currentUser } = vi.hoisted(() => ({
  get: vi.fn(),
  currentUser: { uid: 'u1', displayName: 'Ada' } as {
    uid: string
    displayName: string | null
  } | null
}))
vi.mock('../firebase', () => ({
  auth: {
    get currentUser() {
      return currentUser
    }
  }
}))
vi.mock('../apiClient', () => ({ omiApi: { get } }))

import {
  buildAboutUserCard,
  getAboutUserCard,
  refreshAboutUserCard,
  renderAboutUserCard,
  resetAboutUserCard,
  truncateFact,
  whenAboutUserCardSettled
} from './aboutUser'

beforeEach(() => {
  get.mockReset()
  resetAboutUserCard()
})

describe('renderAboutUserCard — exact template', () => {
  it('renders name, facts, and non-zero counts', () => {
    expect(
      renderAboutUserCard({
        name: 'Ada',
        facts: ['Ships fast.', 'Has a dog.'],
        overdue: 2,
        dueToday: 3
      })
    ).toBe(
      [
        '<about_user>',
        'Name: Ada',
        'What Omi knows about them:',
        '- Ships fast.',
        '- Has a dog.',
        'Right now: 2 overdue, 3 due today.',
        '(This is a quick snapshot, not the exact current list.)',
        '</about_user>'
      ].join('\n')
    )
  })

  it('omits the Name line when the name is empty, and says so when nothing is saved', () => {
    expect(renderAboutUserCard({ name: '', facts: [], overdue: 0, dueToday: 0 })).toBe(
      [
        '<about_user>',
        'What Omi knows about them:',
        '- Nothing saved yet.',
        'Right now: nothing overdue or due today.',
        '(This is a quick snapshot, not the exact current list.)',
        '</about_user>'
      ].join('\n')
    )
  })

  // Phase-A deviation from macOS, deliberately asserted: the hedge stays, but it
  // must not name get_tasks / get_action_items (no tools exist on Windows yet).
  it('hedges without naming a nonexistent tool', () => {
    const card = renderAboutUserCard({ name: 'Ada', facts: [], overdue: 0, dueToday: 0 })
    expect(card).toContain('(This is a quick snapshot, not the exact current list.)')
    expect(card).not.toContain('get_tasks')
    expect(card).not.toContain('get_action_items')
  })
})

describe('truncateFact — the 120-char boundary', () => {
  it('keeps a fact of exactly 120 chars intact', () => {
    const at = 'a'.repeat(120)
    expect(truncateFact(at)).toBe(at)
  })

  it('truncates 121 chars to the first 117 plus an ellipsis', () => {
    const over = 'a'.repeat(121)
    const out = truncateFact(over)
    expect(out).toBe(`${'a'.repeat(117)}…`)
    expect(out).toHaveLength(118)
  })

  it('drops a blank fact', () => {
    expect(truncateFact('   ')).toBeNull()
  })
})

describe('buildAboutUserCard — data sources', () => {
  it('caps facts at 8 and truncates each one', async () => {
    const facts = Array.from({ length: 12 }, (_, i) => `fact ${i}`)
    const card = await buildAboutUserCard({
      name: () => 'Ada',
      facts: async () => facts.slice(0, 8),
      counts: async () => ({ overdue: 1, dueToday: 0 })
    })
    expect(card).toContain('- fact 7')
    expect(card).not.toContain('- fact 8')
    expect(card).toContain('Right now: 1 overdue, 0 due today.')
  })

  it('still renders when BOTH fetchers reject (empty facts, zero counts, no throw)', async () => {
    const card = await buildAboutUserCard({
      name: () => 'Ada',
      facts: async () => {
        throw new Error('memories down')
      },
      counts: async () => {
        throw new Error('tasks down')
      }
    })
    expect(card).toContain('Name: Ada')
    expect(card).toContain('- Nothing saved yet.')
    expect(card).toContain('Right now: nothing overdue or due today.')
  })

  it('fetches memories newest-first and the task counts from the live endpoints', async () => {
    get.mockImplementation((url: string) => {
      if (url === '/v3/memories') {
        return Promise.resolve({
          data: [
            { content: 'older', created_at: '2026-01-01T00:00:00Z' },
            { content: 'newer', created_at: '2026-07-01T00:00:00Z' }
          ]
        })
      }
      return Promise.resolve({
        data: {
          action_items: [
            { id: '1', description: 'late', completed: false, due_at: '2000-01-01T00:00:00Z' },
            { id: '2', description: 'done', completed: true, due_at: '2000-01-01T00:00:00Z' }
          ],
          has_more: false
        }
      })
    })
    const card = await buildAboutUserCard()
    expect(card).toContain('Name: Ada')
    expect(card.indexOf('- newer')).toBeLessThan(card.indexOf('- older'))
    expect(card).toContain('Right now: 1 overdue, 0 due today.')
  })
})

describe('getAboutUserCard / refreshAboutUserCard — cache', () => {
  it('is empty before the first refresh and populated after it settles', async () => {
    get.mockResolvedValue({ data: [] })
    expect(getAboutUserCard()).toBe('')
    refreshAboutUserCard()
    await whenAboutUserCardSettled()
    expect(getAboutUserCard()).toContain('<about_user>')
  })

  it('does not serve another account’s cached card', async () => {
    get.mockResolvedValue({ data: [] })
    refreshAboutUserCard()
    await whenAboutUserCardSettled()
    expect(getAboutUserCard()).toContain('<about_user>')
    currentUser!.uid = 'u2'
    expect(getAboutUserCard()).toBe('')
    currentUser!.uid = 'u1'
  })

  // The build's fetches run against whatever token is current when they LAND, so
  // an account switch mid-build yields the NEW user's data. Filing that under the
  // uid captured at build start would leak u2's memories to u1 on their return.
  it('discards a build whose account switched away while it was in flight', async () => {
    let release: (v: unknown) => void = () => {}
    get.mockReturnValue(new Promise((r) => (release = r)))

    refreshAboutUserCard() // starts for u1
    currentUser!.uid = 'u2'
    currentUser!.displayName = 'Grace'
    release({ data: [{ content: 'u2 secret', created_at: '2026-07-01T00:00:00Z' }] })
    await whenAboutUserCardSettled()

    expect(getAboutUserCard()).toBe('') // u2 has no card of its own yet
    currentUser!.uid = 'u1'
    currentUser!.displayName = 'Ada'
    expect(getAboutUserCard()).toBe('') // and u1 never inherits u2's build
  })

  // Dedupe is per-account: the switched-to account must be able to start its own
  // build even while the abandoned one is still settling.
  it('starts a fresh build for the new account despite an in-flight one', async () => {
    get.mockReturnValue(new Promise(() => {})) // u1's build never settles
    refreshAboutUserCard()

    currentUser!.uid = 'u2'
    currentUser!.displayName = 'Grace'
    get.mockResolvedValue({ data: [] })
    refreshAboutUserCard()
    await whenAboutUserCardSettled()

    expect(getAboutUserCard()).toContain('Name: Grace')
    currentUser!.uid = 'u1'
    currentUser!.displayName = 'Ada'
  })
})
