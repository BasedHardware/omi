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
./scripts/omi-auth-seed.sh com.omi.omi-core-e2e
./scripts/desktop-core-harness.sh --tier 1 --bundle omi-core-e2e --port <PORT>
```

Do **not** mix `omi-auth-seed.sh` (Omi Dev prod session) with `make desktop-run-local` (Auth emulator) — the app will boot unsigned-in.

Linux / CI static gate:

```bash
./desktop/macos/scripts/desktop-core-harness.sh --self-check
```

## Tier ladder

| Tier | Where | Time | Contents | Command |
| --- | --- | --- | --- | --- |
| **T0** | Linux + macOS, CI | <2 min | flow lint, gauntlet `--self-check`, backend desktop contracts | `--tier 0` / `--self-check` |
| **T1** | macOS agent-local | ~5 min | `harness-smoke` + `navigation` on bridge lane | `--tier 1` |
| **T2** | macOS agent-local; **bless tier** | ~15 min | dev-up offline; core matrix flows + spatial overlay swift tests | `--tier 2` |
| **T3** | macOS opt-in | 30+ min | agent continuity gauntlet (live LLM/BYOK) | `--tier 3` |

## Change → tier map

| Change area | Minimum tier |
| --- | --- |
| Transcription / audio capture | T2 |
| ChatProvider / agent runtime | T0 + T3 |
| Sidebar / navigation | T1 |
| Spatial overlay | T1 (`spatial-overlay-harness.sh`) |
| Memories / tasks CRUD surfaces | T2 |
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
| `memories` | v2 | typed bridge | 2 | Navigate + snapshot |
| `tasks` | v2 | typed bridge | 2 | Navigate + snapshot |
| `settings` | v2 | typed bridge | 2 | Settings sections via bridge |
| `dashboard` | v2 | typed bridge | 2 | Dashboard load |
| `chat` | v2 | typed bridge | 2 | Main chat hermetic path |
| `language` | v2 | typed bridge | 2 | Settings transcription section |
| `ask-omi-*-benchmark` | v1 | typed bridge | 3 | Perf benchmarks |
| `desktop-responsiveness-benchmark` | v1 | typed bridge | 3 | Perf |
| `subagent-row-benchmark` | v1 | typed bridge | 3 | Perf |
| `apps` | v2 | manual `do:` | manual | Journey doc for flow-walker |
| `audio-recording` | v2 | manual `do:` | manual | Needs mic permission |
| `refer` | v2 | manual `do:` | manual | |
| `rewind` | v2 | manual `do:` | manual | |
| `screen-recording-permission` | v2 | manual `do:` | manual | TCC-dependent |

Evidence contract: `.harness/desktop-core/<run-id>/{manifest.json, flows/, summary.md}` plus `latest-green` on pass.

## Failure playbook

1. Read `manifest.json` for tier, git SHA, per-flow pass/fail.
2. Read `summary.md` for human summary.
3. For failed flows, open `flows/<name>/` for `omi-harness` step artifacts.
4. T2 hermetic failures: confirm `PROVIDER_MODE=offline`, `OMI_LLM_STUB=1` on Rust backend, bridge `/health`.
5. T3 failures: check LLM credentials / quota; inspect gauntlet evidence under `.harness/agent-continuity-gauntlet/`.

## Hermetic vs live

- **Hermetic (T2):** `make dev-up` with `PROVIDER_MODE=offline`, Rust `OMI_LLM_STUB=1`, bridge transcript seam — no real LLM or mic/STT.
- **Live (T3):** Real provider credentials; agent continuity gauntlet.

See also `desktop/macos/e2e/SKILL.md` and `scripts/dev-harness/`.
