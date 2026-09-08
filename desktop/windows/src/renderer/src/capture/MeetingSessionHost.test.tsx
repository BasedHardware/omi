// @vitest-environment jsdom
import { act, cleanup, render } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { CaptureCommand, CaptureEvent } from '../../../shared/types'
import type { MeetingSessionHandle } from './meetingSession'

type PendingStart = {
  resolve: (handle: MeetingSessionHandle) => void
  reject: (error: Error) => void
  signal: AbortSignal
  onError: (message: string) => void
}

const h = vi.hoisted(() => ({
  commandHandler: null as null | ((command: CaptureCommand) => void),
  pending: [] as PendingStart[],
  captureEmit: vi.fn(),
  stopAttempt1: vi.fn(async () => {}),
  stopAttempt2: vi.fn(async () => {})
}))

vi.mock('./meetingSession', () => ({
  startMeetingSession: vi.fn(
    (args: { signal: AbortSignal; onError: (message: string) => void }) =>
      new Promise<MeetingSessionHandle>((resolve, reject) => {
        h.pending.push({ resolve, reject, signal: args.signal, onError: args.onError })
      })
  )
}))

import { MeetingSessionHost } from './MeetingSessionHost'

beforeEach(() => {
  h.commandHandler = null
  h.pending.length = 0
  h.captureEmit.mockReset()
  h.stopAttempt1.mockClear()
  h.stopAttempt2.mockClear()
  Object.defineProperty(window, 'omi', {
    configurable: true,
    value: {
      captureEmit: h.captureEmit,
      onCaptureCommand: (handler: (command: CaptureCommand) => void) => {
        h.commandHandler = handler
        return () => {
          h.commandHandler = null
        }
      }
    }
  })
})

afterEach(() => {
  cleanup()
})

describe('MeetingSessionHost attempts', () => {
  it('allows Retry while an older cancelled startup is still settling', async () => {
    render(<MeetingSessionHost />)
    act(() => {
      h.commandHandler?.({
        type: 'meeting-capture-start',
        meetingId: 'meeting-1',
        attemptId: 1,
        appName: 'Google Meet'
      })
    })
    expect(h.pending).toHaveLength(1)

    act(() => {
      h.commandHandler?.({ type: 'meeting-capture-stop', meetingId: 'meeting-1', attemptId: 1 })
      h.commandHandler?.({
        type: 'meeting-capture-start',
        meetingId: 'meeting-1',
        attemptId: 2,
        appName: 'Google Meet'
      })
    })
    expect(h.pending).toHaveLength(2)
    expect(h.pending[0].signal.aborted).toBe(true)

    await act(async () => {
      h.pending[1].resolve({ stop: h.stopAttempt2 })
      await Promise.resolve()
    })
    expect(h.captureEmit).toHaveBeenCalledWith({
      type: 'meeting-capture-status',
      meetingId: 'meeting-1',
      attemptId: 2,
      status: 'started'
    })

    await act(async () => {
      h.pending[0].resolve({ stop: h.stopAttempt1 })
      await Promise.resolve()
    })
    expect(h.stopAttempt1).toHaveBeenCalledOnce()
    const events = h.captureEmit.mock.calls.map(([event]) => event as CaptureEvent)
    expect(
      events.some(
        (event) =>
          event.type === 'meeting-capture-status' &&
          event.attemptId === 1 &&
          event.status === 'started'
      )
    ).toBe(false)

    act(() => {
      h.commandHandler?.({ type: 'meeting-capture-stop', meetingId: 'meeting-1', attemptId: 2 })
    })
  })

  it('fails closed when a ready lane drops while its sibling is still starting', async () => {
    render(<MeetingSessionHost />)
    act(() => {
      h.commandHandler?.({
        type: 'meeting-capture-start',
        meetingId: 'meeting-early-drop',
        attemptId: 3,
        appName: 'Google Meet'
      })
    })

    act(() => {
      h.pending[0].onError('system: socket closed')
    })
    await act(async () => {
      h.pending[0].resolve({ stop: h.stopAttempt1 })
      await Promise.resolve()
    })

    expect(h.stopAttempt1).toHaveBeenCalledOnce()
    expect(h.captureEmit).toHaveBeenCalledWith({
      type: 'meeting-capture-status',
      meetingId: 'meeting-early-drop',
      attemptId: 3,
      status: 'startup-error',
      message: 'system: socket closed'
    })
    const events = h.captureEmit.mock.calls.map(([event]) => event as CaptureEvent)
    expect(
      events.some(
        (event) =>
          event.type === 'meeting-capture-status' &&
          event.attemptId === 3 &&
          event.status === 'started'
      )
    ).toBe(false)
  })
})
