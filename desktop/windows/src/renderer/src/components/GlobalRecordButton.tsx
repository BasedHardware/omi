import { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { Mic, ChevronDown, Monitor } from 'lucide-react'
import { useAppState, type CaptureChoice } from '../state/AppStateProvider'
import { Shortcut } from './ui/Shortcut'

const OPTIONS: { choice: CaptureChoice; label: string; Icon: typeof Mic; keys?: string[] }[] = [
  { choice: 'mic', label: 'Mic only', Icon: Mic, keys: ['Ctrl', 'Space'] },
  { choice: 'screen', label: 'Screen record', Icon: Monitor }
]

/**
 * Global Record control pinned to the top-right on every tab — and on Home once
 * a chat has started — but hidden on the idle Home screen (which has its own
 * record buttons) and while a recording is already running.
 */
export function GlobalRecordButton(): React.JSX.Element | null {
  const { recorder, chat, startRecording } = useAppState()
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  // Close the menu on any click outside the control or on Escape. A document
  // listener (rather than an overlay) is z-index-proof — the old overlay sat at
  // z-40 and never caught clicks on the z-50 sidebar.
  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent): void => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  const onIdleHome = pathname === '/home' && chat.history.length === 0
  if (recorder.recording || recorder.saving || onIdleHome) return null

  const choose = (choice: CaptureChoice): void => {
    setOpen(false)
    if (choice === 'mic') {
      navigate('/conversations/live')
      return
    }
    startRecording(choice)
  }

  return (
    <div ref={containerRef} className="fixed right-4 top-4 z-40">
      <button
        onClick={() => setOpen((o) => !o)}
        className="btn-record relative z-50 flex items-center gap-2 shadow-lg"
      >
        <Mic className="h-4 w-4" />
        Record
        <ChevronDown className="h-3.5 w-3.5 opacity-70" />
      </button>
      {open && (
        <div className="glass-strong absolute right-0 top-full z-50 mt-2 w-60 overflow-hidden rounded-xl p-1 text-sm">
          {OPTIONS.map(({ choice, label, Icon, keys }) => (
            <button
              key={choice}
              onClick={() => choose(choice)}
              className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left text-white/90 transition-colors hover:bg-white/10"
            >
              <Icon className="h-4 w-4 shrink-0 text-white/60" />
              <span className="flex-1">{label}</span>
              {keys && <Shortcut keys={keys} />}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
