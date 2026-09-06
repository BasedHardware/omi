# v5 production readiness — 2026-09-06

Status: not production ready. The production-readiness goal remains active.

## Verified changes

- `919dadae`: account partition protection, bounded multi-turn chat context, persisted upload acknowledgment and completion guard. Migration 0005 was applied to the local emulator only.
- `77e8cdbbd1`: mobile destination wiring, truthful loading/error states, full loaded conversation list, read-only task presentation, visible recording failure, stale authentication protection and failed-draft recovery.
- `c6004334`: release cache freshness, web dependency resolution, animation cleanup crash fix and viewport-contained navigation.

The branch was pulled from `BasedHardware/omi:v5`, already at `a14c240bec`. Changes remain local; no remote migration, push, merge or deployment occurred. Existing untracked screenshots were preserved.

## Evidence

`bun run setup` completed without dependency changes. `bun run check` passed: 226 React Native tests, 209 Worker contract tests, 33 Workers/D1 integration tests, 33 ratified-contract tests, 40 PWA tests and one C++ boundary test. Formatting, lint, typecheck and the PWA production build passed. Eight existing React Native lint warnings and the web bundle-size warning remain. Worker strict deployment dry-run passed.

The real local Wrangler Worker on 8787 and PWA proxy on 5178 passed 19 HTTP requests covering read routes, invalid inputs, recording creation/upload/completion, repeated completion, rejection of late audio, chat admission/replay/conflict and persisted history. Missing/wrong authorization returned 401; another client could not read the validation chat. The local emulator used actual Durable Objects, D1 and R2 with synthetic test inputs. AI inference is unavailable locally and produced an explicit failed-generation event.

Browser checks at 390×844 and 320×640 exercised settings, memories, return navigation, chat submission, persisted transcript, provider-failure display and composer recovery. After the animation fix, failed generation no longer blanked the app. The mobile settings button stays visible with long device text. Navigation previously extended to 942px in an 844px viewport; it now ends at the viewport boundary (640px in the 320×640 check). This measurement supports the updated static CSS contract test.

Logs: `/tmp/omi-v5-final-acceptance.log`, `/tmp/omi-v5-proxy-smoke-results.json`, `/tmp/omi-v5-proxy-final.log`, `/tmp/omi-v5-local-migrations.log`, `/tmp/v5-backend-audit-tests.log`, `/tmp/v5-backend-audit-dry-run.log`.

## Remaining release blockers

1. Native validation: iOS clean build failed while writing React-Fabric with `errno=28` (disk full). The sequential macOS build never started. This run's failed temporary build output was removed. No physical-device or signed native runtime proof exists for these changes.
2. Backend completeness: canonical memories return `projection_unavailable`; audio is persisted but no transcription pipeline exists. Production identity/entitlement configuration remains staging-oriented. Task mutation and durable audio retry/recovery contracts remain unavailable.
3. Live integration: successful model inference, signed attachment upload/download, authenticated native flows and production service configuration still need end-to-end validation. Emulator failure handling is not successful live inference proof.
4. Rollout: review migration 0005 before remote application. It conservatively marks only nonempty legacy open recordings failed, retaining bytes/metadata and preserving historical completed/failed states. Previously completed recordings are not retroactively verified. Follow `apps/backend-worker/RELEASE.md` for migration evidence and deployment gates.

No new production mocks, TODOs or placeholder implementations were added. Missing services remain explicit blockers.
