// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { BeeperDraft, MeetingToastPayload } from '../../../../shared/types'
import { InsightToast } from './InsightToast'

let onMeetingToast: ((payload: MeetingToastPayload) => void) | null = null
let onBeeperDraftToast: ((payload: BeeperDraft) => void) | null = null
const meetingAction = vi.fn()
const beeperSendDraft = vi.fn()
const beeperDismissDraft = vi.fn()
const insightDismiss = vi.fn()

beforeEach(() => {
  onMeetingToast = null
  onBeeperDraftToast = null
  meetingAction.mockReset()
  beeperSendDraft.mockReset()
  beeperDismissDraft.mockReset()
  insightDismiss.mockReset()
  beeperSendDraft.mockResolvedValue({})
  beeperDismissDraft.mockResolvedValue({})
  vi.stubGlobal('window', {
    omi: {
      onInsightShow: () => () => {},
      onMeetingToast: (cb: (payload: MeetingToastPayload) => void) => {
        onMeetingToast = cb
        return () => {}
      },
      onWhatsNewToast: () => () => {},
      onBeeperDraftToast: (cb: (payload: BeeperDraft) => void) => {
        onBeeperDraftToast = cb
        return () => {}
      },
      meetingGetToast: async () => null,
      whatsNewGetPending: async () => null,
      beeperGetDraftToast: async () => null,
      meetingAction,
      beeperSendDraft,
      beeperDismissDraft,
      insightDismiss,
      insightHoverStart: vi.fn(),
      insightHoverEnd: vi.fn()
    }
  })
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

function show(kind: MeetingToastPayload['kind']): void {
  act(() => {
    onMeetingToast?.({ meetingId: 'meeting-1', appName: 'Google Meet', kind })
  })
}

function showError(errorKind: NonNullable<MeetingToastPayload['errorKind']>): void {
  act(() => {
    onMeetingToast?.({
      meetingId: 'meeting-1',
      appName: 'Google Meet',
      kind: 'error',
      errorKind
    })
  })
}

describe('meeting capture status toast', () => {
  it('shows startup progress without claiming capture is live', () => {
    render(<InsightToast />)
    show('starting')

    expect(screen.getByText('Starting capture — Google Meet')).toBeTruthy()
    expect(screen.queryByText(/Omi is capturing/)).toBeNull()
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeTruthy()
  })

  it('shows a retry action after startup fails', () => {
    render(<InsightToast />)
    show('error')

    expect(screen.getByText("Capture didn't start — Google Meet")).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(meetingAction).toHaveBeenCalledWith('meeting-1', 'start')
  })

  it('does not offer Retry for a save failure', () => {
    render(<InsightToast />)
    showError('save')

    expect(screen.getByText("Capture couldn't be saved — Google Meet")).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Retry' })).toBeNull()
    fireEvent.click(screen.getByText('Dismiss', { selector: '.meeting-btn' }))
    expect(meetingAction).toHaveBeenCalledWith('meeting-1', 'dismiss')
  })
})

describe('Beeper draft toast', () => {
  const draft: BeeperDraft = {
    id: 'draft-1',
    chatId: '!li_1',
    chatTitle: 'Alex',
    network: 'LinkedIn',
    inboundText: 'hey what time does your flight land tomorrow?',
    replyText: "6:40pm — I'll text when I'm through baggage.",
    inboundMessageId: 'm1',
    createdAt: 1
  }

  it('shows the inbound bubble, suggested reply, and Send/Skip', () => {
    render(<InsightToast />)
    act(() => {
      onBeeperDraftToast?.(draft)
    })

    expect(screen.getByText('Suggested reply')).toBeTruthy()
    expect(screen.getByText('LinkedIn · Alex')).toBeTruthy()
    expect(screen.getByText(draft.inboundText)).toBeTruthy()
    expect(screen.getByText(draft.replyText)).toBeTruthy()
    expect(screen.getByText('Drafted by Omi from your memories. You send it.')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Send' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Skip' })).toBeTruthy()
  })

  it('sends the draft then dismisses the card', async () => {
    render(<InsightToast />)
    act(() => {
      onBeeperDraftToast?.(draft)
    })
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Send' }))
    })
    expect(beeperSendDraft).toHaveBeenCalledWith('draft-1')
    expect(insightDismiss).toHaveBeenCalled()
  })
})
