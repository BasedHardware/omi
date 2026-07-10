# Desktop Core E2E

Tiered desktop confidence ladder built on `dev-harness` (`make dev-up` + `PROVIDER_MODE=offline`), the local automation bridge, and `omi-harness` typed v2 flows.

**Primary entry:** `desktop/macos/scripts/desktop-core-harness.sh`

## Quick start (T1 on macOS)

**Hermetic T2 (recommended — local Auth emulator + offline stack):**

```bash
# 1. Boot local stack (requires Docker for Typesense)
PROVIDER_MODE=offline make dev-up

# 2. Launch named bundle with harness profile (signs in seeded alice user)
make desktop-run-local DESKTOP_APP_NAME=omi-core-e2e DESKTOP_USER=alice
# Note the Automation bridge port printed by run.sh (worktree-specific, not always 47777).

# 3. Run tier 2 in another terminal (use --port from run.sh output)
cd desktop/macos
./scripts/desktop-core-harness.sh --tier 2 --bundle omi-core-e2e --port <PORT> --keep-stack
```

**T1 smoke (navigation only; can use Omi Dev auth seed):**

```bash
cd desktop/macos && OMI_APP_NAME=omi-core-e2e OMI_SKIP_TUNNEL=1 ./run.sh
./scripts/omi-auth-seed.sh com.omi.omi-core-e2e tmp/desktop-auth.json "/Applications/omi-core-e2e.app"
./scripts/desktop-core-harness.sh --tier 1 --bundle omi-core-e2e --port <PORT>
```

**Fault suite (chat backend 5xx — auto-starts `omi-fault-inject` + `omi-fault` bundle):**

```bash
cd desktop/macos
./scripts/desktop-core-harness.sh --fault-suite --port <PORT>
```

Do **not** mix `omi-auth-seed.sh` (Omi Dev prod session) with `make desktop-run-local` (Auth emulator) — the app will boot unsigned-in.

Linux / CI static gate (desktop checks only — backend contracts run in the sibling `contracts` job):

```bash
./desktop/macos/scripts/desktop-core-harness.sh --self-check --skip-backend-contracts
```

Local full T0 (includes backend preflight + pytest desktop contracts):

```bash
./desktop/macos/scripts/desktop-core-harness.sh --self-check
```

## Tier ladder

| Tier | Where | Time | Contents | Command |
| --- | --- | --- | --- | --- |
| **T0** | Linux + macOS, CI | <2 min | flow lint, gauntlet `--self-check`; backend contracts locally or in CI `contracts` job | `--tier 0` / `--self-check` |
| **T1** | macOS agent-local | ~5 min | all flows with `tier: 1` metadata on bridge lane | `--tier 1` |
| **T2** | macOS agent-local; **bless tier** | ~15 min | dev-up offline (enforced); all flows with `tier <= 2` + spatial overlay swift tests | `--tier 2` |
| **Fault** | macOS agent-local | ~5 min | `omi-fault-inject` + `omi-fault` bundle; `chat-fault-5xx.yaml` (backend 5xx → surfaced chat error) | `--fault-suite` |
| **T3** | macOS opt-in | 30+ min | agent continuity gauntlet (live LLM/BYOK) | `--tier 3` |
| **Live P2** | macOS agent-local | varies | `tier: manual` flows — walker / TCC / external URL / destructive gates; **not** bless tier | `omi-harness run e2e/flows/<name>.yaml --lane bridge` |

## Change → tier map

| Change area | Minimum tier |
| --- | --- |
| Transcription / audio capture | T2 |
| ChatProvider / agent runtime | T0 + T3 |
| Sidebar / navigation | T1 |
| Redesigned Home stage (hub/chat/connect) | T2 (`home-stage.yaml`) |
| Spatial overlay | T1 (`spatial-overlay-harness.sh`) |
| Memories / tasks CRUD surfaces | T2 |
| Secondary surfaces (detail, vocabulary, goals, billing, privacy mutations) | T2 + Live P2 for manual-only |
| Rust chat completions / API client | T0 + T1 |
| Release promotion / blessing | T2 bless + gate |

## Flow audit baseline

| Flow | Schema | Runnable | `tier` | Notes |
| --- | --- | --- | --- | --- |
| `harness-smoke` | v1 legacy | typed bridge | 1 | Upgrade to v2 over time |
| `navigation` | v2 | typed bridge | 1 | Sidebar navigation |
| `claude-guidance-overlay` | v2 | typed bridge + visual | 2 | Overlay dogfood |
| `capture-lifecycle` | v2 | typed bridge | 2 | STT seam via `capture_test_transcript` |
| `chat-hermetic` | v2 | typed bridge | 2 | Rust `OMI_LLM_STUB=1` |
| `floating-bar-functional` | v2 | typed bridge | 2 | Ask Omi open + stubbed turn |
| `memories` | v2 | typed bridge | 2 | Navigate + snapshot + search step |
| `tasks` | v2 | typed bridge | 2 | Navigate + snapshot |
| `settings-basic` | v2 | typed bridge | 2 | Settings sections + Advanced snapshot |
| `dashboard` | v2 | typed bridge | 2 | Dashboard load + conversation list snapshot |
| `home-stage` | v2 | typed bridge | 2 | Redesigned Home hub/chat/connect via `homeMode` assertions |
| `chat-fault-5xx` | v2 | typed bridge | fault | Backend 5xx via `omi-fault-inject` (`--fault-suite`) |
| `language` | v2 | typed bridge | 2 | Transcription language set + snapshot |
| `tasks-crud` | v2 | typed bridge | 2 | Task create/toggle/delete via bridge |
| `memory-depth` | v2 | typed bridge | 2 | Memory search, tag filter, visibility toggle |
| `quick-note` | v2 | typed bridge | 2 | Quick Note → Rewind notes |
| `about-settings` | v2 | typed bridge | 2 | About section + version snapshot |
| `notifications-settings` | v2 | typed bridge | 2 | Notifications snapshot + API update |
| `rewind-settings` | v2 | typed bridge | 2 | Rewind retention/excluded-apps snapshot |
| `keyboard-shortcuts` | v2 | typed bridge | 2 | Cmd+1..6 / Cmd+, navigation |
| `memory-graph` | v2 | typed bridge | 2 | Knowledge graph API counts |
| `ai-chat-settings` | v2 | typed bridge | 2 | AI Chat section (non-prod) |
| `conversation-detail` | v2 | typed bridge | 2 | Capture seam + detail/transcript drawer snapshot |
| `memory-crud` | v2 | typed bridge | 2 | Memory create/edit/delete via bridge actions |
| `vocabulary` | v2 | typed bridge | 2 | Transcription vocabulary set + snapshot |
| `goals-dashboard` | v2 | typed bridge | 2 | Dashboard goal create + snapshot |
| `plan-usage` | v2 | typed bridge | 2 | Settings billing subscription snapshot |
| `privacy-settings` | v2 | typed bridge | 2 | Privacy toggle snapshot |
| `apps-marketplace` | v2 | typed bridge | 2 | Apps catalog snapshot |
| `connector-import` | v2 | typed bridge | 2 | `memory_log_import_probe` typed wrap |
| `conversation-folders` | v2 | typed bridge | 2 | Folder create + starred + extended list snapshot |
| `conversation-sharing` | v2 | typed bridge | 2 | Detail open + share link probe (clipboard manual) |
| `speaker-naming` | v2 | typed bridge | 2 | Multi-speaker inject + assign fixture |
| `connector-import-progress` | v2 | manual `do:` | manual | Connector sheet progress persistence |
| `ask-omi-*-benchmark` | v1 | typed bridge | 3 | Perf benchmarks |
| `desktop-responsiveness-benchmark` | v1 | typed bridge | 3 | Perf |
| `subagent-row-benchmark` | v1 | typed bridge | 3 | Perf |
| `apps` | v2 | manual `do:` | manual | Marketplace walker journey |
| `audio-recording` | v2 | manual `do:` | manual | Needs mic permission |
| `refer-external` | v2 | manual `do:` | manual | Profile menu → affiliate URL |
| `delete-account` | v2 | manual `do:` | manual | Confirmation sheet only; never confirm |
| `logout` | v2 | manual bridge | manual | `sign_out` bridge action; local Auth emulator only |
| `onboarding-smoke` | v2 | manual `do:` + bridge | manual | `reset_onboarding`; Wave 7 fix — manual until 2× local green |
| `rewind` | v2 | manual `do:` | manual | |
| `screen-recording-permission` | v2 | manual `do:` | manual | TCC-dependent |

## Secondary surfaces audit

| Surface | Tier | Lane | Mutation depth | Flow / status |
| --- | --- | --- | --- | --- |
| Conversation detail | T2 | bridge | drawer + segments | ✅ `conversation-detail.yaml` |
| Sharing / export | T2 partial | bridge + manual | share link probe; clipboard native manual | ⚠️ `conversation-sharing.yaml` |
| Folders / starring | T2 | bridge | folder create + star | ✅ `conversation-folders.yaml` |
| Speaker naming | T2 | bridge | multi-speaker inject + assign | ✅ `speaker-naming.yaml` |
| Memory CRUD | T2 | bridge | create / edit / delete | ✅ `memory-crud.yaml` |
| Memory depth | T2 | bridge | search / tags / visibility | ✅ `memory-depth.yaml` |
| Memory graph | T2 | bridge | API counts | ✅ `memory-graph.yaml` |
| Vocabulary | T2 | bridge | set terms + snapshot | ✅ `vocabulary.yaml` |
| Goals | T2 | bridge | create goal | ✅ `goals-dashboard.yaml` |
| Privacy toggles | T2 | bridge | toggle snapshot | ✅ `privacy-settings.yaml` |
| Plan / usage | T2 | bridge | read subscription | ✅ `plan-usage.yaml` |
| Apps catalog | T2 + Live P2 | bridge + manual | catalog snapshot + walker | ✅ `apps-marketplace.yaml` / ⚠️ `apps.yaml` |
| Connector import | T2 + Live P2 | bridge + manual | API probe + sheet UI | ✅ `connector-import.yaml` / ⚠️ `connector-import-progress.yaml` |
| Refer external | Live P2 | manual | opens browser | ⚠️ `refer-external.yaml` |
| Delete account | Live P2 | manual | confirm sheet only | ⚠️ `delete-account.yaml` |
| Logout | Live P2 | manual bridge | `sign_out` action | ⚠️ `logout.yaml` (local emulator; stays manual — destructive to session) |
| Onboarding reset | Live P2 | manual + bridge | reset + restart | ⚠️ `onboarding-smoke.yaml` (fix landed; manual gate) |
| Settings depth | T2 | bridge | About / Notifications / Rewind / Shortcuts / Advanced | ✅ dedicated flows + `settings-basic.yaml` |
| AI Chat settings | T2 | bridge | non-prod section snapshot | ✅ `ai-chat-settings.yaml` |

Evidence contract: `.harness/desktop-core/<run-id>/{manifest.json, flows/, summary.md}` plus `latest-green` on pass. T2+ manifests include `provider_mode` (must be `offline` for bless-eligible runs).

## Failure playbook

1. Read `manifest.json` for tier, git SHA, per-flow pass/fail.
2. Read `summary.md` for human summary.
3. For failed flows, open `flows/<name>/` for `omi-harness` step artifacts.
4. T2 hermetic failures: confirm `provider_mode: offline` in `manifest.json`, `PROVIDER_MODE=offline` in dev-harness `config-digest.json`, `OMI_LLM_STUB=1` on Rust backend, bridge `/health`. If a live stack is already up, the harness fails loudly instead of reusing it.
5. **`dev-up failed: Port 8085 for firestore is already in use by a foreign process`:** Another harness instance (or stale Firebase emulator) owns the default ports. Either `make dev-down` on the owning worktree, or set a separate `OMI_INSTANCE` / harness state root before `PROVIDER_MODE=offline make dev-up`. If emulators are healthy but process records are stale, flows can still be blessed manually: launch `make desktop-run-local DESKTOP_APP_NAME=omi-core-e2e DESKTOP_USER=alice`, note the automation port, then run each T2 flow with `python3 scripts/omi-harness run e2e/flows/<name>.yaml --lane bridge --port <PORT>`.
6. T3 failures: check LLM credentials / quota; inspect gauntlet evidence under `.harness/agent-continuity-gauntlet/`.

## Wave 8 bless (2026-07-09)

- **Harness gate:** `desktop-core-harness.sh --tier 2` blocked on `dev-up` port 8085 conflict (foreign Firestore emulator); see playbook item 5.
- **Manual T2 bless:** 32/32 tier-2 flows green via `omi-harness` bridge lane against `omi-core-e2e` on port 47877 (`make desktop-run-local` + seeded `happy_path` scenario).
- **Static gate:** `desktop-core-harness.sh --self-check --skip-backend-contracts` passed; `DesktopAutomationSecondaryActionTests` (17 tests) passed.

## Hermetic vs live

- **Hermetic (T2):** `make dev-up` with `PROVIDER_MODE=offline` (verified via config digest + service health; non-offline stacks abort), Rust `OMI_LLM_STUB=1`, bridge transcript seam — no real LLM or mic/STT.
- **Live P2 (manual):** Walker or hybrid flows for TCC, external URLs, destructive gates, and OAuth-adjacent paths. Not included in bless-tier matrix.
- **Live (T3):** Real provider credentials; agent continuity gauntlet.

Release-candidate agent QA: launch a named bundle, then run
`cd desktop/macos && ./scripts/agent-continuity-gauntlet.sh --suite resilience`
for startup/bad-state bridge and subagent probes. Follow with
`./scripts/agent-continuity-gauntlet.sh --suite all` for the full continuity,
prompt, owner, and resilience pass. Evidence is written under
`.harness/agent-continuity-gauntlet/`.

See also `desktop/macos/e2e/SKILL.md`, `desktop/macos/e2e/feature-vector.md`, and `scripts/dev-harness/`.
