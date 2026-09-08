import { createContext, useContext } from 'react'
import type { UseRecorder } from '../hooks/useRecorder'
import type { UseChat } from '../hooks/useChat'
import type { CaptureChoice } from '../../../shared/types'

export type { CaptureChoice }

export type AppState = {
  recorder: UseRecorder
  chat: UseChat
  pickerOpen: boolean
  setPickerOpen: (v: boolean) => void
  /** Begin a recording for the chosen capture mode (from any tab). */
  startRecording: (choice: CaptureChoice) => void
}

export const Ctx = createContext<AppState | null>(null)

export function useAppState(): AppState {
  const v = useContext(Ctx)
  if (!v) throw new Error('useAppState must be used within AppStateProvider')
  return v
}
