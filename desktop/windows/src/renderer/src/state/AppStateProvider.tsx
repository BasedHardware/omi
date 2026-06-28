import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import { useRecorder, type UseRecorder } from '../hooks/useRecorder'
import { useChat, type UseChat } from '../hooks/useChat'
import type { CaptureChoice } from '../../../shared/types'

export type { CaptureChoice }

type AppState = {
  recorder: UseRecorder
  chat: UseChat
  pickerOpen: boolean
  setPickerOpen: (v: boolean) => void
  /** Begin a recording for the chosen capture mode (from any tab). */
  startRecording: (choice: CaptureChoice) => void
}

const Ctx = createContext<AppState | null>(null)

/**
 * App-level state shared across every tab: the recorder and chat engines live
 * here (not inside a single page) so recording keeps running and the chat
 * thread persists while navigating, and so a global Record control can drive
 * them from anywhere. Must be mounted inside the Router (useRecorder navigates).
 */
export function AppStateProvider(props: { children: React.ReactNode }): React.JSX.Element {
  const recorder = useRecorder()
  const chat = useChat({ surface: 'main' })
  const [pickerOpen, setPickerOpen] = useState(false)

  // Hold the live recorder in a ref (updated after each render) so the keydown
  // handler can read current state without stale closures or re-subscribing.
  const recorderRef = useRef(recorder)
  useEffect(() => {
    recorderRef.current = recorder
  })

  const startRecording = useCallback((choice: CaptureChoice): void => {
    // 'screen' transcribes both the mic and system (loopback) audio; 'mic' is
    // mic-only.
    const withSystem = choice === 'screen'
    const withScreen = choice === 'screen'
    void recorderRef.current.start({ system: withSystem })
    if (withScreen) setPickerOpen(true)
  }, [])

  return (
    <Ctx.Provider value={{ recorder, chat, pickerOpen, setPickerOpen, startRecording }}>
      {props.children}
    </Ctx.Provider>
  )
}

export function useAppState(): AppState {
  const v = useContext(Ctx)
  if (!v) throw new Error('useAppState must be used within AppStateProvider')
  return v
}
