# v5 production readiness — 2026-09-06

Status: not production ready. The production-readiness goal remains active.

## Verified changes

- `919dadae`: account partition protection, bounded multi-turn chat context, persisted upload acknowledgment and completion guard. Migration 0005 was applied to the local emulator only.
- `77e8cdbbd1`: mobile destination wiring, truthful loading/error states, full loaded conversation list, read-only task presentation, visible recording failure, stale authentication protection and failed-draft recovery.
- `c6004334`: release cache freshness, web dependency resolution, animation cleanup crash fix and viewport-contained navigation.

The branch was pulled from `BasedHardware/omi:v5`, already at `a14c240bec`; a final fetch confirms no newer upstream commits. Changes remain local; no remote migration, push, merge or deployment occurred. Existing untracked screenshots were preserved.

## Evidence

`bun run setup` completed; native dependency resolution was subsequently aligned with the hoisted workspace and the pinned CocoaPods version. `bun run check` passed: 237 React Native tests, 210 Worker contract tests, 35 Workers/D1 integration tests, 33 ratified-contract tests, 40 PWA tests and one C++ boundary test, plus native JVM transport, Apple OAuth callback, and real Bun Metro startup regressions. Formatting, lint, typecheck and the PWA production build passed. Eight existing React Native lint warnings and the web bundle-size warning remain. Worker strict deployment dry-run passed.

The real local Wrangler Worker on 8787 and PWA proxy on 5178 passed 19 HTTP requests again after the second pass covering read routes, invalid inputs, recording creation/upload/completion, repeated completion, rejection of late audio, chat admission/replay/conflict and persisted history. Missing/wrong authorization returned 401; another client could not read the validation chat. The local emulator used actual Durable Objects, D1 and R2 with synthetic test inputs. AI inference is unavailable locally and produced an explicit failed-generation event.

Browser checks at 390×844 and 320×640 exercised settings, memories, return navigation, chat submission, persisted transcript, provider-failure display and composer recovery. After the animation fix, failed generation no longer blanked the app. The mobile settings button stays visible with long device text. Navigation previously extended to 942px in an 844px viewport; it now ends at the viewport boundary (640px in the 320×640 check). This measurement supports the updated static CSS contract test.

Logs: `/tmp/omi-v5-readiness-final.log`, `/tmp/omi-v5-pass2-final.log`, `/tmp/omi-v5-pass2-complete-check.log`, `/tmp/omi-v5-pass2-acceptance.log`, `/tmp/omi-v5-macos-pass2.log`, `/tmp/omi-v5-ios-final-build.log`, `/tmp/omi-v5-final-acceptance.log`, `/tmp/omi-v5-proxy-smoke-results.json`, `/tmp/omi-v5-proxy-pass2.log`, `/tmp/omi-v5-proxy-final.log`, `/tmp/omi-v5-local-migrations.log`, `/tmp/v5-backend-audit-tests.log`, `/tmp/v5-backend-audit-dry-run.log`.

## Remaining release blockers

1. Native validation: macOS Debug, iOS arm64 Simulator Debug, and Android arm64 Debug builds pass. Stale CocoaPods metadata and inconsistent native dependency paths are repaired. Windows was not built in this macOS environment. Android still lacks an interactive native authentication module and generation streaming. The Android emulator renders the dashboard and the iOS simulator renders Welcome. macOS renders Welcome and reaches the Google account chooser. Android Nearby devices denial and regrant were exercised; scan registers successfully and returns after its timeout. Account selection/callback completion and physical-device capture remain unverified.
2. Backend completeness: canonical memories return `projection_unavailable`; audio is persisted but no transcription pipeline exists. Production identity/entitlement configuration remains staging-oriented. The ratified task-mutation contract and client adapter exist, but the Worker has no task-write route or account-epoch authority wired to them. Durable audio retry/recovery is also incomplete.
3. Live integration: successful model inference, signed attachment upload/download, authenticated native flows and production service configuration still need end-to-end validation. Emulator failure handling is not successful live inference proof.
4. Rollout: review migration 0005 before remote application. It conservatively marks only nonempty legacy open recordings failed, retaining bytes/metadata and preserving historical completed/failed states. Previously completed recordings are not retroactively verified. Follow `apps/backend-worker/RELEASE.md` for migration evidence and deployment gates.

The second pass fixes simultaneous duplicate chat admissions (the real proxy now returns 200/201 with one generation), rejects timestamps outside the platform Date range, exposes the existing mobile device selection controls, requests Android Bluetooth permissions before native access, and prevents Android authenticated HTTP redirects. iOS now shares the existing native session authority and gates product reads on sign-in. Apple callback validation and Android transport behavior have native regression runners in CI. Pending recording work is retired on sign-out/unmount, with deferred-open/upload regressions preventing cross-session continuation. Real native launch checks also found and repaired missing Android core-module registration, duplicate React Native bundle initialization, Bun Metro startup, and Android status-bar overlap, and missing native scan arguments. Screenshots: `/tmp/omi-v5-ios-welcome.png` and `/tmp/omi-v5-android-insets.png`. These show rendering, not successful authenticated backend integration.

No new production mocks, TODOs or placeholder implementations were added. Missing services remain explicit blockers.
