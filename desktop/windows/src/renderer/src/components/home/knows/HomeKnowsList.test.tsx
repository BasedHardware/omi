// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, cleanup, fireEvent, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { HomeKnowsList } from './HomeKnowsList'
import { dashboardIntelligence } from '../../../lib/intelligence/dashboardStore'
import { useHubKnowsPresence } from '../hub/hubKnowsSlot'

vi.mock('../../../lib/persistentCache', () => ({ getCacheUid: () => 'uid-1' }))
vi.mock('../../../lib/apiClient', () => ({
  omiApi: { get: vi.fn(), post: vi.fn(), delete: vi.fn() }
}))

const fetchAllActionItems = vi.hoisted(() => vi.fn())
vi.mock('../../../lib/actionItems', () => ({ fetchAllActionItems }))

const insightRecent = vi.fn()

const NOW = Date.parse('2026-08-16T12:00:00Z')
const FUTURE = '2026-08-16T18:00:00Z'

function stubIntelligence(over: Partial<ReturnType<typeof dashboardIntelligence.getState>> = {}) {
  const base = {
    accountGeneration: 3,
    recommendations: [],
    goals: [],
    selectedGoalDetail: null,
    focusReplacementGoalId: null,
    error: null,
    isLoading: false,
    pendingFeedbackCount: 0
  }
  vi.spyOn(dashboardIntelligence, 'getState').mockReturnValue({ ...base, ...over })
  vi.spyOn(dashboardIntelligence, 'subscribe').mockReturnValue(() => {})
  vi.spyOn(dashboardIntelligence, 'load').mockResolvedValue()
}

const recommendation = (over: Record<string, unknown> = {}) => ({
  id: 'out-1:dk-1',
  headline: 'Finish the report',
  whyNow: 'Due soon',
  contextLabel: null,
  recommendedAction: 'Open it',
  destination: { kind: 'task', taskId: 'task-1', workstreamId: null },
  wire: {
    interventionId: 'iv-1',
    outputVersion: 'out-1',
    subjectKind: 'task',
    subjectId: 'task-1',
    feedbackSubjectKind: 'task',
    feedbackSubjectId: 'task-1',
    destinationTaskId: null,
    destinationWorkstreamId: null,
    headline: 'Finish the report',
    whyNow: 'Due soon',
    contextLabel: null,
    recommendedAction: 'Open it',
    alternativeAction: null,
    evidencePreview: '',
    dedupeKey: 'dk-1',
    expiresAt: FUTURE
  },
  ...over
})

function mount(): ReturnType<typeof render> {
  return render(
    <MemoryRouter>
      <HomeKnowsList onAskPrefill={onAskPrefill} />
    </MemoryRouter>
  )
}

let onAskPrefill: ReturnType<typeof vi.fn>

function PresenceProbe(): React.JSX.Element {
  const present = useHubKnowsPresence()
  return <span data-testid="presence">{String(present)}</span>
}

beforeEach(() => {
  onAskPrefill = vi.fn()
  fetchAllActionItems.mockResolvedValue([
    {
      id: 7,
      description: 'Pay the invoice',
      completed: false,
      dueAt: NOW + 1000,
      createdAt: NOW - 5000
    },
    { id: 8, description: 'Done thing', completed: true, dueAt: null, createdAt: NOW - 1000 }
  ])
  insightRecent.mockResolvedValue([])
  ;(window as unknown as { omi: { insightRecent: typeof insightRecent } }).omi = { insightRecent }
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe('HomeKnowsList', () => {
  it('renders composed rows from open tasks and reports presence to the hub slot', async () => {
    stubIntelligence()
    render(
      <MemoryRouter>
        <HomeKnowsList onAskPrefill={onAskPrefill} />
        <PresenceProbe />
      </MemoryRouter>
    )
    await waitFor(() => expect(screen.getByText('Pay the invoice')).toBeTruthy())
    expect(screen.queryByText('Done thing')).toBeNull()
    expect(screen.getByTestId('presence').textContent).toBe('true')
  })

  it('recommendation rows lead the insight slot and open runs the store open flow', async () => {
    stubIntelligence({ recommendations: [recommendation() as never] })
    const open = vi.spyOn(dashboardIntelligence, 'openRecommendation').mockResolvedValue(true)
    mount()
    await waitFor(() => expect(screen.getByText('Finish the report')).toBeTruthy())
    fireEvent.click(screen.getByText('Finish the report'))
    expect(open).toHaveBeenCalledWith('out-1:dk-1', expect.any(Function))
  })

  it('dismissing a recommendation opens the optional-reason popover; a chosen reason flows through', async () => {
    stubIntelligence({ recommendations: [recommendation() as never] })
    const dismiss = vi.spyOn(dashboardIntelligence, 'dismiss').mockResolvedValue()
    mount()
    await waitFor(() => expect(screen.getByText('Finish the report')).toBeTruthy())
    const row = screen.getByTestId('home-knows-insight-out-1:dk-1')
    fireEvent.click(row.querySelector('[aria-label="Dismiss"]') as Element)
    expect(screen.getByText('Optional reason')).toBeTruthy()
    fireEvent.click(screen.getByText('Not useful'))
    expect(dismiss).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'out-1:dk-1' }),
      'not_useful'
    )
  })

  it('closing the reason popover without choosing still dismisses with reason null', async () => {
    stubIntelligence({ recommendations: [recommendation() as never] })
    const dismiss = vi.spyOn(dashboardIntelligence, 'dismiss').mockResolvedValue()
    mount()
    await waitFor(() => expect(screen.getByText('Finish the report')).toBeTruthy())
    const row = screen.getByTestId('home-knows-insight-out-1:dk-1')
    fireEvent.click(row.querySelector('[aria-label="Dismiss"]') as Element)
    fireEvent.click(screen.getByLabelText('Dismiss without a reason'))
    expect(dismiss).toHaveBeenCalledWith(expect.objectContaining({ id: 'out-1:dk-1' }), null)
  })

  it('task rows dismiss session-locally without touching the store', async () => {
    stubIntelligence()
    const dismiss = vi.spyOn(dashboardIntelligence, 'dismiss').mockResolvedValue()
    mount()
    await waitFor(() => expect(screen.getByText('Pay the invoice')).toBeTruthy())
    const row = screen.getByTestId('home-knows-task-7')
    fireEvent.click(row.querySelector('[aria-label="Dismiss"]') as Element)
    await waitFor(() => expect(screen.queryByText('Pay the invoice')).toBeNull())
    expect(dismiss).not.toHaveBeenCalled()
  })

  it('question rows prefill the ask bar and never auto-send', async () => {
    stubIntelligence()
    fetchAllActionItems.mockResolvedValue([])
    mount()
    const question = await screen.findByText('What should I do today?')
    fireEvent.click(question)
    expect(onAskPrefill).toHaveBeenCalledWith('What should I do today?')
  })

  it('an intelligence error renders the retry card wired to load', async () => {
    stubIntelligence({ error: 'Saved feedback will retry automatically.' })
    mount()
    await waitFor(() => expect(screen.getByTestId('dashboard-intelligence-error')).toBeTruthy())
    fireEvent.click(screen.getByText('Retry'))
    expect(dashboardIntelligence.load).toHaveBeenCalled()
  })
})

describe('rolling variant (chat-mode)', () => {
  it('renders at most three rows, no error card, and never reports presence', async () => {
    stubIntelligence({ error: 'Saved feedback will retry automatically.' })
    render(
      <MemoryRouter>
        <HomeKnowsList onAskPrefill={onAskPrefill} variant="rolling" />
        <PresenceProbe />
      </MemoryRouter>
    )
    await waitFor(() => expect(screen.getByTestId('home-knows-rolling')).toBeTruthy())
    expect(screen.queryByTestId('dashboard-intelligence-error')).toBeNull()
    expect(screen.getByTestId('home-knows-rolling').children.length).toBeLessThanOrEqual(3)
    expect(screen.getByTestId('presence').textContent).toBe('false')
  })
})

describe('row context menu', () => {
  it('right-click offers Later and Dismiss on recommendation rows', async () => {
    stubIntelligence({ recommendations: [recommendation() as never] })
    const later = vi.spyOn(dashboardIntelligence, 'later').mockResolvedValue()
    mount()
    await waitFor(() => expect(screen.getByText('Finish the report')).toBeTruthy())
    fireEvent.contextMenu(screen.getByTestId('home-knows-insight-out-1:dk-1'))
    const menu = screen.getByTestId('knows-context-menu')
    expect(menu.textContent).toContain('Later')
    expect(menu.textContent).toContain('Dismiss')
    fireEvent.click(screen.getByText('Later'))
    expect(later).toHaveBeenCalledWith(expect.objectContaining({ id: 'out-1:dk-1' }))
  })
})
