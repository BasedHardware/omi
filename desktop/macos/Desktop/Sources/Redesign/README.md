# omi macOS — Redesign (light mode)

Frontend-only redesign of the macOS app to match the mockup at
`https://archit-lal.github.io/omi/` (source: `mockup/screens/*.html`, `mockup/design-system.css`).

## Design language (golden source: `design-system.css`)
- **Light mode**, warm-paper canvas `#F4F2ED`, white cards, near-black ink `#201F1A`.
- **Monochrome ink accent** — no purple, no colored accent. Amber is defined in the CSS
  but overridden to ink everywhere; treat the accent as ink.
- Semantic color only: `live` green `#2CC66B` (Capture/Listening, "Held", "Granted"),
  `warn` orange `#E8913A` ("Needs you", "Due today"), `danger` red `#E5544B` (destructive).
- Native type: New York **serif** for display / stat numbers / the `omi.` wordmark;
  SF Pro **sans** for body; SF Mono for dates / counts / code.
- Pill-soft buttons, hairline cards (no drop shadow), generous whitespace.
- The **omi buddy** — an 8-dot rotating ring — is the brand presence mark.

## Structure
- **68px nav rail** replaces the old sidebar. Order: buddy→Home, Home, Ask omi, Memory,
  Messages(badge), Rewind, [spacer], All features, Settings. Many pages share one rail icon
  (Home covers dashboard/focus/insights/tasks; Memory covers conversations/memory/persona/graph;
  Settings covers permissions/plan/help).
- Window chrome: presence chips (Capture / Listening) top-right.

## Voice (golden rule)
Short, simple, conversational, non-redundant, absolutely clear. First person, from omi.
Benefit-led. Reassuring about privacy ("On your Mac · encrypted · you own it all").
Every button and step must be obvious to a first-time user.

## Wiring
Frontend only. Every screen stays live-wired to existing stores/services; no backend changes.
Redesign is additive: new light-mode `Ink*` design system + new pages, routed through the
existing `selectedIndex` / `PageContentView` switch and the existing onboarding step ladder.

## Onboarding
Existing = 19 wired steps; mockup = 7-step narrative. We keep every functional step and its
wiring, but reskin to the new design system + omi voice, add the 7-segment progress rail and
the buddy, and consolidate the presentation toward the mockup's calm, handheld flow.

## Status
Phased. This PR establishes the design system + shell (rail, light mode, window chrome) and
rebuilds screens incrementally. See the PR description for what is done vs. in progress.
