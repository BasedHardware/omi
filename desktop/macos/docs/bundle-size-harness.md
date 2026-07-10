# Bundle Size Harness

Use this harness to hill-climb macOS app bundle size reductions without relying
on manual Finder inspection.

```bash
cd desktop/macos
./scripts/bundle-size-harness.sh
```

The harness builds a named throwaway bundle (`omi-bundle-size.app` by default),
allows ad-hoc signing only for that named bundle, runs bundle-local Node runtime
smoke checks, and writes:

- `.harness/bundle-size/latest.txt` — human-readable size breakdown
- `.harness/bundle-size/latest.json` — machine-readable byte counts
- `.harness/bundle-size/run.log` — full `run.sh` output

Useful variants:

```bash
OMI_BUNDLE_SIZE_APP_NAME=omi-size-probe ./scripts/bundle-size-harness.sh
OMI_BUNDLE_SIZE_NO_ADHOC=1 ./scripts/bundle-size-harness.sh
OMI_BUNDLE_SIZE_KEEP_APP=1 ./scripts/bundle-size-harness.sh
OMI_BUNDLE_SIZE_BUILD_TIMEOUT_SECONDS=900 ./scripts/bundle-size-harness.sh
```

The app name must start with `omi-`. Do not aim this harness at `Omi`,
`Omi Beta`, or `Omi Dev`. The build timeout covers the full `run.sh` build and
launch wait; raise it on cold machines or when another bundle build is finishing.

Before accepting a size reduction, compare `latest.json` before/after and keep
the runtime smoke checks green. For Node dependency pruning, prefer edits in
`scripts/prepare-agent-runtime.sh` so the developer `node_modules` trees remain
untouched.
