// Bar-side mount of the voice-plane supervisor (2026-07-18) — see
// lib/voice/supervisor/voicePlaneSupervisor.ts for the contract. This hook does
// the wiring only:
//
//   * press/release come from the SAME gesture stream the PTT hook consumes
//     (`window.omiBar.onPtt`) — the outermost observable seam. A release arms
//     the watch only when a turn is actually live at that instant (hub turn
//     active, or the local machine recording): a tap or an already-aborted hold
//     owes no terminal, so the supervisor stays inert for them.
//   * observable terminals are edge-detected from the states the bar already
//     renders: the hub orb's reply-playback / hint transitions, the local PTT
//     hint/error strips, and the shared chat pipeline leaving 'idle' (a cascade
//     turn's text commit shows up there).
//   * on fire: failure chip + flight-record + the shared fallback telemetry
//     shape + `resetVoicePlane` — the full-stack rebuild.
//   * an external `voice:planeReset` (the "Reset voice" menu, or another
//     window's supervisor) cancels the local machine and shows a reset chip, so
//     every window converges on a clean plane.

import { useEffect, useRef, useState } from 'react'
import { trackEvent } from '../lib/analytics'
import { recordVoiceFlight } from '../lib/voice/flightRecord'
import {
  VoicePlaneSupervisor,
  type VoiceSupervisorLane
} from '../lib/voice/supervisor/voicePlaneSupervisor'

/** The failure chip (shown while the reset runs). Mirrors the tone of the PTT
 *  hint strip; auto-clears. */
export const SUPERVISOR_FIRE_CHIP = "Voice isn't responding — resetting…"
/** Chip for an externally-commanded reset (context menu). */
export const PLANE_RESET_CHIP = 'Voice was reset'
const CHIP_MS = 5000

export type VoicePlaneSupervisorSignals = {
  /** A main-owned hub turn is live (VoiceHubBarState.active). */
  hubActive: boolean
  /** The hub reply is audibly playing — a contract terminal. */
  hubResponseActive: boolean
  /** The hub projection's visible hint ('' when none) — non-empty is a terminal. */
  hubHint: string
  /** The local PTT machine is recording a hold. */
  pttRecording: boolean
  /** Local lane visible hint/error — non-empty is a terminal. */
  pttHint: string | null
  pttError: string | null
  /** The shared chat pipeline ('idle' | 'sending' | 'speaking'); leaving 'idle'
   *  means text committed — a terminal. */
  chatStatus: string
  /** Cancel the local PTT machine (an external plane reset must stop a live
   *  local hold; the hub side is reset by the main window). */
  cancelLocal?: () => void
}

export function useVoicePlaneSupervisor(signals: VoicePlaneSupervisorSignals): {
  /** Transient failure/reset chip for the bar hint strip (null = none). */
  chip: string | null
  /** Report a user abort (Esc path) so a dead turn's release never arms. */
  noteCancel: () => void
} {
  const [chip, setChip] = useState<string | null>(null)
  const chipTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const showChip = (text: string): void => {
    setChip(text)
    if (chipTimer.current !== null) clearTimeout(chipTimer.current)
    chipTimer.current = setTimeout(() => setChip(null), CHIP_MS)
  }
  const showChipRef = useRef(showChip)
  // eslint-disable-next-line react-hooks/refs -- latest-ref for the once-built supervisor
  showChipRef.current = showChip

  // Latest signals for event-time reads (the gesture listener must see the
  // freshest state without re-subscribing per render).
  const signalsRef = useRef(signals)
  // eslint-disable-next-line react-hooks/refs -- latest-ref for the once-registered listeners
  signalsRef.current = signals

  const [supervisor] = useState(
    // eslint-disable-next-line react-hooks/refs -- onFire reads latest-refs at fire time (a timer callback), never during render
    () =>
      new VoicePlaneSupervisor({
        record: recordVoiceFlight,
        onFire: ({ lane }) => {
          showChipRef.current(SUPERVISOR_FIRE_CHIP)
          // Shared fallback shape (AGENTS.md): the plane fail-opened into a full
          // reset — no new counter, closed-enum fields, outcome 'degraded' (the
          // turn was lost; the plane continues after the rebuild).
          trackEvent('fallback_triggered', {
            component: lane === 'hub' ? 'realtime_hub' : 'ptt_cascade',
            from: lane === 'hub' ? 'hub' : 'cascade',
            to: 'reset',
            reason: 'other',
            outcome: 'degraded'
          })
          window.omi?.resetVoicePlane?.('supervisor_timeout')
        }
      })
  )

  // Press/release from the gesture stream (an independent subscription — the
  // preload returns per-listener unsubscribes, so this never disturbs the PTT
  // hook's own listener).
  useEffect(() => {
    const un = window.omiBar?.onPtt?.((phase) => {
      if (phase === 'down') {
        supervisor.notePress()
        return
      }
      const s = signalsRef.current
      const lane: VoiceSupervisorLane = s.hubActive ? 'hub' : 'local'
      // Arm only when a turn is actually live at release — a tap (no hold
      // threshold reached) or an aborted hold owes no terminal.
      if (s.hubActive || s.pttRecording) supervisor.noteRelease(lane)
    })
    return () => {
      un?.()
      supervisor.dispose()
    }
  }, [supervisor])

  // Terminal edges — each disarms a pending watch. Rising-edge semantics come
  // free from the deps: the effect only runs when the value changes.
  const { hubResponseActive, hubHint, pttHint, pttError, chatStatus } = signals
  useEffect(() => {
    if (hubResponseActive) supervisor.noteTerminal('hub_playback')
  }, [supervisor, hubResponseActive])
  useEffect(() => {
    if (hubHint !== '') supervisor.noteTerminal('hub_hint')
  }, [supervisor, hubHint])
  useEffect(() => {
    if (pttHint) supervisor.noteTerminal('ptt_hint')
  }, [supervisor, pttHint])
  useEffect(() => {
    if (pttError) supervisor.noteTerminal('ptt_error')
  }, [supervisor, pttError])
  useEffect(() => {
    if (chatStatus !== 'idle') supervisor.noteTerminal('chat_status')
  }, [supervisor, chatStatus])

  // An external plane reset (menu / another window): stop a live local hold,
  // clear any pending watch, and tell the user what happened. The supervisor's
  // own fire shows its chip first; don't overwrite it.
  useEffect(
    () =>
      window.omi?.onVoicePlaneReset?.(() => {
        supervisor.noteCancel()
        signalsRef.current.cancelLocal?.()
        setChip((current) => current ?? PLANE_RESET_CHIP)
        if (chipTimer.current !== null) clearTimeout(chipTimer.current)
        chipTimer.current = setTimeout(() => setChip(null), CHIP_MS)
      }),
    [supervisor]
  )

  useEffect(
    () => () => {
      if (chipTimer.current !== null) clearTimeout(chipTimer.current)
    },
    []
  )

  return { chip, noteCancel: () => supervisor.noteCancel() }
}
