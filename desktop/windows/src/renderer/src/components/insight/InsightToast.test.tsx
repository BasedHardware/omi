// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { MeetingToastPayload } from '../../../../shared/types'
import { InsightToast } from './InsightToast'

let onMeetingToast: ((payload: MeetingToastPayload) => void) | null = null
const meetingAction = vi.fn()

beforeEach(() => {
  onMeetingToast = null
  meetingAction.mockReset()
  vi.stubGlobal('window', {
    omi: {
      onInsightShow: () => () => {},
      onMeetingToast: (cb: (payload: MeetingToastPayload) => void) => {
        onMeetingToast = cb
        return () => {}
      },
      onWhatsNewToast: () => () => {},
      meetingGetToast: async () => null,
      whatsNewGetPending: async () => null,
      meetingAction,
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
