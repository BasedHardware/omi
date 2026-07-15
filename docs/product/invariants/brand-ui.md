# INV-UI-1: No purple; neutral accents

**Status:** locked
**Statement:** Purple is off-brand. UI accents and primary actions use
white/neutral treatments, not purple hues, glows, or gradients.

## MUST NOT

- Use purple in UI (icons, accents, glows, hover states, gradients).
- Introduce new purple system colors or brand tokens.

## Surfaces

- Desktop SwiftUI (`OmiTheme` and views)
- Flutter app UI
- Web marketing / admin UI that ships under the Omi brand

## Guard tests

- `.github/scripts/check_brand_ui.py` — **no-increase ratchet** on purple
  literals / `Color.purple` / purple theme tokens in changed UI files. Existing
  debt may remain; introducing new purple in a file (or raising its count vs
  the PR base) fails. Allowlist escape: add a path under `ALLOWLIST_FILES` in
  that script with a comment citing why.

## Path globs

- `desktop/macos/Desktop/Sources/**`
- `app/lib/**`
- `web/**`

## PR rule

Do **not** require naming `INV-UI-1` in routine UI PRs. The brand ratchet
enforces the floor. Name `INV-UI-1` only when intentionally changing brand
color policy or the allowlist.

## Related

- [`AGENTS.md`](../../../AGENTS.md) → Coding Guidelines → UI / Design
