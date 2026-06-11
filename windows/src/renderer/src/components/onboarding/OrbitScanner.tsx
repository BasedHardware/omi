// A self-contained "scanning" animation: a bright dot at the center with four
// dots orbiting a single shared ring. The dots spin at different speeds and in
// mixed directions (clockwise / counter-clockwise), each dragging a fading
// comet trail that "paints" the ring as it travels. Pure SVG + CSS so it costs
// nothing and respects the app's global reduce-motion kill-switch.
//
// Geometry is fixed in a 200x200 user space: center (100,100), ring radius 70.
// Each orbiting dot lives in a static "offset" group (spreads the starting
// positions around the ring) wrapping a CSS-animated "spin" group. The head dot
// sits at the ring's 3 o'clock point (170,100); its trail is an arc that ends at
// the head and fades to transparent behind it — mirrored for reverse spinners so
// the tail always lags the motion.

const CENTER = 100
const RADIUS = 70

type Spin = 'cw' | 'ccw'

type OrbitDot = {
  /** Starting angle around the ring, in degrees. */
  offset: number
  /** Spin direction — picks the trail side and animation-direction. */
  spin: Spin
  /** Seconds per revolution. Distinct values give the "different speeds" look. */
  duration: number
  /** Overall brightness of this dot + its trail. */
  opacity: number
}

// Distinct speeds + alternating directions so no two dots ever sync up.
const DOTS: OrbitDot[] = [
  { offset: 0, spin: 'cw', duration: 3.4, opacity: 1 },
  { offset: 95, spin: 'ccw', duration: 5.2, opacity: 0.85 },
  { offset: 190, spin: 'cw', duration: 4.3, opacity: 0.7 },
  { offset: 285, spin: 'ccw', duration: 6.6, opacity: 0.6 }
]

// Comet-trail arcs. The head is always (170,100); the tail trails the motion, so
// clockwise dots fade in from above and counter-clockwise from below.
const TRAIL_CW = 'M 123.94 34.22 A 70 70 0 0 1 170 100'
const TRAIL_CCW = 'M 123.94 165.78 A 70 70 0 0 0 170 100'

export function OrbitScanner(): React.JSX.Element {
  return (
    <svg viewBox="0 0 200 200" className="h-[180px] w-[180px]" aria-hidden="true">
      <defs>
        {/* Trail fades from transparent (tail) to white (head). userSpaceOnUse
            resolves in each dot's rotated frame, so the fade tracks the arc. */}
        <linearGradient id="orbitTrailCw" gradientUnits="userSpaceOnUse" x1="123.94" y1="34.22" x2="170" y2="100">
          <stop offset="0%" stopColor="#fff" stopOpacity="0" />
          <stop offset="100%" stopColor="#fff" stopOpacity="0.9" />
        </linearGradient>
        <linearGradient id="orbitTrailCcw" gradientUnits="userSpaceOnUse" x1="123.94" y1="165.78" x2="170" y2="100">
          <stop offset="0%" stopColor="#fff" stopOpacity="0" />
          <stop offset="100%" stopColor="#fff" stopOpacity="0.9" />
        </linearGradient>
      </defs>

      {/* Faint guide ring the dots travel along. */}
      <circle cx={CENTER} cy={CENTER} r={RADIUS} fill="none" stroke="#fff" strokeOpacity="0.05" />

      {DOTS.map((dot, i) => (
        <g key={i} transform={`rotate(${dot.offset} ${CENTER} ${CENTER})`} opacity={dot.opacity}>
          <g
            style={{
              transformOrigin: `${CENTER}px ${CENTER}px`,
              animation: `orbitSpin ${dot.duration}s linear infinite`,
              animationDirection: dot.spin === 'ccw' ? 'reverse' : 'normal'
            }}
          >
            <path
              d={dot.spin === 'cw' ? TRAIL_CW : TRAIL_CCW}
              fill="none"
              stroke={dot.spin === 'cw' ? 'url(#orbitTrailCw)' : 'url(#orbitTrailCcw)'}
              strokeWidth="2.5"
              strokeLinecap="round"
            />
            <circle cx={CENTER + RADIUS} cy={CENTER} r="3" fill="#fff" />
          </g>
        </g>
      ))}

      {/* Central dot, with a soft halo. */}
      <circle cx={CENTER} cy={CENTER} r="9" fill="#fff" fillOpacity="0.08" />
      <circle cx={CENTER} cy={CENTER} r="4.5" fill="#fff" />
    </svg>
  )
}
