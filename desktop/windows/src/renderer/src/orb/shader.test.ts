import { describe, it, expect } from 'vitest'
import { ORB_FRAG, ORB_VERT } from './shader'

// The orb's merged blob was "misty" (a soft, fuzzy rim instead of a crisp disc)
// because the antialias width was keyed off `fwidth(length(q))` — the gradient of
// the distance-from-centre, which is a constant unit slope. The merged field is
// NOT unit-gradient: chained smin blends (dots + centre pool) and the additive
// rim noise flatten it in places, so a fixed-width AA smeared the edge across
// many pixels wherever the field was flat. The fix derives the AA from the
// screen-space derivative of EACH field itself (`fwidth(dSurf)` / `fwidth(dDots)`),
// which makes every crossing a crisp ~2px band regardless of the field's slope.
//
// These are source-level guards: a true pixel-transition regression check needs a
// real WebGL2 context (see scripts/orb/check-invariants.mjs, run under Playwright
// + SwiftShader). Plain vitest has no GL, so we lock the AA-derivation invariant
// here — reverting to the length(q) form (the bug) fails this test.
describe('orb fragment shader — antialias derivation', () => {
  it('derives the mask AA from each field, not from length(q)', () => {
    expect(ORB_FRAG).toContain('fwidth(dSurf)')
    expect(ORB_FRAG).toContain('fwidth(dDots)')
    // The misty form: AA taken from the constant unit gradient of length(q).
    expect(ORB_FRAG).not.toContain('fwidth(length(q))')
  })

  it('feeds the field-derived AA into the matching smoothstep', () => {
    // surface mask uses the surface's own AA, dot mask uses the dots' own AA.
    expect(ORB_FRAG).toMatch(/smoothstep\(-aaSurf,\s*aaSurf,\s*dSurf\)/)
    expect(ORB_FRAG).toMatch(/smoothstep\(-aaDots,\s*aaDots,\s*dDots\)/)
  })

  it('compiles to WebGL-shaped GLSL ES 3.00 sources', () => {
    // Cheap sanity: both stages declare the ES 3.00 version and the frag has a
    // single color output — guards against an accidental truncation of the
    // template literal (a stray backtick once terminated it mid-shader).
    expect(ORB_VERT).toContain('#version 300 es')
    expect(ORB_FRAG).toContain('#version 300 es')
    expect(ORB_FRAG).toContain('out vec4 outColor')
    expect(ORB_FRAG).toContain('void main()')
  })
})
