import { useEffect, useState } from 'react'
import { Square, Monitor } from 'lucide-react'
import type { TranscriptLine } from '../../../shared/types'

function fmtElapsed(totalSec: number): string {
  const m = Math.floor(totalSec / 60)
  const r = totalSec % 60
  return `${m}:${r.toString().padStart(2, '0')}`
}

/**
 * Minimal transcription card docked at the bottom-right while recording. It's
 * non-blocking — the rest of the app (chat, tabs, adding a screen) stays usable
 * underneath it. Shows the live microphone transcript, an elapsed timer, Stop,
 * and (when no screen is captured yet) an "Add screen" button. System audio is
 * transcribed too but only surfaces in the saved conversation, not here.
 */
export function TranscriptPopup(props: {
  micLines: TranscriptLine[]
  micInterim: string
  saving: boolean
  hasScreen: boolean
  onStop: () => void
  onAddScreen: () => void
}): React.JSX.Element {
  const { micLines, micInterim, saving, hasScreen, onStop, onAddScreen } = props
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    const id = setInterval(() => setElapsed((s) => s + 1), 1000)
    return () => clearInterval(id)
  }, [])

  return (
    <div className="fixed bottom-4 right-4 z-30 w-80 max-w-[calc(100vw-2rem)]">
      <div className="glass-strong animate-fade-in rounded-2xl p-3 shadow-2xl">
        <div className="mb-2 flex items-center justify-between">
          <span className="flex items-center gap-2 text-xs font-medium text-white/85">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-pulse-ring rounded-full bg-red-400/40" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-red-400" />
            </span>
            Recording
          </span>
          <span className="font-mono text-[10px] text-white/45">{fmtElapsed(elapsed)}</span>
        </div>

        <div className="max-h-24 min-h-[48px] overflow-y-auto rounded-xl bg-black/20 p-2 text-xs leading-relaxed">
          {micLines.map((l, i) => (
            <div key={i} className="whitespace-pre-wrap text-white/90">
              {l.speaker && <span className="text-white/55">{l.speaker}: </span>}
              {l.text}
            </div>
          ))}
          {micInterim && (
            <div className="whitespace-pre-wrap italic text-white/40">{micInterim}</div>
          )}
          {micLines.length === 0 && !micInterim && (
            <span className="text-white/40">Listening…</span>
          )}
        </div>

        <div className="mt-2 flex items-center justify-between gap-2">
          {hasScreen ? (
            <span className="flex items-center gap-1.5 text-[10px] text-white/40">
              <Monitor className="h-2.5 w-2.5" /> Capturing screen
            </span>
          ) : (
            <button
              onClick={onAddScreen}
              className="flex items-center gap-1.5 text-[10px] text-white/45 transition-colors hover:text-white/80"
            >
              <Monitor className="h-2.5 w-2.5" /> Add screen
            </button>
          )}
          <button onClick={onStop} disabled={saving} className="btn-danger px-3 py-1 text-xs">
            <Square className="h-3 w-3" />
            {saving ? 'Saving…' : 'Stop'}
          </button>
        </div>
      </div>
    </div>
  )
}
