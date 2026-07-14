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

// The orbit every satellite sits ON. Earlier the satellites were scattered at
// varying distances while the ring stayed fixed, so the ring read as a stray
// circle from some other drawing rather than the orbit they belong to.
const ORBIT = 33

// Deterministic angles (no RNG — this must render identically every time), all at
// the orbit radius. Node sizes still vary, which is what keeps it from looking
// like a stamped clock face; their POSITIONS are what has to be disciplined.
const SATELLITES = [
  { angle: -90, r: 2.6 },
  { angle: -38, r: 3.4 },
  { angle: 14, r: 2.2 },
  { angle: 58, r: 3 },
  { angle: 104, r: 2.4 },
  { angle: 150, r: 3.2 },
  { angle: 196, r: 2.2 },
  { angle: 244, r: 2.8 }
].map(({ angle, r }) => {
  const rad = (angle * Math.PI) / 180
  return { x: 50 + Math.cos(rad) * ORBIT, y: 50 + Math.sin(rad) * ORBIT, r }
})

export function BrainGraphFallback(): React.JSX.Element {
  return (
    <div
      className="absolute inset-0 flex items-center justify-center"
      data-testid="brain-graph-fallback"
    >
      {/* Fills the host square (which is already sized/centred by the pane), so the
          mark grows with the window instead of sitting small in a big empty pane —
          the live map it stands in for scales, and so must this. */}
      <svg viewBox="0 0 100 100" className="h-full w-full text-white" aria-hidden role="img">
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
        {/* The orbit itself — same constant the satellites are placed on, so the two
            can never drift apart again. */}
        <circle
          cx="50"
          cy="50"
          r={ORBIT}
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
