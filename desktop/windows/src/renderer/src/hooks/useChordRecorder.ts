import { useEffect, useRef, useState } from 'react'
import { eventToAccelerator, validateCustomAccelerator } from '../lib/overlayShortcut'

/** Message shown when the OS reports the chord is already owned by another app.
 *  Identical across both recording surfaces. */
export const CHORD_IN_USE_MESSAGE = 'That shortcut is already in use — try another.'

export type ChordCommitResult = { ok: boolean; registered: boolean }

export type UseChordRecorderConfig = {
  /** Release global chords so the raw keydown reaches us. Called when recording
   *  starts. */
  suspend: () => void
  /** Re-claim global chords. Called when recording stops (any reason) or the
   *  component unmounts mid-recording. */
  resume: () => void
  /** Persist a validated accelerator. Resolve ok:true to accept it, ok:false when
   *  it is already owned by another app (the hook then shows CHORD_IN_USE_MESSAGE). */
  commit: (accelerator: string) => Promise<ChordCommitResult>
  /** Called with the accepted accelerator + its commit result after commit ok. */
  onCommitted: (accelerator: string, result: ChordCommitResult) => void
  /** Surface a validation / in-use message; null clears it. */
  onError: (message: string | null) => void
}

export type ChordRecorder = {
  recording: boolean
  /** Begin capturing keys (clears any prior error first). */
  start: () => void
}

/**
 * The capture-phase keydown flow shared by the two "record a global shortcut"
 * surfaces (Settings record hotkey, onboarding summon shortcut): while recording,
 * every keydown is captured (preventDefault / stopPropagation); Esc cancels; a
 * complete chord is validated (validateCustomAccelerator) and committed. Global
 * chords are suspended for the duration and resumed on stop / unmount — both
 * injected so each surface drives its own shortcut slot with its own commit target.
 */
export function useChordRecorder(config: UseChordRecorderConfig): ChordRecorder {
  const [recording, setRecording] = useState(false)
  // Read config live from a ref so the keydown handler (bound once per recording
  // session) never closes over a stale callback after a re-render. Updated in an
  // effect (not during render) so it's always the latest committed config.
  const cfgRef = useRef(config)
  useEffect(() => {
    cfgRef.current = config
  })

  useEffect(() => {
    if (!recording) return
    cfgRef.current.suspend()
    const onKeyDown = (e: KeyboardEvent): void => {
      e.preventDefault()
      e.stopPropagation()
      if (e.key === 'Escape') {
        setRecording(false)
        return
      }
      const next = eventToAccelerator(e)
      if (!next) return // still building the chord (modifier-only / no key yet)
      const valid = validateCustomAccelerator(next)
      if (!valid.ok) {
        cfgRef.current.onError(valid.reason)
        return // stay recording so the user can immediately try another
      }
      void (async () => {
        const result = await cfgRef.current.commit(next)
        if (result.ok) {
          cfgRef.current.onError(null)
          cfgRef.current.onCommitted(next, result)
        } else {
          cfgRef.current.onError(CHORD_IN_USE_MESSAGE)
        }
        setRecording(false)
      })()
    }
    window.addEventListener('keydown', onKeyDown, true)
    return () => {
      window.removeEventListener('keydown', onKeyDown, true)
      cfgRef.current.resume()
    }
  }, [recording])

  return {
    recording,
    start: (): void => {
      cfgRef.current.onError(null)
      setRecording(true)
    }
  }
}
