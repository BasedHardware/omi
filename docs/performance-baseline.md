# Performance baseline — app first render (launcher)

`perf-baseline` measured app first-render `launcherMs` at median **27510**
(spread 30292) against `pageMs` 131. Practically all of that wait was
`run-shell.sh` calling `build-shell.sh` on every launch, whether or not Swift
had changed.

This document records that number, the confirmation on this machine, and the
number after the launcher started skipping an exact-match rebuild. Other
seams `perf-baseline` measured are unchanged by this lane and are not
restated here.

**Before ref (unconditional Swift rebuild):** `2370c524743d`
(`2370c524743d5df911bdb823620bc9cea5fd11e1`), `lane/shell-rebuild-cost`,
tracking `origin/codex/track3-backend-integration`. Same tree as
`perf-baseline`'s `fc4b3a774d` measurement of this seam, plus later trunk
commits that do not change `run-shell.sh`.

**After:** this commit on `lane/shell-rebuild-cost`. `run-shell.sh` skips
`build-shell.sh` only when `Contents/Resources/omi-build-stamp.json` agrees
with the current working tree (provenance `treeHash`, no mtimes) **and** the
sha256 of `OMI_SURFACES_DIST` equals the sha256 of
`Contents/Resources/surface/`. Anything else rebuilds. `build-shell.sh`
itself is unchanged — L1–L4 still compile exactly as they did.

**Machine:** Apple M5 Max, Darwin 25.6.0 arm64. David's daily app stayed on
4851/8788/5290 and was not stopped. Measurements used a private
`OMI_BUILD_DIR` and verification origin **15290**.

**Load during confirmation / after timings:** quieter than `perf-baseline`'s
UI batch (that run's loadavg was 32.12 / 16.1 / 12.08). A quieter machine
makes the *rebuild* cheaper; it does not make an unconditional rebuild a
cache hit. Cold vs warm below are labeled.

**N = 5.** Median is the middle sample after sorting. Spread is max − min.
Units are milliseconds. Samples are listed in run order.

---

## Before — unconditional rebuild (confirms `perf-baseline`)

`perf-baseline` (`fc4b3a774d`), already-built bundle, `dev-run-macos.sh`
including Swift rebuild + spawn + probe:

| Clock | N | Median | Min | Max | Spread | Samples |
|---|---:|---:|---:|---:|---:|---|
| pageMs (user-felt) | 5 | 131 | 109 | 198 | 89 | 129, 137, 131, 109, 198 |
| launcherMs (includes Swift rebuild) | 5 | 27510 | 21351 | 51643 | 30292 | 21351, 22478, 51643, 27510, 34131 |

Confirmation at `2370c524743d`, same protocol's rebuild core
(`build-shell.sh` / `run-shell.sh` to HTTP ready on 15290). David's ports
untouched. The shape reproduced: **every warm launch still compiled**, even
though the `.app` already existed.

| Kind | Clock | N | Median | Min | Max | Spread | Samples |
|---|---|---:|---:|---:|---:|---:|---|
| Cold (no `.app` yet) | `build-shell.sh` | 1 | 15929 | 15929 | 15929 | — | 15929 |
| Warm (`.app` exists, still rebuilds) | `build-shell.sh` | 5 | 14924 | 14753 | 15696 | 943 | 14874, 15201, 15696, 14753, 14924 |
| Warm (`.app` exists, still rebuilds) | `run-shell.sh` to ready | 5 | 16775 | 15949 | 18093 | 2144 | 18093, 17401, 16775, 16113, 15949 |

Warm ≈ cold because there was no skip: `swiftc` ran every time
(`built:` in every sample). The 15–18s here vs `perf-baseline`'s 27.5s
median is load, not a different mechanism. The defect was the mechanism.

---

## After — skip only on exact input match

Same `run-shell.sh` to HTTP ready on 15290, same private build dir, N = 5
launches after one rebuild that stamped the current tree.

| Kind | Clock | N | Median | Min | Max | Spread | Samples |
|---|---|---:|---:|---:|---:|---:|---|
| Unchanged tree, second+ launch | `run-shell.sh` to ready | 5 | 1356 | 1347 | 1448 | 101 | 1364, 1350, 1347, 1448, 1356 |

Every sample printed `cached:` and did not print `built:`. Median launcher
wait fell from **16775 ms** (this machine, before) / **27510 ms**
(`perf-baseline`) to **1356 ms**.

A needed rebuild still costs a full `swiftc` (Swift-line change: 16060 ms;
surfaces-dist byte change: 16040 ms). That is the correct trade.

---

## What changed

`frontend/shells/macos/scripts/run-shell.sh` used to call `build-shell.sh`
unconditionally. It now asks `scripts/shell-bundle-fresh.mjs`, which reuses
the existing `omi-build-stamp.json` `treeHash` and content-hashes the
surfaces files that `rsync` copies into the bundle. Skip only on an exact
match of both. Direct `build-shell.sh` callers and L3/L4 (fresh
`OMI_BUILD_DIR`) still always compile.
