# Desktop (Windows/Linux) — Developer Guide

## Project Overview

Omi's Electron + React + TypeScript desktop app. One codebase ships both the
Windows and Linux builds (`electron-builder.config.mjs`'s `linux`/`win` targets);
there is no separate Linux-only source tree. See `README.md` for the quickstart
and feature overview.

## Package manager: pnpm, not npm

This directory is pnpm-managed (`pnpm-lock.yaml`, `pnpm-workspace.yaml`) and CI
installs exclusively with `pnpm install --frozen-lockfile`
(`.github/workflows/desktop-windows-ci.yml`, `desktop_windows_release.yml`).
Running `npm install` here corrupts `package.json`/`pnpm-lock.yaml`/
`pnpm-workspace.yaml` (npm doesn't understand pnpm-workspace semantics) and
produces a stray, untracked `package-lock.json` — if you see unexplained diffs
in those three files with no matching commit, this is almost certainly why;
`git restore` them and reinstall with pnpm.

**pnpm major-version pin:** CI pins `pnpm/action-setup@v6` to **version 10**.
If your local `pnpm --version` is a different major (e.g. a system package
manager installed 11+), `.npmrc`'s `node-linker=hoisted` may be silently
ignored, breaking the pi-mono dependency-closure postinstall check
(`scripts/verify-pimono-unpack.mjs`) with a confusing "closure package(s) do
not resolve on disk" error. Use `npx pnpm@10 <command>` if your system pnpm
is a different major version — don't downgrade a system-managed pnpm install
for this alone.

## Development Workflow

- **Install**: `pnpm install --frozen-lockfile` (postinstall rebuilds
  `better-sqlite3`, builds Windows-only OCR/audio/automation `.NET` helpers —
  those steps no-op on Linux/macOS dev machines).
- **Run**: `pnpm dev` (electron-vite dev server + Electron). Multiple parallel
  worktrees auto-isolate ports/profiles — see `docs/multi-worktree-dev.md`.
- **Typecheck**: `pnpm typecheck` (`typecheck:node` + `typecheck:web`).
- **Lint**: `pnpm lint` (ESLint; Prettier formatting is non-blocking in CI).
- **Unit tests**: `pnpm test` (vitest, ~550 tests, runs against an Electron
  stub — no real Electron binary needed).
- **Build**: `pnpm build:win` / `pnpm build:mac` / `pnpm build:linux`. Every
  build must pass `--config electron-builder.config.mjs` explicitly (not
  auto-detected — see `docs/release-pipeline.md`) and `--publish never`
  outside the release workflow.
- **Manual E2E / smoke / soak scripts** (`test:e2e:*`, `smoke:*`, `soak*`,
  `orb:*`, `verify:*` in `package.json`): a large surface CI does **not** run —
  these are the maintainer's day-to-day verification toolkit for things CI
  can't reach (live ASR, agent spawning, OAuth flows, Rewind semantics). Specs
  live under `e2e/`. Run the relevant one manually before shipping a change
  in that area; don't assume `pnpm test` alone covers it.

### Linux dev environment (niri / Wayland compositors)

On native Wayland compositors with limited XWayland support (e.g. niri), the
default XWayland path (`ozone-platform=x11`, chosen deliberately for global
shortcuts + active-window support — see `src/main/index.ts`) can fail to map
the main window at all (tray icon appears, window never does). Set
`OMI_OZONE=wayland` to run under native Wayland instead, at the cost of global
shortcuts (push-to-talk / overlay summon) and active-window detection not
working. See `docs/multi-worktree-dev.md`'s environment-overrides table for
this and other dev-only env vars (`OMI_DEV_HW_GPU`, etc.).

`OMI_OZONE=wayland` alone can still leave the main window mapped but blank
(tray works fine) — `pnpm dev`'s software-render default has known
presentation bugs on native Wayland; add `OMI_DEV_HW_GPU=1` alongside it. See
`docs/multi-worktree-dev.md`'s
troubleshooting section for the confirmed repro (Asahi Fedora + niri) and a
second known limitation: the bar and the focus-halo glow window both
position themselves via explicit `setBounds`, which native Wayland ignores,
so they float in the screen center instead of staying parked off-screen —
functional, just misplaced.

## CI

`.github/workflows/desktop-windows-ci.yml` — three jobs, triggered on
`desktop/windows/**` changes:
- **checks** (ubuntu): `pnpm typecheck`, `pnpm lint` (blocking), `pnpm test`.
- **build-windows** (real `windows-latest` runner): builds the native `.NET`
  OCR/UI-automation helpers, rebuilds `better-sqlite3`, runs
  `pnpm build:unpack`. Verifies packaging succeeds; does **not** launch or
  smoke-test the packaged binary at runtime.
- **build-linux** (ubuntu): builds the Linux variant, then actually launches
  it under `xvfb-run` and runs targeted integration tests (OCR helper, Wayland
  degradation) against the real running app — more runtime coverage than the
  Windows job gets today.

## Release Pipeline

Full detail: `docs/release-pipeline.md` (mirrors macOS's auto-release shape in
what it produces; Windows has no external CI, so the same workflow also
builds the NSIS installer on a `windows-latest` runner). Unlike the macOS
workflow, it's **manual only** (`workflow_dispatch`, no `push` trigger) — see
`docs/release-pipeline.md` for tagging, signing, auto-update feed, and public
download link detail.

The version-bump "sync back to main" step is documented as best-effort and can
leave a stale, unmerged PR behind after a release — see issue #10727. If you
hit this, check for an open `chore(windows): sync release v<version> to main`
PR before assuming something else broke.

**Auto-update** (`src/main/updater.ts`, `windowsUpdateFeed.ts`): Windows-only
today (`platform !== 'win32'` gate) — Linux gets no auto-update mechanism at
all, and there's currently no release pipeline publishing Linux builds to
GitHub Releases in the first place. Closing this gap needs both a new Linux
release-publishing workflow and a backend update-feed endpoint mirroring
`/v2/desktop/update-feed/windows` — check for an open tracking issue/PR before
starting this from scratch.

## Docs index

- `docs/release-pipeline.md` — Windows release/tagging/signing/auto-update, in
  depth.
- `docs/bar-gotchas.md` — **read before touching bar window/animation code**:
  the top-edge companion bar has real, non-obvious pathologies (OS show-fade,
  clip-reveal, orb remount blink, eaten hardware clicks).
- `docs/conversation-sync.md` — offline-retry outbox design.
- `docs/multi-worktree-dev.md` — parallel-worktree port/profile isolation, dev
  env var reference.
- `docs/linux-screen-recording.md` — Rewind needs a Wayland desktop portal;
  wlroots compositors (niri, Sway, Hyprland) often ship none configured.
- `docs/perf-invisible-wins.md`, `docs/perf-startup-burst-2026-07-19.md` — perf notes.

## Changelog Entries

Add one fragment under `changelog/unreleased/` for user-visible changes —
follow the existing fragment shape in that directory (`{"changes": [...]}`).
Non-user-visible internal changes don't need one.
