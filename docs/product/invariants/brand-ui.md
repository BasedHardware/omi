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
- Windows desktop app (`desktop/windows/**`) — **carved out** (see below); not ratchet-scanned.

## Windows carve-out (ruling B, 2026-07-14)

The Windows desktop app faithfully ports macOS's palette, and macOS's beta ships
purple. Per **ruling B (Chris, 2026-07-14)**, purple in `desktop/windows/**` is
intentional and correct — Windows adds the same purple/HomePalette tokens macOS
defines, for Hub/chat/brain-graph surfaces.

Windows is therefore **intentionally excluded** from the no-purple ratchet: it is
deliberately absent from the guard's `UI_ROOTS`, not an oversight. A no-increase
ratchet there would fail every faithful purple port. Do not add `desktop/windows`
to `UI_ROOTS` without re-baselining this decision.

The rule still holds within Windows **in spirit**: do not introduce purple where
macOS renders neutral — only port the purple macOS itself ships. This is a
review/verification concern, not CI-enforced. macOS, Flutter app, and web remain
fully guarded by the ratchet.

## Guard tests

- `.github/scripts/check_brand_ui.py` — **no-increase ratchet** on purple
  literals / `Color.purple` / purple theme tokens in changed UI files. Existing
  debt may remain; introducing new purple in a file (or raising its count vs
  the PR base) fails. Allowlist escape: add a path under `ALLOWLIST_FILES` in
  that script with a comment citing why.

## Path globs

Enforced (scanned by the ratchet):

- `desktop/macos/Desktop/Sources/**`
- `app/lib/**`
- `web/**`

Carved out (intentionally **not** in the enforced globs):

- `desktop/windows/**` — faithful macOS palette port; see Windows carve-out above.

## PR rule

Do **not** require naming `INV-UI-1` in routine UI PRs. The brand ratchet
enforces the floor. Name `INV-UI-1` only when intentionally changing brand
color policy or the allowlist.

## Related

- [`AGENTS.md`](../../../AGENTS.md) → Coding Guidelines → UI / Design
