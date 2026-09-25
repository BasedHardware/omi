# Omi v2 UI → Flutter: start here

This folder is everything a coding agent needs to restyle the existing Flutter app (`app/`) to the Omi v2
design. It is a **restyle of the current app**, not a rewrite: same pages, same providers, same backend calls.
It works for **iOS and Android** from the same Dart code.

## What's inside

| Path | Use it for |
|---|---|
| `SCREEN_MAP.md` | Which design screen replaces which Flutter file, in build order. |
| `renders/dark/*.png`, `renders/light/*.png` | The visual target for every screen (393×852 pt, @2×). |
| `renders/wires/*.png` | Rev 3 simple wires: multi-device direction (Devices tab, source switcher). |
| `flutter/omi_tokens_v2.dart` | New values for the existing `OmiColors` / `OmiRadius` / `OmiMotion` names, plus a few NEW tokens. |
| `flutter/omi_ring_logo.dart` | The Omi logo (eight dots on a ring, measured from `assets/images/herologo.png`) with still / breathe / chase / orbit animations. |
| `flutter/live_capture_controls.dart` | Reference for the Home live card: Pause/Resume + End. |
| `flutter/test/*` | Widget tests for the two components (they pass on Flutter 3.44.5 — see `TESTED.md`). |
| `icons/glyphs/*.svg` | 107 icons on a 24-pt grid (SF-Symbols-style). Tab icons have `-fill` variants for the selected tab. |
| `icons/logo/`, `icons/app-icon/` | Ring logo SVGs; app icon in default / dark / tinted / clear. |
| `spec/` | What every button does, where it goes, the transition (520 controls, 58 screens). |
| `tokens.json` | All design values in one JSON (colors dark + light, type, radii, spacing, motion). |

## Rules (read before writing code)

1. **Follow the mobile UX contract** (`app/docs/ux-contract.md`, invariant `INV-UI-3`): no `Color(0x…)`,
   numeric `fontSize:` or `BorderRadius.circular(n)` in pages. Change the **token values** in
   `app/lib/ui/omi_tokens.dart`, add new tokens there, and use the shared components in `app/lib/ui/components/`.
2. **Behaviour does not change.** Keep providers, services, capture (`pauseCapture` / `resumeCapture` /
   `finishCapture`), and every API call. This is UI only. No backend changes.
3. **One PR per row of `SCREEN_MAP.md`.** Step 0 (tokens + components) first: it restyles the whole app with no
   page edits.
4. **Status never lies.** Blue (`OmiColorsV2.live`) only while audio is really captured. No fake waveforms.
5. **User-facing text goes through l10n** (`app/lib/l10n/*.arb`, 49 locales).
6. **Compare with the render.** For each screen, run the app's visual-audit tool and put the before/after next to
   `renders/…/<Screen>.png` in the PR.
7. Sample names, numbers and `[Price]` in renders are placeholders.

## Prompt to give Claude Code

> Read `design/omi-flutter-v2/START_HERE.md` and `SCREEN_MAP.md`. Do step 0 only: apply the values from
> `flutter/omi_tokens_v2.dart` to the existing names in `app/lib/ui/omi_tokens.dart`, add the NEW tokens, and add
> `OmiRingLogo` to `app/lib/ui/components/` (exported from `ui.dart`) with its test. Follow `app/AGENTS.md` and the
> UX contract. Run the app's checks. Then show me screenshots of Home, Conversations and Settings before/after.

Then repeat with "do step 1", "do step 2", … one at a time.

## Android

Yes — the same Flutter code runs on Android. Differences to handle:

| Topic | iOS | Android |
|---|---|---|
| Back | edge swipe | system back + predictive back gesture: use `PopScope`, never block it |
| Top of screen | island / notch / none | punch-hole cameras in various places: always `SafeArea`; keep the top-centre empty (the design already does) |
| Glass blur | `BackdropFilter` is fine | costly on low-end devices: fall back to solid `surface1` when the device is slow or "reduce transparency" is on |
| Icons | SVG glyphs (no SF Symbols in Flutter) | same SVGs — consistent on both |
| Font | SF Pro (system) | Roboto (system). Do not bundle SF Pro (licence). Type scale stays the same |
| Sheets | large top radius (40) | 28 radius, Material drag handle |
| Haptics | `OmiHaptics` | same calls; weaker on many devices — never the only feedback |
| Live Activity / Dynamic Island | native Swift (separate project) | the ongoing recording notification (`lib/utils/audio/foreground.dart`) with Pause / End actions |
| Reduce motion | Reduce Motion | "Remove animations" — `OmiMotion.of(context)` already covers both |
