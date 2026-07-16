// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, cleanup, screen, fireEvent, waitFor, within } from '@testing-library/react'

// One mock for the whole api surface. `omiGet` switches on the url so the detail
// fetch and the reviews fetch return distinct fixtures; `omiPost` records review
// writes so we can assert the query-param shape (and that PATCH is never used).
const { omiGet, omiPost } = vi.hoisted(() => ({ omiGet: vi.fn(), omiPost: vi.fn() }))
vi.mock('../../lib/apiClient', () => ({
  omiApi: { get: omiGet, post: omiPost },
  desktopApi: { post: vi.fn() }
}))
// Stable current-user id so the "your review" match + optimistic build are deterministic.
vi.mock('../../lib/persistentCache', () => ({ getCacheUid: () => 'me' }))

import { AppDetailSheet } from './AppDetailSheet'
import type { App, AppCatalogItem, AppReview } from '../../lib/omiApi.generated'

const CARD: AppCatalogItem = {
  id: 'app-1',
  name: 'Weather Bot',
  author: 'Acme',
  description: 'Tells you the weather.',
  category: 'productivity',
  image: 'https://ex.com/i.png',
  capabilities: ['external_integration', 'chat']
}

const DETAIL: App = {
  id: 'app-1',
  name: 'Weather Bot',
  author: 'Acme',
  description: 'Tells you the weather.',
  category: 'productivity',
  image: 'https://ex.com/i.png',
  capabilities: ['external_integration', 'chat'],
  rating_avg: 4.5,
  rating_count: 12,
  installs: 3400,
  external_integration: {
    auth_steps: [{ name: 'Connect account', url: 'https://ex.com/setup' }],
    setup_completed_url: 'https://ex.com/done'
  }
}

const OTHER_REVIEW: AppReview = {
  score: 5,
  review: 'Love it',
  uid: 'someone-else',
  username: 'Dana',
  rated_at: '2026-01-01T00:00:00Z'
}

function mockGets(detail: App, reviews: AppReview[]): void {
  omiGet.mockImplementation((url: string) => {
    if (url.endsWith('/reviews')) return Promise.resolve({ data: reviews })
    return Promise.resolve({ data: detail })
  })
}

function renderSheet(props: Partial<React.ComponentProps<typeof AppDetailSheet>> = {}): {
  onToggle: ReturnType<typeof vi.fn>
  onClose: ReturnType<typeof vi.fn>
} {
  const onToggle = vi.fn()
  const onClose = vi.fn()
  render(
    <AppDetailSheet
      app={CARD}
      enabled={false}
      busy={false}
      settingUp={false}
      onToggle={onToggle}
      onClose={onClose}
      {...props}
    />
  )
  return { onToggle, onClose }
}

beforeEach(() => {
  omiGet.mockReset()
  omiPost.mockReset()
  omiPost.mockResolvedValue({ data: { status: 'ok' } })
  ;(window as unknown as { omi: Record<string, unknown> }).omi = {
    openExternalUrl: vi.fn().mockResolvedValue(true),
    checkAppSetup: vi.fn().mockResolvedValue(false)
  }
})

afterEach(cleanup)

describe('AppDetailSheet layout', () => {
  it('renders every section in the exact macOS order', async () => {
    mockGets(DETAIL, [OTHER_REVIEW])
    renderSheet()
    await waitFor(() => expect(screen.getByText('(12)')).toBeTruthy()) // detail landed

    const headings = Array.from(document.querySelectorAll('h3')).map((h) => h.textContent)
    expect(headings).toEqual(['About', 'Setup', 'Capabilities', 'Category', 'Reviews'])
  })

  it('shows rating (only with count) and installs in the header', async () => {
    mockGets(DETAIL, [])
    renderSheet()
    await waitFor(() => expect(screen.getByText('4.5')).toBeTruthy())
    expect(screen.getByText('(12)')).toBeTruthy()
    expect(screen.getByText('3,400 installs')).toBeTruthy()
  })

  it('hides rating when rating_count is 0', async () => {
    mockGets({ ...DETAIL, rating_avg: 0, rating_count: 0, installs: 0 }, [])
    renderSheet()
    await waitFor(() => expect(screen.getByText('About')).toBeTruthy())
    expect(screen.queryByText('(0)')).toBeNull()
    expect(screen.queryByText(/installs/)).toBeNull()
  })

  it('renders numbered setup steps that open the step url with ?uid=', async () => {
    mockGets(DETAIL, [])
    renderSheet()
    await waitFor(() => expect(screen.getByText('Connect account')).toBeTruthy())
    expect(screen.getByText('Click to complete')).toBeTruthy()
    fireEvent.click(screen.getByText('Connect account'))
    expect(
      (window as unknown as { omi: { openExternalUrl: ReturnType<typeof vi.fn> } }).omi
        .openExternalUrl
    ).toHaveBeenCalledWith('https://ex.com/setup?uid=me')
  })

  it('omits the Setup section when there are no auth steps', async () => {
    mockGets({ ...DETAIL, external_integration: null }, [])
    renderSheet()
    await waitFor(() => expect(screen.getByText('About')).toBeTruthy())
    expect(screen.queryByText('Setup')).toBeNull()
  })
})

describe('AppDetailSheet primary button (tri-state)', () => {
  it('shows Install when not enabled and calls onToggle', async () => {
    mockGets(DETAIL, [])
    const { onToggle } = renderSheet({ enabled: false })
    await waitFor(() => expect(screen.getByText('About')).toBeTruthy())
    const btn = screen.getByRole('button', { name: /^Install$/ })
    fireEvent.click(btn)
    expect(onToggle).toHaveBeenCalledTimes(1)
    expect(screen.queryByLabelText('Disable app')).toBeNull()
  })

  it('shows Installed + a disable trash when enabled', async () => {
    mockGets(DETAIL, [])
    const { onToggle } = renderSheet({ enabled: true })
    await waitFor(() => expect(screen.getByText('Installed')).toBeTruthy())
    const trash = screen.getByLabelText('Disable app')
    fireEvent.click(trash)
    expect(onToggle).toHaveBeenCalledTimes(1)
  })

  it('shows "Setting up…" while a setup poll is in flight', async () => {
    mockGets(DETAIL, [])
    renderSheet({ settingUp: true })
    await waitFor(() => expect(screen.getByText('Setting up…')).toBeTruthy())
  })
})

describe('AppDetailSheet reviews', () => {
  it('reflects a review score as filled stars', async () => {
    mockGets(DETAIL, [OTHER_REVIEW])
    renderSheet()
    const card = await screen.findByText('Love it')
    const filled = card.closest('.rounded-xl')!.querySelectorAll('.fill-amber-400')
    expect(filled.length).toBe(5) // 5-star review
  })

  it('shows the empty copy when there are no reviews', async () => {
    mockGets(DETAIL, [])
    renderSheet()
    await waitFor(() =>
      expect(screen.getByText('No reviews yet. Be the first to review this app.')).toBeTruthy()
    )
  })

  it('gates the button label on user_review only (Add when none)', async () => {
    mockGets(DETAIL, [OTHER_REVIEW])
    renderSheet({ enabled: false })
    await waitFor(() => expect(screen.getByText('Add review')).toBeTruthy())
    expect(screen.queryByText('Edit your review')).toBeNull()
  })

  it('shows Edit + a "Your review" card when the user already reviewed', async () => {
    const mine: AppReview = {
      score: 3,
      review: 'It is fine',
      uid: 'me',
      username: 'Me',
      rated_at: '2026-01-02T00:00:00Z'
    }
    mockGets({ ...DETAIL, user_review: mine }, [mine, OTHER_REVIEW])
    renderSheet()
    await waitFor(() => expect(screen.getByText('Edit your review')).toBeTruthy())
    expect(screen.getByText('Your review')).toBeTruthy()
    expect(screen.getByText('It is fine')).toBeTruthy()
  })
})

describe('AppDetailSheet add/edit review submit', () => {
  it('POSTs a NEW review with app_id as a query param (never PATCH) + optimistic + re-fetch', async () => {
    mockGets(DETAIL, [OTHER_REVIEW])
    renderSheet()
    await waitFor(() => expect(screen.getByText('Add review')).toBeTruthy())
    omiGet.mockClear() // so we can assert the post-submit reviews re-fetch
    // After the upsert the server has the review; the reconciling re-fetch returns it.
    const persisted: AppReview = {
      score: 4,
      review: 'Solid app',
      uid: 'me',
      username: null,
      rated_at: '2026-01-03T00:00:00Z'
    }
    mockGets(DETAIL, [persisted, OTHER_REVIEW])

    fireEvent.click(screen.getByText('Add review'))
    const dialog = await screen.findByText('Add a review')
    const root = dialog.closest('[role="dialog"]') as HTMLElement
    fireEvent.click(within(root).getByLabelText('4 stars'))
    fireEvent.change(within(root).getByPlaceholderText(/Share what you think/), {
      target: { value: 'Solid app' }
    })
    fireEvent.click(within(root).getByText('Submit review'))

    await waitFor(() => expect(omiPost).toHaveBeenCalled())
    const [url, body, config] = omiPost.mock.calls[0]
    expect(url).toBe('/v1/apps/review')
    expect(body).toEqual({ score: 4, review: 'Solid app' })
    expect(config).toEqual({ params: { app_id: 'app-1' } })
    // Every write goes to the single upsert endpoint — never a PATCH route.
    expect(omiPost.mock.calls.every((c) => c[0] === '/v1/apps/review')).toBe(true)

    // Optimistic render of the just-submitted review, then a reviews re-fetch fired.
    await waitFor(() => expect(screen.getByText('Solid app')).toBeTruthy())
    expect(omiGet.mock.calls.some((c) => String(c[0]).endsWith('/reviews'))).toBe(true)
  })

  it('EDIT also POSTs to /v1/apps/review (upsert) — not a PATCH', async () => {
    const mine: AppReview = {
      score: 2,
      review: 'Meh',
      uid: 'me',
      username: 'Me',
      rated_at: '2026-01-02T00:00:00Z'
    }
    mockGets({ ...DETAIL, user_review: mine }, [mine])
    renderSheet()
    await waitFor(() => expect(screen.getByText('Edit your review')).toBeTruthy())

    fireEvent.click(screen.getByText('Edit your review'))
    const dialog = await screen.findByText('Edit your review', { selector: 'h2, .font-display' })
    const root = dialog.closest('[role="dialog"]') as HTMLElement
    fireEvent.click(within(root).getByLabelText('5 stars'))
    fireEvent.click(within(root).getByText('Update review'))

    await waitFor(() => expect(omiPost).toHaveBeenCalled())
    expect(omiPost.mock.calls[0][0]).toBe('/v1/apps/review')
    expect(omiPost.mock.calls[0][2]).toEqual({ params: { app_id: 'app-1' } })
  })

  it('renders the submitted values, not anything off the response body', async () => {
    // Even if the POST body carried a review shape, the sheet must ignore it and use
    // the submitted values (backend actually returns just {status:'ok'}). Give the
    // response a misleading review and prove it never surfaces.
    mockGets(DETAIL, [])
    omiPost.mockResolvedValue({ data: { status: 'ok', score: 1, review: 'DECODED_FROM_BODY' } })
    renderSheet()
    await waitFor(() => expect(screen.getByText('Add review')).toBeTruthy())
    // The reconciling re-fetch returns the genuinely persisted review.
    mockGets(DETAIL, [
      {
        score: 3,
        review: 'From the values, not the body',
        uid: 'me',
        username: null,
        rated_at: 'x'
      }
    ])
    fireEvent.click(screen.getByText('Add review'))
    const dialog = await screen.findByText('Add a review')
    const root = dialog.closest('[role="dialog"]') as HTMLElement
    fireEvent.click(within(root).getByLabelText('3 stars'))
    fireEvent.change(within(root).getByPlaceholderText(/Share what you think/), {
      target: { value: 'From the values, not the body' }
    })
    fireEvent.click(within(root).getByText('Submit review'))
    await waitFor(() => expect(screen.getByText('From the values, not the body')).toBeTruthy())
    expect(screen.queryByText('DECODED_FROM_BODY')).toBeNull()
  })
})
