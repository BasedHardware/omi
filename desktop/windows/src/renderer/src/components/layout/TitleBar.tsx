import { Minus, X } from 'lucide-react'

export function TitleBar(): React.JSX.Element {
  return (
    <div
      className="fixed left-0 right-0 top-0 z-[9999] flex h-8 select-none items-center justify-end"
      // The full bar is draggable; the button cluster overrides back to no-drag.
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
        {/* Maximize: use two stacked squares (⧠) to indicate restore/maximize toggle */}
        <button
          onClick={() => window.omi?.winMaximize?.()}
          className="flex h-8 w-11 items-center justify-center text-white/35 transition-colors hover:bg-white/10 hover:text-white/80"
          aria-label="Maximize"
        >
          <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1.2">
            <rect x="1" y="1" width="8" height="8" rx="0.5" />
          </svg>
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
