import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import {
  createMuteReminderController,
  formatMutedDurationLabel,
  normalizeMuteReminderIntervalMinutes,
  normalizeMuteReminderUrgency,
  type MuteReminderNotificationPayload
} from './muteReminder'

describe('muteReminder (#20215)', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-10-17T12:00:00Z'))
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('normalizes urgency and interval bounds safely', () => {
    expect(normalizeMuteReminderUrgency(undefined)).toBe('standard')
    expect(normalizeMuteReminderUrgency('invalid')).toBe('standard')
    expect(normalizeMuteReminderUrgency('subtle')).toBe('subtle')
    expect(normalizeMuteReminderUrgency('high')).toBe('high')
    expect(normalizeMuteReminderUrgency('off')).toBe('off')

    expect(normalizeMuteReminderIntervalMinutes(undefined)).toBe(30)
    expect(normalizeMuteReminderIntervalMinutes(NaN)).toBe(30)
    expect(normalizeMuteReminderIntervalMinutes(1)).toBe(5)
    expect(normalizeMuteReminderIntervalMinutes(999)).toBe(240)
    expect(normalizeMuteReminderIntervalMinutes(15)).toBe(15)
  })

  it('never reminds users who start or restore auth with recording disabled', () => {
    const onRemind = vi.fn()
    const controller = createMuteReminderController({ onRemind })
    const state = { signedIn: true, onboarded: true, continuousRecording: false }
    controller.update(state)
    vi.advanceTimersByTime(120 * 60_000)
    expect(controller.isArmed()).toBe(false)
    controller.update({ ...state, signedIn: false })
    controller.update({ ...state, urgency: 'high', intervalMinutes: 15 })
    vi.advanceTimersByTime(120 * 60_000)
    expect(onRemind).not.toHaveBeenCalled()
    controller.dispose()
  })

  it('does not carry active recording history across sign-out or onboarding', () => {
    const onRemind = vi.fn()
    const controller = createMuteReminderController({ onRemind })
    const state = { signedIn: true, onboarded: true, continuousRecording: true }
    for (const boundary of [{ signedIn: false }, { onboarded: false }]) {
      controller.update(state)
      controller.update({ ...state, ...boundary })
      controller.update({ ...state, continuousRecording: false })
      expect(controller.isArmed()).toBe(false)
      vi.advanceTimersByTime(60 * 60_000)
    }
    expect(onRemind).not.toHaveBeenCalled()
    controller.dispose()
  })

  it('formats elapsed muted duration labels clearly', () => {
    expect(formatMutedDurationLabel(15)).toBe('15 min')
    expect(formatMutedDurationLabel(60)).toBe('1 hour')
    expect(formatMutedDurationLabel(90)).toBe('1h 30m')
    expect(formatMutedDurationLabel(120)).toBe('2 hours')
  })

  it('arms only after active recording is paused, firing periodic reminders until unmuted', () => {
    const reminders: MuteReminderNotificationPayload[] = []
    const controller = createMuteReminderController({
      onRemind: (payload) => reminders.push(payload)
    })

    controller.update({ signedIn: true, onboarded: true, continuousRecording: true })

    controller.update({
      signedIn: true,
      onboarded: true,
      continuousRecording: false,
      urgency: 'standard',
      intervalMinutes: 30
    })

    expect(controller.isArmed()).toBe(true)
    expect(reminders).toHaveLength(0)

    // Advance 29 minutes — not fired yet
    vi.advanceTimersByTime(29 * 60_000)
    expect(reminders).toHaveLength(0)

    // Advance 1 more minute (total 30m) — first reminder fires
    vi.advanceTimersByTime(1 * 60_000)
    expect(reminders).toHaveLength(1)
    expect(reminders[0]).toMatchObject({
      title: 'Omi recording is still muted',
      urgency: 'standard',
      mutedMinutes: 30,
      reminderCount: 1,
      silentSystemNotification: false,
      playAttentionCue: false
    })

    // Advance another 30 minutes (total 60m) — second persistent reminder fires
    vi.advanceTimersByTime(30 * 60_000)
    expect(reminders).toHaveLength(2)
    expect(reminders[1]).toMatchObject({
      mutedMinutes: 60,
      reminderCount: 2
    })
    expect(reminders[1].body).toContain('1 hour')

    // Resume recording — disarms immediately and resets counter
    controller.update({
      signedIn: true,
      onboarded: true,
      continuousRecording: true,
      urgency: 'standard',
      intervalMinutes: 30
    })
    expect(controller.isArmed()).toBe(false)
    expect(controller.getReminderCount()).toBe(0)

    vi.advanceTimersByTime(60 * 60_000)
    expect(reminders).toHaveLength(2)
  })

  it('does not arm when signed out, not onboarded, actively recording, or urgency is off', () => {
    const onRemind = vi.fn()
    const controller = createMuteReminderController({ onRemind })

    controller.update({
      signedIn: false,
      onboarded: true,
      continuousRecording: false,
      urgency: 'standard',
      intervalMinutes: 15
    })
    expect(controller.isArmed()).toBe(false)

    controller.update({
      signedIn: true,
      onboarded: false,
      continuousRecording: false,
      urgency: 'standard',
      intervalMinutes: 15
    })
    expect(controller.isArmed()).toBe(false)

    controller.update({
      signedIn: true,
      onboarded: true,
      continuousRecording: false,
      urgency: 'off',
      intervalMinutes: 15
    })
    expect(controller.isArmed()).toBe(false)

    vi.advanceTimersByTime(120 * 60_000)
    expect(onRemind).not.toHaveBeenCalled()
  })

  it('distinguishes subtle vs standard (intermediate) vs high urgency reminder modes and respects interval changes', () => {
    const reminders: MuteReminderNotificationPayload[] = []
    const controller = createMuteReminderController({
      onRemind: (payload) => reminders.push(payload)
    })

    controller.update({ signedIn: true, onboarded: true, continuousRecording: true })

    controller.update({
      signedIn: true,
      onboarded: true,
      continuousRecording: false,
      urgency: 'subtle',
      intervalMinutes: 15
    })

    vi.advanceTimersByTime(15 * 60_000)
    expect(reminders).toHaveLength(1)
    expect(reminders[0].silentSystemNotification).toBe(true)
    expect(reminders[0].playAttentionCue).toBe(false)

    // Switch to high urgency and 60-minute interval while still muted
    controller.update({
      signedIn: true,
      onboarded: true,
      continuousRecording: false,
      urgency: 'high',
      intervalMinutes: 60
    })

    vi.advanceTimersByTime(60 * 60_000)
    expect(reminders).toHaveLength(2)
    expect(reminders[1].urgency).toBe('high')
    expect(reminders[1].silentSystemNotification).toBe(false)
    expect(reminders[1].playAttentionCue).toBe(true)
    expect(reminders[1].title).toContain('1h 15m')
  })

  it('changing the interval mid-mute restarts the countdown without resetting muted duration', () => {
    const onRemind = vi.fn()
    const controller = createMuteReminderController({ onRemind })
    const state = {
      signedIn: true,
      onboarded: true,
      continuousRecording: false,
      urgency: 'standard' as const,
      intervalMinutes: 30
    }

    controller.update({ signedIn: true, onboarded: true, continuousRecording: true })

    controller.update(state)
    vi.advanceTimersByTime(20 * 60_000)
    controller.update({ ...state, intervalMinutes: 15 })

    // The old 30-minute deadline must not survive the interval change.
    vi.advanceTimersByTime(10 * 60_000)
    expect(onRemind).not.toHaveBeenCalled()
    vi.advanceTimersByTime(5 * 60_000 - 1)
    expect(onRemind).not.toHaveBeenCalled()
    vi.advanceTimersByTime(1)
    expect(onRemind).toHaveBeenCalledTimes(1)
    expect(onRemind).toHaveBeenLastCalledWith(
      expect.objectContaining({ mutedMinutes: 35, reminderCount: 1 })
    )

    vi.advanceTimersByTime(15 * 60_000)
    expect(onRemind).toHaveBeenCalledTimes(2)
    expect(onRemind).toHaveBeenLastCalledWith(
      expect.objectContaining({ mutedMinutes: 50, reminderCount: 2 })
    )
    controller.dispose()
  })

  it('updating only urgency mid-mute preserves the running interval countdown', () => {
    const reminders: MuteReminderNotificationPayload[] = []
    const controller = createMuteReminderController({
      onRemind: (payload) => reminders.push(payload)
    })

    controller.update({ signedIn: true, onboarded: true, continuousRecording: true })

    controller.update({
      signedIn: true,
      onboarded: true,
      continuousRecording: false,
      urgency: 'standard',
      intervalMinutes: 30
    })

    // Advance 20 minutes (10 minutes remaining)
    vi.advanceTimersByTime(20 * 60_000)
    expect(reminders).toHaveLength(0)

    // Urgency changes to 'high', but interval stays 30 min
    controller.update({
      signedIn: true,
      onboarded: true,
      continuousRecording: false,
      urgency: 'high',
      intervalMinutes: 30
    })

    // Advance remaining 10 minutes -> should fire reminder with high urgency at 30 min mark
    vi.advanceTimersByTime(10 * 60_000)
    expect(reminders).toHaveLength(1)
    expect(reminders[0].urgency).toBe('high')
    expect(reminders[0].mutedMinutes).toBe(30)
  })
})
