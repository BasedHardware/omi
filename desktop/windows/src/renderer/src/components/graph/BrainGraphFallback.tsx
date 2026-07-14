// Static, non-WebGL stand-in for the brain map.
//
// Shown when this renderer cannot get a WebGL context (GPU crash / crash loop /
// a machine with no usable GL) or when the three.js renderer throws on mount.
// Before this existed, those cases left an empty black pane — most visibly on the
// ONBOARDING split screen, where the map is half the first thing a new user sees.
//
// Deliberately a resting MARK, not a fake graph: one centre node, a faint ring of
// satellites, hairline links. It reads as the map at rest rather than as an error,
// carries no text, and never animates (there is no GPU to animate it with).
// Monochrome white at low alpha — no purple anywhere (brand invariant INV-UI-1).

// Satellites on a fixed ring, at deterministic angles (no RNG — this must render
// identically every time). Radii vary slightly so the ring doesn't look stamped.
const SATELLITES = [
  { angle: -90, dist: 34, r: 2.6 },
  { angle: -38, dist: 30, r: 3.4 },
  { angle: 14, dist: 36, r: 2.2 },
  { angle: 58, dist: 28, r: 3 },
  { angle: 104, dist: 35, r: 2.4 },
  { angle: 150, dist: 31, r: 3.2 },
  { angle: 196, dist: 27, r: 2.2 },
  { angle: 244, dist: 34, r: 2.8 }
].map(({ angle, dist, r }) => {
  const rad = (angle * Math.PI) / 180
  return { x: 50 + Math.cos(rad) * dist, y: 50 + Math.sin(rad) * dist, r }
})

export function BrainGraphFallback(): React.JSX.Element {
  return (
    <div
      className="absolute inset-0 flex items-center justify-center"
      data-testid="brain-graph-fallback"
    >
      <svg
        viewBox="0 0 100 100"
        className="h-full w-full max-h-[520px] max-w-[520px] text-white"
        aria-hidden
        role="img"
      >
        {SATELLITES.map((s, i) => (
          <line
            key={`l${i}`}
            x1="50"
            y1="50"
            x2={s.x}
            y2={s.y}
            stroke="currentColor"
            strokeWidth="0.3"
            opacity="0.1"
          />
        ))}
        <circle
          cx="50"
          cy="50"
          r="33"
          fill="none"
          stroke="currentColor"
          strokeWidth="0.2"
          opacity="0.06"
        />
        {SATELLITES.map((s, i) => (
          <circle key={`n${i}`} cx={s.x} cy={s.y} r={s.r} fill="currentColor" opacity="0.22" />
        ))}
        {/* Centre ("you") node: the one element with real presence. */}
        <circle cx="50" cy="50" r="9" fill="currentColor" opacity="0.05" />
        <circle cx="50" cy="50" r="5" fill="currentColor" opacity="0.35" />
      </svg>
    </div>
  )
}
