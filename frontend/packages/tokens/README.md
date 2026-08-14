# `@omi-core/tokens`

Dependency-free semantic design tokens for production surfaces. The four
ratified host combinations are `mobileDark`, `mobileLight`,
`desktopLightGlass`, and `desktopDarkGlass`.

Hosts adapt `SEMANTIC_TOKENS` to CSS variables, SwiftUI, or Flutter. Surface
components consume semantic roles rather than importing host colors. The values
intentionally promote the existing black/charcoal mobile ladder and Ink's
light-glass measurements; no unratified purple accent is included.

Typography uses deliberate platform fallbacks (`system`, `rounded`, and
`mono`) rather than naming a font the shipped WebViews do not bundle. The same
contract carries compact/regular/wide content measures, card/floating/overlay
elevation, interaction geometry, and the instant/fast/standard/deliberate
motion ladder used by the production primitive state matrix. Reduced-motion
hosts map every nonessential duration to `instant`; the semantic state itself
must remain visible without animation.
