// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { InsightPayload, MeetingToastPayload } from '../../../../shared/types'
import { InsightToast } from './InsightToast'

let onMeetingToast: ((payload: MeetingToastPayload) => void) | null = null
let onInsightShow: ((payload: InsightPayload) => void) | null = null
const meetingAction = vi.fn()
const rewindFocusFrame = vi.fn()
const jitFeedback = vi.fn(() => Promise.resolve())
const insightDismiss = vi.fn()

beforeEach(() => {
  onMeetingToast = null
  onInsightShow = null
  meetingAction.mockReset()
  rewindFocusFrame.mockReset()
  jitFeedback.mockReset()
  jitFeedback.mockResolvedValue(undefined)
  insightDismiss.mockReset()
  vi.stubGlobal('window', {
    omi: {
      onInsightShow: (cb: (payload: InsightPayload) => void) => {
        onInsightShow = cb
        return () => {}
      },
      onMeetingToast: (cb: (payload: MeetingToastPayload) => void) => {
        onMeetingToast = cb
        return () => {}
      },
      onWhatsNewToast: () => () => {},
      meetingGetToast: async () => null,
      whatsNewGetPending: async () => null,
      meetingAction,
      insightHoverStart: vi.fn(),
      insightHoverEnd: vi.fn(),
      rewindFocusFrame,
      jitFeedback,
      insightDismiss
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

function showError(
  errorKind: NonNullable<MeetingToastPayload['errorKind']>,
  errorReason?: MeetingToastPayload['errorReason']
): void {
  act(() => {
    onMeetingToast?.({
      meetingId: 'meeting-1',
      appName: 'Google Meet',
      kind: 'error',
      errorKind,
      ...(errorReason ? { errorReason } : {})
    })
  })
}

function showInsight(): void {
  act(() => {
    onInsightShow?.({
      headline: 'A timely thought',
      advice: 'Do the next step.',
      reasoning: 'A trigger matched.',
      category: 'other',
      sourceApp: 'Omi',
      confidence: 1,
      jit: {
        lane: 'planned',
        eventId: 'e'.repeat(64),
        subjectId: 'trigger-1',
        candidateId: 'c'.repeat(64),
        triggerRevision: 1,
        accountGeneration: 1,
        rewindFrameId: 42
      }
    })
  })
}

function showAmbientInsight(): void {
  act(() => {
    onInsightShow?.({
      headline: 'A context thought',
      advice: 'Consider whether this is useful.',
      reasoning: 'Ambient context.',
      category: 'other',
      sourceApp: 'Omi',
      confidence: 1
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

  it('names a spent daily limit instead of blaming sign-in/mic, and offers no Retry', () => {
    // Live bug: a daily-budget stop showed "Check your sign-in, internet connection,
    // and Windows microphone access, then retry." — none of which could fix it.
    render(<InsightToast />)
    showError('runtime', 'daily_limit')

    expect(screen.getByText('Capture stopped — Google Meet')).toBeTruthy()
    expect(screen.getByText(/daily voice transcription limit is used up/)).toBeTruthy()
    expect(screen.queryByText(/microphone access/)).toBeNull()
    expect(screen.queryByRole('button', { name: 'Retry' })).toBeNull()
    expect(screen.getByText('Dismiss', { selector: '.meeting-btn' })).toBeTruthy()
  })

  it('names a used-up free quota as the reason capture stopped', () => {
    render(<InsightToast />)
    showError('runtime', 'quota')

    expect(screen.getByText(/free Omi transcription is used up/)).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Retry' })).toBeNull()
  })

  it('keeps the generic advice and Retry for an ordinary runtime drop', () => {
    render(<InsightToast />)
    showError('runtime')

    expect(screen.getByText(/Check your sign-in/)).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Retry' })).toBeTruthy()
  })
})

describe('JIT evidence navigation', () => {
  it('uses main-process frame focus instead of a toast href', () => {
    render(<InsightToast />)
    showInsight()
    fireEvent.click(screen.getByRole('button', { name: 'Open keyframe in Rewind' }))
    expect(rewindFocusFrame).toHaveBeenCalledWith(42)
  })

  it('keeps the actionable toast open when feedback enqueue fails', async () => {
    jitFeedback.mockRejectedValueOnce(new Error('database unavailable'))
    render(<InsightToast />)
    showInsight()
    fireEvent.click(screen.getByRole('button', { name: 'Useful' }))
    await act(async () => Promise.resolve())
    expect(insightDismiss).not.toHaveBeenCalled()
    expect(screen.getByRole('alert').textContent).toMatch(/retry/i)
  })

  it('does not expose trigger feedback controls for an ambient result without a revision fence', () => {
    render(<InsightToast />)
    showAmbientInsight()
    expect(screen.queryByRole('button', { name: 'Useful' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Not relevant' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Snooze' })).toBeNull()
  })
})
