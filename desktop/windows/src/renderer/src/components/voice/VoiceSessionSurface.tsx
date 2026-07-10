import { useEffect, useState } from 'react'
import { Mic, MicOff, X, RefreshCw } from 'lucide-react'
import { cn } from '../../lib/utils'
import {
  getVoiceState,
  subscribeVoiceState,
  startVoiceSession,
  stopVoiceSession,
  setVoiceMuted,
  setVoiceOutputDevice
} from '../../lib/voice/voiceController'
import { attachVoiceE2eHook } from '../../lib/voice/e2eHook'
import type { VoiceSessionState } from '../../lib/voice/sessionMachine'

// The realtime voice-session surface (Phase 6). A self-contained component with
// no positional assumptions, so BOTH the Home chat area (today) and the Phase 4
// bar (later) can mount it — the bar just wraps it in its own chrome. All
// session state lives in the voiceController singleton; this is pure UI.
//
// Design: neutral/white accents only (never purple), quiet chrome matching the
// chat bar (rounded-2xl, border-white/10, --surface).

function useVoiceSession(): VoiceSessionState {
  const [state, setState] = useState<VoiceSessionState>(getVoiceState)
  useEffect(() => subscribeVoiceState(setState), [])
  return state
}

function useOutputDevices(active: boolean): MediaDeviceInfo[] {
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([])
  useEffect(() => {
    if (!active) return
    let cancelled = false
    const refresh = (): void => {
      void navigator.mediaDevices.enumerateDevices().then((all) => {
        if (!cancelled) setDevices(all.filter((d) => d.kind === 'audiooutput' && d.label))
      })
    }
    refresh()
    navigator.mediaDevices.addEventListener('devicechange', refresh)
    return () => {
      cancelled = true
      navigator.mediaDevices.removeEventListener('devicechange', refresh)
    }
  }, [active])
  return devices
}

const PROVIDER_LABEL = { openai: 'OpenAI', gemini: 'Gemini' } as const

export function VoiceSessionSurface(props: { onClose?: () => void }): React.JSX.Element {
  const state = useVoiceSession()
  const devices = useOutputDevices(state.status === 'live')
  const [sink, setSink] = useState('')

  useEffect(() => {
    attachVoiceE2eHook()
  }, [])

  const close = (): void => {
    stopVoiceSession()
    props.onClose?.()
  }

  return (
    <div
      data-voice-surface
      className="flex items-center gap-3 rounded-2xl border border-white/10 bg-[color:var(--surface)] px-4 py-3"
    >
      {/* Status dot */}
      <span
        aria-hidden
        className={cn(
          'h-2.5 w-2.5 shrink-0 rounded-full',
          state.status === 'live' && 'animate-pulse bg-white',
          state.status === 'connecting' && 'animate-pulse bg-white/40',
          state.status === 'error' && 'bg-red-400/90',
          state.status === 'idle' && 'bg-white/25'
        )}
      />

      {/* Status text + controls */}
      {state.status === 'idle' && (
        <>
          <div className="flex-1 text-sm text-white/70">Talk with Omi, hands-free</div>
          <button
            onClick={() => void startVoiceSession('openai')}
            className="rounded-xl bg-white/[0.08] px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-white/[0.14]"
          >
            Start voice chat
          </button>
        </>
      )}

      {state.status === 'connecting' && (
        <>
          <div className="flex-1 text-sm text-white/70">
            Connecting · {PROVIDER_LABEL[state.provider]}…
          </div>
          <button
            onClick={close}
            className="rounded-xl px-3 py-1.5 text-sm text-white/60 transition-colors hover:bg-white/[0.08] hover:text-white"
          >
            Cancel
          </button>
        </>
      )}

      {state.status === 'live' && (
        <>
          <div className="min-w-0 flex-1 text-sm text-white">
            {state.muted ? 'Muted' : 'Listening'}
            <span className="ml-2 text-xs text-white/40">{PROVIDER_LABEL[state.provider]}</span>
          </div>
          {devices.length > 1 && (
            <select
              aria-label="Voice output device"
              value={sink}
              onChange={(e) => {
                setSink(e.target.value)
                void setVoiceOutputDevice(e.target.value)
              }}
              className="max-w-[180px] truncate rounded-lg border border-white/10 bg-transparent px-2 py-1 text-xs text-white/70 focus:outline-none [&>option]:bg-neutral-900"
            >
              <option value="">Default output</option>
              {devices.map((d) => (
                <option key={d.deviceId} value={d.deviceId}>
                  {d.label}
                </option>
              ))}
            </select>
          )}
          <button
            onClick={() => setVoiceMuted(!state.muted)}
            aria-label={state.muted ? 'Unmute microphone' : 'Mute microphone'}
            className="rounded-xl bg-white/[0.06] p-2 text-white/80 transition-colors hover:bg-white/[0.12] hover:text-white"
          >
            {state.muted ? <MicOff className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
          </button>
          <button
            onClick={close}
            className="rounded-xl bg-white/[0.08] px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-white/[0.14]"
          >
            End
          </button>
        </>
      )}

      {state.status === 'error' && (
        <>
          <div className="min-w-0 flex-1 truncate text-sm text-red-300/90" title={state.message}>
            {state.message}
          </div>
          {state.retryable && (
            <button
              onClick={() => void startVoiceSession('openai')}
              aria-label="Try again"
              className="inline-flex items-center gap-1.5 rounded-xl bg-white/[0.08] px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-white/[0.14]"
            >
              <RefreshCw className="h-3.5 w-3.5" />
              Try again
            </button>
          )}
          <button
            onClick={close}
            aria-label="Dismiss voice session"
            className="rounded-xl p-2 text-white/60 transition-colors hover:bg-white/[0.08] hover:text-white"
          >
            <X className="h-4 w-4" />
          </button>
        </>
      )}
    </div>
  )
}
