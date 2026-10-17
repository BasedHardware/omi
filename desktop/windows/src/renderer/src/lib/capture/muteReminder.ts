// Prolonged-mute reminder state machine (#20215).
//
// PRIVACY INVARIANT:
// While recording is muted/paused (`continuousRecording === false`), this
// module ONLY tracks elapsed wall-clock time and emits static reminder copy.
// It NEVER accesses, samples, buffers, or inspects microphone audio, screen
// frames, or transcript content.

export type MuteReminderUrgency = 'off' | 'subtle' | 'standard' | 'high'

export const MUTE_REMINDER_URGENCY_DEFAULT: MuteReminderUrgency = 'standard'
export const MUTE_REMINDER_INTERVAL_MINUTES_DEFAULT = 30
export const MUTE_REMINDER_INTERVAL_MINUTES_MIN = 5
export const MUTE_REMINDER_INTERVAL_MINUTES_MAX = 240

export const MUTE_REMINDER_INTERVAL_OPTIONS = [15, 30, 60, 120] as const

const VALID_URGENCIES = new Set<MuteReminderUrgency>(['off', 'subtle', 'standard', 'high'])

export function normalizeMuteReminderUrgency(value: unknown): MuteReminderUrgency {
  if (typeof value === 'string' && VALID_URGENCIES.has(value as MuteReminderUrgency)) {
    return value as MuteReminderUrgency
  }
  return MUTE_REMINDER_URGENCY_DEFAULT
}

export function normalizeMuteReminderIntervalMinutes(value: unknown): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    return MUTE_REMINDER_INTERVAL_MINUTES_DEFAULT
  }
  const rounded = Math.round(value)
  return Math.min(
    MUTE_REMINDER_INTERVAL_MINUTES_MAX,
    Math.max(MUTE_REMINDER_INTERVAL_MINUTES_MIN, rounded)
  )
}

export interface MuteReminderStateInput {
  signedIn: boolean
  onboarded: boolean
  continuousRecording: boolean
  urgency?: MuteReminderUrgency
  intervalMinutes?: number
}

export interface MuteReminderNotificationPayload {
  title: string
  body: string
  urgency: Exclude<MuteReminderUrgency, 'off'>
  mutedMinutes: number
  reminderCount: number
  /** True when the OS notification should suppress its native chime (subtle mode). */
  silentSystemNotification: boolean
  /** True when the renderer should play a soft attention chime (high urgency mode). */
  playAttentionCue: boolean
}

export function formatMutedDurationLabel(minutes: number): string {
  const safeMinutes = Math.max(1, Math.round(minutes))
  if (safeMinutes < 60) {
    return `${safeMinutes} min`
  }
  const hours = Math.floor(safeMinutes / 60)
  const rem = safeMinutes % 60
  if (rem === 0) {
    return hours === 1 ? '1 hour' : `${hours} hours`
  }
  return `${hours}h ${rem}m`
}

export function buildMuteReminderPayload(
  mutedMinutes: number,
  urgency: Exclude<MuteReminderUrgency, 'off'>,
  reminderCount: number
): MuteReminderNotificationPayload {
  const durationLabel = formatMutedDurationLabel(mutedMinutes)
  const title =
    urgency === 'high'
      ? `Omi recording is still muted (${durationLabel})`
      : 'Omi recording is still muted'
  const body =
    urgency === 'subtle'
      ? `Audio recording has been paused for ${durationLabel}. Turn Microphone back on when you are ready to capture.`
      : `Audio recording has been paused for ${durationLabel}. Click to open Omi and resume recording so you don't miss your next conversation.`

  return {
    title,
    body,
    urgency,
    mutedMinutes: Math.max(1, Math.round(mutedMinutes)),
    reminderCount,
    silentSystemNotification: urgency === 'subtle',
    playAttentionCue: urgency === 'high'
  }
}

export interface MuteReminderControllerOptions {
  onRemind: (payload: MuteReminderNotificationPayload) => void
  now?: () => number
  setTimer?: (cb: () => void, ms: number) => ReturnType<typeof setTimeout>
  clearTimer?: (handle: ReturnType<typeof setTimeout>) => void
}

export interface MuteReminderController {
  update: (input: MuteReminderStateInput) => void
  dispose: () => void
  isArmed: () => boolean
  getReminderCount: () => number
}

/**
 * Pure timer controller that arms a repeating reminder while the user is signed in,
 * onboarded, and has `continuousRecording` paused/muted (`false`). Disarms
 * immediately when recording resumes, when the user signs out, or when urgency is 'off'.
 */
export function createMuteReminderController(
  options: MuteReminderControllerOptions
): MuteReminderController {
  const now = options.now ?? (() => Date.now())
  const setTimer = options.setTimer ?? ((cb, ms) => setTimeout(cb, ms))
  const clearTimer = options.clearTimer ?? ((handle) => clearTimeout(handle))

  let timerHandle: ReturnType<typeof setTimeout> | null = null
  let mutedSinceMs: number | null = null
  let reminderCount = 0
  let currentUrgency: MuteReminderUrgency = MUTE_REMINDER_URGENCY_DEFAULT
  let currentIntervalMs = MUTE_REMINDER_INTERVAL_MINUTES_DEFAULT * 60_000
  let armed = false

  function cancelTimer(): void {
    if (timerHandle !== null) {
      clearTimer(timerHandle)
      timerHandle = null
    }
    armed = false
  }

  function disarmAndReset(): void {
    cancelTimer()
    mutedSinceMs = null
    reminderCount = 0
  }

  function scheduleNextTick(): void {
    cancelTimer()
    if (currentUrgency === 'off' || mutedSinceMs === null) return
    armed = true
    timerHandle = setTimer(() => {
      timerHandle = null
      if (!armed || currentUrgency === 'off' || mutedSinceMs === null) return
      reminderCount += 1
      const elapsedMs = Math.max(currentIntervalMs, now() - mutedSinceMs)
      const mutedMinutes = Math.max(1, Math.round(elapsedMs / 60_000))
      const payload = buildMuteReminderPayload(mutedMinutes, currentUrgency, reminderCount)
      options.onRemind(payload)
      // Rearm for persistent periodic reminders while still muted.
      if (armed && currentUrgency !== 'off' && mutedSinceMs !== null) {
        scheduleNextTick()
      }
    }, currentIntervalMs)
  }

  function update(input: MuteReminderStateInput): void {
    const urgency = normalizeMuteReminderUrgency(input.urgency)
    const intervalMinutes = normalizeMuteReminderIntervalMinutes(input.intervalMinutes)
    const nextIntervalMs = intervalMinutes * 60_000
    const shouldMonitorMuted =
      input.signedIn === true &&
      input.onboarded === true &&
      input.continuousRecording === false &&
      urgency !== 'off'

    if (!shouldMonitorMuted) {
      disarmAndReset()
      currentUrgency = urgency
      currentIntervalMs = nextIntervalMs
      return
    }

    const wasMonitoring = mutedSinceMs !== null
    const intervalChanged = nextIntervalMs !== currentIntervalMs
    const urgencyChanged = urgency !== currentUrgency

    currentUrgency = urgency
    currentIntervalMs = nextIntervalMs

    if (!wasMonitoring) {
      mutedSinceMs = now()
      reminderCount = 0
      scheduleNextTick()
      return
    }

    if (intervalChanged || urgencyChanged || !armed) {
      scheduleNextTick()
    }
  }

  return {
    update,
    dispose: disarmAndReset,
    isArmed: () => armed,
    getReminderCount: () => reminderCount
  }
}
