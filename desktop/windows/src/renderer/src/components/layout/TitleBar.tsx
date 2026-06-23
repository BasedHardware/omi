import { useEffect, useState } from 'react'
import { Minus, X } from 'lucide-react'

// Single square = maximize; overlapping squares = restore (matches Win11 Fluent iconography)
function MaximizeIcon(): React.JSX.Element {
  return (
    <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1.2">
      <rect x="1" y="1" width="8" height="8" rx="0.5" />
    </svg>
  )
}

function RestoreIcon(): React.JSX.Element {
  return (
    <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1.2">
      <rect x="3" y="1" width="6" height="6" rx="0.5" />
      <path d="M1 3.5V8.5a0.5 0.5 0 0 0 0.5 0.5H7" />
    </svg>
  )
}

export function TitleBar(): React.JSX.Element {
  const [maximized, setMaximized] = useState(false)

  useEffect(() => {
    // Seed the initial state (window may already be maximized on first render).
    void (window.omi as any)?.winIsMaximized?.().then(setMaximized)
    // Subscribe to maximize/unmaximize events pushed from main.
    const unsub = (window.omi as any)?.onWinMaximizeChange?.(setMaximized)
    return () => unsub?.()
  }, [])

  return (
    <div
      className="fixed left-0 right-0 top-0 z-[9999] flex h-8 select-none items-center justify-end"
      style={{ WebkitAppRegion: 'drag' } as React.CSSProperties}
    >
      <div
        className="flex items-center"
        style={{ WebkitAppRegion: 'no-drag' } as React.CSSProperties}
      >
        <button
          onClick={() => window.omi?.winMinimize?.()}
          className="flex h-8 w-11 items-center justify-center text-white/35 transition-colors hover:bg-white/10 hover:text-white/80"
          aria-label="Minimize"
        >
          <Minus size={11} strokeWidth={1.5} />
        </button>
        <button
          onClick={() => window.omi?.winMaximize?.()}
          className="flex h-8 w-11 items-center justify-center text-white/35 transition-colors hover:bg-white/10 hover:text-white/80"
          aria-label={maximized ? 'Restore' : 'Maximize'}
          title={maximized ? 'Restore' : 'Maximize'}
        >
          {maximized ? <RestoreIcon /> : <MaximizeIcon />}
        </button>
        <button
          onClick={() => window.omi?.winClose?.()}
          className="flex h-8 w-11 items-center justify-center rounded-tr text-white/35 transition-colors hover:bg-red-600 hover:text-white"
          aria-label="Close"
        >
          <X size={11} strokeWidth={1.5} />
        </button>
      </div>
    </div>
  )
}
