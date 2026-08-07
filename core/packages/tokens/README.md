# `@omi-core/tokens`

Dependency-free semantic design tokens for production surfaces. Wave 0 exposes
exactly two ratified themes: `mobileDark` and `desktopLightGlass`.

Hosts adapt `SEMANTIC_TOKENS` to CSS variables, SwiftUI, or Flutter. Surface
components consume semantic roles rather than importing host colors. The values
intentionally promote the existing black/charcoal mobile ladder and Ink's
light-glass measurements; no unratified purple accent is included.
