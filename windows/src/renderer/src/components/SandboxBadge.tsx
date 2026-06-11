// Dev-only visual marker so multiple sandbox app windows are instantly
// distinguishable. Renders nothing unless VITE_SANDBOX_NAME is set, so it is
// inert in real builds. Fixed to the bottom-left corner, pointer-events-none so
// it never intercepts clicks.

// Pick black/white text for legible contrast against the badge color (YIQ).
function contrastText(hex: string): string {
  const m = /^#?([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(hex.trim())
  if (!m) return '#000'
  let h = m[1]
  if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2]
  const r = parseInt(h.slice(0, 2), 16)
  const g = parseInt(h.slice(2, 4), 16)
  const b = parseInt(h.slice(4, 6), 16)
  const yiq = (r * 299 + g * 587 + b * 114) / 1000
  return yiq >= 140 ? '#000' : '#fff'
}

export function SandboxBadge(): React.JSX.Element | null {
  const name = import.meta.env.VITE_SANDBOX_NAME as string | undefined
  if (!name) return null

  const color = (import.meta.env.VITE_SANDBOX_COLOR as string | undefined)?.trim() || '#444'

  return (
    <div
      className="pointer-events-none fixed bottom-2.5 left-2.5 z-[9999] select-none rounded-full px-2.5 py-1 font-display text-[11px] font-semibold tracking-tight shadow-lg ring-1 ring-black/20"
      style={{ backgroundColor: color, color: contrastText(color) }}
      title={`Sandbox: ${name}`}
    >
      {name}
    </div>
  )
}
