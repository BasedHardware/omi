# INV-UI-2: Desktop UX uses the shared interaction components

**Status:** locked
**Statement:** The macOS app leaves, confirms, copies, dates and labels things one way, through the
shared components named in [`desktop/macos/docs/ux-contract.md`](../../desktop/macos/docs/ux-contract.md);
a page does not draw its own back button, close button, confirmation, copy feedback or date format.

## MUST NOT

- Draw a back control other than `BackChip` (leading edge, names its destination), or a close
  control other than `DismissButton` (trailing edge) — and never an xmark on something that replaced
  the page or a chevron on something floating over it.
- Show a `BackChip` or `DismissButton` without consuming Esc for the same action.
- Delete without either an undo (`UndoToast`) or a confirmation (`.shellConfirmation`); use a system
  `.alert` in the main window; put a close button on an undo toast.
- Copy to the pasteboard without confirming (`CopyButton`, `OmiToastCenter.copy`), or copy an
  empty string as if it succeeded.
- Format a user-visible date with a `DateFormatter.dateFormat` string instead of `OmiDateFormat`.
- Name a transcript speaker other than through `SpeakerLabelFormatter` (raw `SPEAKER_00` labels
  never reach the UI).
- Add `.font(.system(size:))`, literal `scaledFont` sizes, literal corner radii, raw
  `NSCursor.pointingHand.push()`, "..." in UI copy, or a page "More" menu other than `PageMoreMenu`.

## Surfaces

- Desktop SwiftUI (`desktop/macos/Desktop/Sources/**`)

## Guard tests

- `.github/scripts/check_desktop_ux_contract.py` — **no-increase ratchet** per changed file against
  the merge base. Existing debt may remain; a file may not grow more, and a new file starts at zero.
  Deliberate exceptions carry `// omi-ux-allow: <rule-id> -- <reason>` on the line.
- `.github/scripts/test_check_desktop_ux_contract.py` — proves each rule fails on the shape of the
  defect it was written for.
- `desktop/macos/Desktop/Tests/DesktopUXContractTests.swift` — behavior of the shared components
  (date styles, speaker labels, back-to-origin navigation, copy, icon-button ladder, Settings search
  anchors).

## Path globs

- `desktop/macos/Desktop/Sources/**`

## PR rule

Do **not** require naming `INV-UI-2` in routine UI PRs. The ratchet enforces the floor. Name it only
when changing the contract itself: a rule in `ux-contract.md`, a shared component's behavior, or a
rule in the guard.

## Related

- [`brand-ui.md`](./brand-ui.md) (INV-UI-1)
- [`desktop/macos/docs/ux-contract.md`](../../desktop/macos/docs/ux-contract.md)
