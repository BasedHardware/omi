import { useEffect, useRef } from 'react'
import { auth, onAuthStateChanged } from '../../lib/firebase'
import { getPreferences, isOnboardingComplete, onPreferencesChange } from '../../lib/preferences'
import {
  createMuteReminderController,
  type MuteReminderNotificationPayload
} from '../../lib/capture/muteReminder'
import { toast } from '../../lib/toast'

const CHIME_RESUME_TIMEOUT_MS = 500
const CHIME_CLOSE_FALLBACK_MS = 1500

async function resumeAudioContext(ctx: AudioContext, timeoutMs: number): Promise<boolean> {
  let timer: ReturnType<typeof setTimeout> | null = null
  try {
    const didResume = await Promise.race([
      Promise.resolve()
        .then(() => ctx.resume())
        .then(
          () => true,
          () => false
        ),
      new Promise<boolean>((resolve) => {
        timer = setTimeout(() => resolve(false), timeoutMs)
      })
    ])
    return didResume && ctx.state === 'running'
  } finally {
    if (timer !== null) {
      clearTimeout(timer)
    }
  }
}

// Plays a soft, non-intrusive two-note Web Audio sine cue when high-urgency
// mute reminders fire. Explicitly resumes the AudioContext (for Chromium's
// autoplay policy) and closes it on every exit path so contexts never leak.
async function playSoftMuteReminderChime(): Promise<void> {
  let ctx: AudioContext | null = null
  let fallbackCloseTimer: ReturnType<typeof setTimeout> | null = null
  let closed = false

  const closeContext = (): void => {
    if (closed) return
    closed = true
    if (fallbackCloseTimer !== null) {
      clearTimeout(fallbackCloseTimer)
      fallbackCloseTimer = null
    }
    const currentCtx = ctx
    if (currentCtx && currentCtx.state !== 'closed') {
      try {
        void Promise.resolve(currentCtx.close()).catch(() => {})
      } catch {
        /* best-effort audio cleanup */
      }
    }
  }

  try {
    const AudioCtx =
      typeof window !== 'undefined'
        ? window.AudioContext ||
          (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
        : undefined
    if (!AudioCtx) return

    ctx = new AudioCtx()
    const running = await resumeAudioContext(ctx, CHIME_RESUME_TIMEOUT_MS)
    if (!running) {
      closeContext()
      return
    }

    fallbackCloseTimer = setTimeout(closeContext, CHIME_CLOSE_FALLBACK_MS)
    const now = ctx.currentTime
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()
    osc.type = 'sine'
    osc.frequency.setValueAtTime(523.25, now) // C5
    osc.frequency.setValueAtTime(659.25, now + 0.12) // E5
    gain.gain.setValueAtTime(0.0001, now)
    gain.gain.exponentialRampToValueAtTime(0.06, now + 0.02)
    gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.28)
    osc.connect(gain)
    gain.connect(ctx.destination)
    osc.onended = () => {
      closeContext()
    }
    osc.start(now)
    osc.stop(now + 0.3)
  } catch {
    closeContext()
  }
}

function handleMuteReminder(payload: MuteReminderNotificationPayload): void {
  window.omi?.notifyMutedRecordingReminder?.({
    title: payload.title,
    body: payload.body,
    silent: payload.silentSystemNotification
  })
  toast(payload.title, {
    body: payload.body,
    tone: payload.urgency === 'high' ? 'warn' : 'info',
    duration: 8000
  })
  if (payload.playAttentionCue) {
    void playSoftMuteReminderChime()
  }
}

// App-root host (main window only) that monitors prolonged muted/paused audio
// recording (`continuousRecording === false`) and surfaces periodic reminders
// without capturing or inspecting any audio, screen, or transcript content.
export function MuteReminderHost(): null {
  const controllerRef = useRef<ReturnType<typeof createMuteReminderController> | null>(null)

  useEffect(() => {
    const controller = createMuteReminderController({
      onRemind: handleMuteReminder
    })
    controllerRef.current = controller

    const sync = (): void => {
      const prefs = getPreferences()
      controller.update({
        signedIn: !!auth.currentUser,
        onboarded: isOnboardingComplete(),
        continuousRecording: !!prefs.continuousRecording,
        urgency: prefs.muteReminderUrgency,
        intervalMinutes: prefs.muteReminderIntervalMinutes
      })
    }

    sync()
    const unsubPrefs = onPreferencesChange(() => sync())
    const unsubAuth = onAuthStateChanged(auth, () => sync())

    return () => {
      unsubPrefs()
      unsubAuth()
      controller.dispose()
      controllerRef.current = null
    }
  }, [])

  return null
}
