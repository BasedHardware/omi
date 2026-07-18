import { useEffect, useState, useCallback } from 'react'
import {
  startMonologur,
  stopMonologur,
  setOnProactiveMessage,
  setOnMonologurStatusChange,
  getMonologurSettings
} from '../../lib/monologurEngine'
import { resumeAfterInteraction } from '../../lib/ttsService'

type MonologurStatus = 'idle' | 'listening' | 'thinking' | 'speaking'

export function MonologurHost(): React.JSX.Element | null {
  const [status, setStatus] = useState<MonologurStatus>('idle')
  const [lastMessage, setLastMessage] = useState<string | null>(null)
  const [showMessage, setShowMessage] = useState(false)
  const [ttsProvider, setTtsProvider] = useState<'web' | 'deepgram'>('web')

  const handleMessage = useCallback((text: string) => {
    setLastMessage(text)
    setShowMessage(true)
    setTimeout(() => setShowMessage(false), 10000)
  }, [])

  useEffect(() => {
    const handleInteraction = (): void => {
      resumeAfterInteraction()
    }
    document.addEventListener('click', handleInteraction, { once: true })

    setOnProactiveMessage(handleMessage)
    setOnMonologurStatusChange(setStatus)

    const settings = getMonologurSettings()
    setTtsProvider(settings.ttsProvider)

    if (settings.enabled) {
      startMonologur()
    }

    return () => {
      document.removeEventListener('click', handleInteraction)
      setOnProactiveMessage(null)
      setOnMonologurStatusChange(null)
      stopMonologur()
    }
  }, [handleMessage])

  if (status === 'idle') return null

  const isDeepgram = ttsProvider === 'deepgram'

  return (
    <>
      {/* Status indicator */}
      <div
        className="fixed bottom-4 left-4 z-50 flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-medium shadow-lg"
        style={{
          backgroundColor: 'rgba(0, 0, 0, 0.7)',
          color: 'white'
        }}
      >
        <div
          className="h-2 w-2 rounded-full"
          style={{
            backgroundColor:
              status === 'speaking'
                ? '#22c55e'
                : status === 'thinking'
                  ? '#eab308'
                  : status === 'listening'
                    ? '#3b82f6'
                    : '#6b7280',
            animation: status === 'thinking' ? 'pulse 1s infinite' : undefined
          }}
        />
        <span>
          {status === 'speaking'
            ? `Monologur speaking${isDeepgram ? ' (Deepgram)' : ''}...`
            : status === 'thinking'
              ? 'Monologur thinking...'
              : status === 'listening'
                ? `Monologur listening${isDeepgram ? ' (Deepgram)' : ''}`
                : 'Monologur'}
        </span>
      </div>

      {/* Proactive message toast */}
      {showMessage && lastMessage && (
        <div
          className="fixed bottom-16 left-4 z-50 max-w-sm rounded-lg p-4 shadow-xl transition-all duration-300"
          style={{
            backgroundColor: 'rgba(59, 130, 246, 0.9)',
            color: 'white',
            transform: showMessage ? 'translateY(0)' : 'translateY(20px)',
            opacity: showMessage ? 1 : 0
          }}
        >
          <div className="flex items-start gap-3">
            <div className="flex-shrink-0 text-lg">💬</div>
            <div>
              <div className="mb-1 text-xs font-semibold opacity-80">
                Monologur {isDeepgram ? '(Deepgram TTS)' : ''}
              </div>
              <div className="text-sm">{lastMessage}</div>
            </div>
            <button
              onClick={() => setShowMessage(false)}
              className="ml-2 flex-shrink-0 opacity-70 hover:opacity-100"
            >
              ✕
            </button>
          </div>
        </div>
      )}

      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.5; }
        }
      `}</style>
    </>
  )
}
