import { useRef, useState } from 'react'

export type RecordingState = 'idle' | 'recording' | 'stopping'

export function useRecording(): {
  state: RecordingState
  start: () => string
  stop: () => { conversationId: string; startedAt: number; endedAt: number } | null
  conversationIdRef: React.MutableRefObject<string | null>
} {
  const [state, setState] = useState<RecordingState>('idle')
  const conversationIdRef = useRef<string | null>(null)
  const startedAtRef = useRef<number | null>(null)

  const start = (): string => {
    const id = `local-${crypto.randomUUID()}`
    conversationIdRef.current = id
    startedAtRef.current = Date.now()
    setState('recording')
    return id
  }

  const stop = (): { conversationId: string; startedAt: number; endedAt: number } | null => {
    if (!conversationIdRef.current || !startedAtRef.current) return null
    const out = {
      conversationId: conversationIdRef.current,
      startedAt: startedAtRef.current,
      endedAt: Date.now()
    }
    conversationIdRef.current = null
    startedAtRef.current = null
    setState('idle')
    return out
  }

  return { state, start, stop, conversationIdRef }
}
