# INV-UI-3: Mobile UX contract — one primitive per UI job

**Status:** locked
**Statement:** In the Flutter app every recurring UI job goes through the one shared primitive named in [`app/docs/ux-contract.md`](../../app/docs/ux-contract.md), and changed files never add a hand-rolled variant.

The jobs: leaving a surface, sheets, confirmations, toasts, copying, dates and durations, speaker
names, colours, type, radii, spinners and user-facing copy.

## MUST NOT

- Draw a back or close control by hand (`Icons.arrow_back*`, `FontAwesomeIcons.arrowLeft` /
  `chevronLeft`) instead of `OmiBackButton` / `OmiCloseButton`, or push a page with
  `PageRouteBuilder` (it has no iOS back swipe).
- Call `showModalBottomSheet`, `AlertDialog(`, `CupertinoAlertDialog(`, `SnackBar(` or
  `Clipboard.setData` directly instead of `showOmiSheet`, `showOmiConfirm` / `showOmiAlert`,
  `OmiFeedback`, `OmiClipboard`.
- Format a date with a pattern string (`DateFormat('h:mm a')`, `dateTimeFormat('MMM d', …)`); use
  `OmiDateFormat`, which follows the locale and the 24-hour setting.
- Add `Color(0x…)`, numeric `fontSize:` or `BorderRadius.circular(<number>)` literals instead of
  `OmiColors` / `OmiType` / `OmiRadius`, or a raw `CircularProgressIndicator` instead of `OmiSpinner`.
- Ship user-facing English in `Text('…')`, or "..." in a string (use "…").
- Delete something with neither a confirmation nor an Undo, or offer "Don't ask again" on an action
  no Undo backs.

## Surfaces

- Flutter mobile app (`app/lib/`)

## Guard tests

- `.github/scripts/check_mobile_ux_contract.py` — **no-increase ratchet**, per rule and per
  changed file under `app/lib/` against the PR merge base (new files start at zero). Generated
  code and the primitives under `app/lib/ui/` are exempt. Escape hatch for a deliberate exception:
  end the line with `// omi-ux-allow: <rule> -- <reason>`.
- `.github/scripts/test_check_mobile_ux_contract.py` — proves every rule fails on the defect it
  targets and passes with the allow comment, on an unchanged count and on a decrease.

## Path globs

- `app/lib/**`

## PR rule

Do **not** require naming `INV-UI-3` in routine UI PRs. The ratchet enforces the floor. Name
`INV-UI-3` only when changing a rule in the contract, a primitive's behaviour, or the guard.

## Related

- [`app/docs/ux-contract.md`](../../app/docs/ux-contract.md) — the rules and the component for each
- [`brand-ui.md`](./brand-ui.md) — INV-UI-1, no purple
- macOS twin: `INV-UI-2` (`desktop-ux-contract.md`, BasedHardware/omi#17286)
