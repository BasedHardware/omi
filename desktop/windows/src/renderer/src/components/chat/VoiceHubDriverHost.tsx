import { useEffect, useRef, useState } from 'react'
import { useAppState } from '../../state/appState'
import { useAuth } from '../../hooks/useAuth'
import { getPreferences, onPreferencesChange } from '../../lib/preferences'
import { useHubWarmLifecycle } from '../../hooks/useHubWarmLifecycle'
import { interruptCurrentResponse } from '../../lib/voice/voiceController'
import { startPttCapture } from '../../lib/ptt/capture'
import { batchTranscribe } from '../../lib/ptt/transport'
import { muteSystemAudioForHubCapture } from '../../lib/ptt/systemAudioMute'
import { HubController } from '../../lib/voice/hub/hubController'
import { VoiceHubTurnDriver } from '../../lib/voice/turn/voiceHubTurnDriver'

// The main-window mount for the warm-hub PTT driver (A5 PR-6b, Option A / D1).
//
// The coordinator + host + hub controller + output coordinator all run HERE
// because `pcmPlayer` and `voiceController` are main-resident — so hub spoken
// audio plays locally with zero audio IPC. This host wires the driver's injected
// seams to the real subsystems and subscribes to the three bar→main control
// channels (begin / end / cancel).
//
// The kill-switch is structural: the bar sends `voiceHubBegin` ONLY when
// `pttHubEnabled` is on, so with the flag off this host constructs its (pure,
// unconnected) objects and registers three listeners that NEVER fire — no
// capture, no hub warm, no projection. The shipped local PTT cascade is untouched.
export function VoiceHubDriverHost(): null {
  const { chat } = useAppState()
  const { user, loading } = useAuth()
  // Eager-warm gate (the pttHubEnabled opt-out contract). Reactive so a runtime
  // toggle warms/tears down with no restart.
  const [hubEnabled, setHubEnabled] = useState(() => getPreferences().pttHubEnabled === true)
  useEffect(() => onPreferencesChange((p) => setHubEnabled(p.pttHubEnabled === true)), [])

  // Latest-ref so the once-constructed driver always drives the freshest send.
  const sendRef = useRef(chat.send)
  // eslint-disable-next-line react-hooks/refs -- latest-ref for the once-built driver
  sendRef.current = chat.send

  // Built once. Every collaborator points at the real main-resident subsystem:
  //   * hub session (playback via its own pcmPlayer, D3) — HubController.
  //   * barge-in — voiceController.interruptCurrentResponse (the existing channel).
  //   * capture — startPttCapture issued FROM MAIN, so owned PCM routes here.
  //   * cascade STT (omniSTT route + warm-wait fallback) — transport.batchTranscribe.
  //   * final transcript — the ONE chat engine's send (fromVoice ⇒ spoken reply).
  //   * orb projection — publishVoiceHubState (main → bar).
  const [driver] = useState(
    // eslint-disable-next-line react-hooks/refs -- latest-ref (sendRef) is read at turn-commit time inside the once-built driver, never during render
    () =>
      new VoiceHubTurnDriver({
        createHub: (events) => new HubController({ events }),
        interruptPlayback: (leaseID) => interruptCurrentResponse(leaseID),
        publishState: (state) => window.omi?.publishVoiceHubState?.(state),
        startCapture: (opts) => startPttCapture(opts),
        transcribe: (pcm) => batchTranscribe(pcm, new AbortController().signal),
        onFinalText: (text) => void sendRef.current(text, { fromVoice: true }),
        muteForCapture: muteSystemAudioForHubCapture
      })
  )

  useEffect(() => {
    const un1 = window.omi?.onVoiceHubBegin?.((p) => driver.begin(p))
    const un2 = window.omi?.onVoiceHubEnd?.(() => driver.end())
    const un3 = window.omi?.onVoiceHubCancel?.(() => driver.cancel())
    return () => {
      un1?.()
      un2?.()
      un3?.()
    }
  }, [driver])

  // Eagerly warm the hub for a signed-in user with the flag on. This is what makes
  // hub.isAvailable() true — without it selectPttRoute always picks the cascade and
  // the warm hub never engages. Tears down on toggle-off / sign-out.
  useHubWarmLifecycle(driver, { ready: !loading, signedIn: !!user, hubEnabled })

  return null
}
