// The bar chat's "waiting for Omi's reply" loader: the Omi dot-ring mark, spun
// fast (see .omi-thinking-spin in globals.css). It stands ALONE — deliberately
// NOT wrapped in a message bubble — left-aligned where the assistant reply will
// land, so when the reply arrives the bubble simply pops in (bubble-in) and this
// loader is unmounted. Replaces the old bubble-of-dots ("…") pending indicator in
// the floating bar's inline conversation (overlay variant only).
//
// The eight-dot ring mirrors the shipped omi-mark.png glyph (the same mark
// ConnectorBrandMark's OmiMark / macOS HomeOmiMarkIcon draw), rendered inline so
// it tints white for the dark bar panel. A graded opacity around the ring gives a
// bright "head" and faded "tail": without it, eight identical evenly-spaced dots
// have 8-fold symmetry and rotation would read as a static shimmer rather than a
// clear spin. The head/tail makes the direction and speed obvious.

// Eight dots on a radius-6.6 ring inside a 24×24 box (exact omi-mark geometry),
// index 0 at the top going clockwise. Opacity ramps 1.0 → 0.2 head-to-tail.
const DOTS = Array.from({ length: 8 }, (_, i) => {
  const angle = (i * Math.PI) / 4
  return {
    cx: 12 + 6.6 * Math.sin(angle),
    cy: 12 - 6.6 * Math.cos(angle),
    opacity: 1 - i * (0.8 / 7)
  }
})

export function OmiThinkingSpinner(): React.JSX.Element {
  return (
    <div className="mr-auto flex items-center pl-1" role="status" aria-label="Omi is thinking">
      <svg
        viewBox="0 0 24 24"
        className="omi-thinking-spin h-5 w-5"
        fill="#f0ece3"
        aria-hidden="true"
      >
        {DOTS.map((d, i) => (
          <circle key={i} cx={d.cx} cy={d.cy} r="1.55" fillOpacity={d.opacity} />
        ))}
      </svg>
    </div>
  )
}
