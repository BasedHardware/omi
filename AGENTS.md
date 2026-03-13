<!-- Synced from CLAUDE.md. When updating agent rules, edit CLAUDE.md first then sync here. -->
<!-- Official guidance: https://developers.openai.com/codex/guides/agents-md | Format spec: https://agents.md
     CLAUDE.md source: https://docs.anthropic.com/en/docs/claude-code/memory -->

# Codex Agent Rules

These rules apply to Codex when working in this repository.

## Setup

- Install pre-commit hook: `ln -s -f ../../scripts/pre-commit .git/hooks/pre-commit`
- Mobile app setup: `cd app && bash setup.sh ios` (or `android`)

## Safety Rules

- Never kill, stop, or restart the production macOS app (`/Applications/omi.app`, bundle id `com.omi.computer-macos`) during local development or testing.
- Development scripts/commands must target only dev app processes (for example `Omi Dev.app` / `com.omi.desktop-dev`), never production.

## Coding Guidelines

### Backend

- No in-function imports. All imports must be at the module top level.
- Follow the module hierarchy when importing. Higher-level modules import from lower-level modules, never the reverse.

Module hierarchy (lowest to highest):
1. `database/`
2. `utils/`
3. `routers/`
4. `main.py`

- Memory management: free large objects immediately after use. E.g., `del` for byte arrays after processing, `.clear()` for dicts/lists holding data.

#### Backend Service Map

```
Shared: Firestore, Redis

backend (main.py)
  ├── ws ──► pusher (pusher/)
  ├── ──────► diarizer (diarizer/)
  ├── ──────► vad (modal/)
  └── ──────► deepgram (self-hosted or cloud)

pusher
  ├── ──────► diarizer (diarizer/)
  └── ──────► deepgram (cloud)

agent-proxy (agent-proxy/main.py)
  └── ws ──► user agent VM (private IP, port 8080)

notifications-job (modal/job.py)  [cron]
```

Helm charts: `backend/charts/{backend-listen,pusher,diarizer,vad,deepgram-self-hosted,agent-proxy}/`

- **backend** (`main.py`) — REST API. Streams audio to pusher via WebSocket (`utils/pusher.py`). Calls diarizer for speaker embeddings (`utils/stt/speaker_embedding.py`). Calls vad for voice activity detection and speaker identification (`utils/stt/vad.py`, `utils/stt/speech_profile.py`). Calls deepgram for STT (`utils/stt/streaming.py`).
- **pusher** (`pusher/main.py`) — Receives audio via binary WebSocket protocol. Calls diarizer and deepgram for speaker sample extraction (`utils/speaker_identification.py` → `utils/speaker_sample.py`).
- **agent-proxy** (`agent-proxy/main.py`) — GKE. WebSocket proxy at `wss://agent.omi.me/v1/agent/ws`. Validates Firebase ID token, looks up `agentVm` in Firestore, proxies bidirectionally to VM's `ws://<ip>:8080/ws`. VM credentials never leave the server.
- **diarizer** (`diarizer/main.py`) — GPU. Speaker embeddings at `/v2/embedding`. Called by backend and pusher (`HOSTED_SPEAKER_EMBEDDING_API_URL`).
- **vad** (`modal/main.py`) — GPU. `/v1/vad` (voice activity detection) and `/v1/speaker-identification` (speaker matching). Called by backend only (`HOSTED_VAD_API_URL`, `HOSTED_SPEECH_PROFILE_API_URL`).
- **deepgram** — STT. Streaming uses self-hosted (`DEEPGRAM_SELF_HOSTED_URL`) or cloud based on `DEEPGRAM_SELF_HOSTED_ENABLED` (`utils/stt/streaming.py`). Pre-recorded always uses Deepgram cloud (`utils/stt/pre_recorded.py`). Called by backend and pusher.
- **notifications-job** (`modal/job.py`) — Cron job, reads Firestore/Redis, sends push notifications.

Keep this map up to date. When adding, removing, or changing inter-service calls, update this section and the matching section in `CLAUDE.md`.

### App (Flutter)

- All user-facing strings must use l10n (`context.l10n.keyName`). Add keys to ARB files using `jq` to avoid reading large files.
- When adding new l10n keys, translate all 33 non-English locales — never leave English text in non-English ARB files. Use `omi-add-missing-language-keys-l10n` skill for translations. Ensure `{parameter}` placeholders match the English ARB exactly.
- After modifying ARB files in `app/lib/l10n/`, regenerate localizations: `cd app && flutter gen-l10n`

#### Verifying UI Changes (agent-flutter)

After any Flutter UI edit, verify programmatically with [agent-flutter](https://github.com/beastoin/agent-flutter). Marionette is already integrated in debug builds. Install once: `npm install -g agent-flutter-cli`.

Edit → Verify → Evidence loop:
1. Edit code, hot restart: `kill -SIGUSR2 $(pgrep -f "flutter run" | head -1)`
2. Connect: `AGENT_FLUTTER_LOG=/tmp/flutter-run.log agent-flutter connect`
3. Verify: `agent-flutter snapshot -i` (see widgets on screen)
4. Interact: `agent-flutter press @e3` / `press 540 1200` (coordinates) / `find type button press` / `fill @e5 "text"` / `dismiss` (system dialogs)
5. Evidence: `agent-flutter screenshot /tmp/evidence.png`

Key rules:
- Must reconnect after every hot restart (kills VM Service session).
- Refs go stale frequently (Flutter rebuilds aggressively) — always re-snapshot before every interaction. Use `press x y` as fallback.
- Use `AGENT_FLUTTER_LOG` pointing to flutter run stdout (not logcat) for auto-detect.
- Prefer `find type X` or `find key "name"` over hardcoded `@ref` for stability.
- When adding interactive widgets, use `Key('descriptive_name')` for agent discoverability.
- App flows & exploration skill: See `app/e2e/SKILL.md` for navigation architecture, widget patterns, and reference flows.
- Full command reference: `agent-flutter schema` or `agent-flutter --help`.

### Desktop (macOS)

#### Verifying UI Changes (agent-swift)

After any Swift UI edit, verify programmatically with [agent-swift](https://github.com/beastoin/agent-swift). No app-side instrumentation needed — uses macOS Accessibility API. Install once: `brew install beastoin/tap/agent-swift`.

Requires: Accessibility permission for Terminal.app (System Settings → Privacy & Security → Accessibility).

Edit → Verify → Evidence loop:
1. Edit code, rebuild: `cd desktop && ./run.sh`
2. Connect: `agent-swift connect --bundle-id com.omi.desktop-dev`
3. Verify: `agent-swift snapshot -i` (interactive elements only)
4. Interact: `agent-swift click @e3` / `fill @e5 "text"` / `find role button click`
5. Assert: `agent-swift is exists @e3` / `wait text "Settings"`
6. Evidence: `agent-swift screenshot /tmp/evidence.png`

Key rules:
- `agent-swift doctor` verifies Accessibility permission and target app.
- Prefer `click` over `press` for SwiftUI — `click` sends CGEvent clicks (triggers NavigationLink), `press` sends AXPress (AppKit only).
- Refs stale after `click`/`press`/`fill`/`scroll` — re-snapshot before next interaction.
- Always use `snapshot -i` — full snapshots of complex apps are very verbose.
- Argument order: `get <property> <ref>`, `is <condition> <ref>`, `wait <condition> [<target>]`, `find <locator> <value>`.
- JSON output: `--json` flag, `AGENT_SWIFT_JSON=1` env var, or pipe to auto-detect.
- 15 commands: `doctor`, `connect`, `disconnect`, `status`, `snapshot`, `press`, `click`, `fill`, `get`, `find`, `screenshot`, `is`, `wait`, `scroll`, `schema`.
- Works with any macOS app (SwiftUI, AppKit, Electron) — zero app-side setup.
- Dev bundle ID: `com.omi.desktop-dev`. Prod: `com.omi.computer-macos`.
- App flows & exploration skill: See `desktop/e2e/SKILL.md` for navigation architecture, interaction patterns, and reference flows.
- Full command reference: `agent-swift --help` or `agent-swift schema`.

## Formatting

Always format code after making changes. The pre-commit hook handles this automatically, but you can also run manually:

- **Dart (app/)**: `dart format --line-length 120 <files>`
  - Files ending in `.gen.dart` or `.g.dart` are auto-generated and should not be formatted manually.
- **Python (backend/)**: `black --line-length 120 --skip-string-normalization <files>`
- **C/C++ (firmware: omi/, omiGlass/)**: `clang-format -i <files>`

## Documentation Maintenance

- Update this file and `CLAUDE.md` in the same commit when rules change.
- For architecture or core flow changes, update Mintlify docs (`docs/doc/developer/`) in the same PR.

## Skills
Available skills for Omi repo work. Use `omi-preflight` as the default entry point — it routes to the right skill.

| Skill | When |
|---|---|
| omi-preflight | Default entry point for any Omi task |
| omi-pr-workflow | Full issue-to-merge flow |
| omi-issue-triage | Score and prioritize issues |
| omi-pr-scan | Audit open PRs (stale drafts, missing tests) |
| omi-pr-review-reviewer | Review PRs as principal engineer |
| omi-pr-review-contributor | Fix review feedback on your PR |
| omi-pr-review-tester | Add tests for PR changes |
| omi-community-pr-review | Review external contributor PRs |
| omi-pr-rescue | Rescue messy PRs (close, re-scope, restart) |
| omi-team-delivery-pipeline | Team delivery: scope lock, queue, assign, execute, verify |
| omi-combined-pr-verifier | Verify 2+ PRs combined in one branch |
| omi-e2e-device-test | Full-stack validation on physical Android device |
| omi-prod-feature-verify | Post-deploy user-facing validation |
| omi-prod-deploy-monitor | Deployment monitoring with fixed cadence |
| omi-dev-gke-deploy-verify | Dev GKE deploy + rollout verification |
| omi-model-eval | A/B eval for model migrations (gpt-5.1 judge) |
| omi-incident-detection | Detect and analyze production incidents |
| omi-deep-rca | Deep root cause analysis with Codex consultation |
| omi-cost-impact-verify | Verify backend cost impact (Deepgram usage) |
| omi-deeplink-verification | Verify deep links, Universal Links, App Links |
| omi-pr-evidence-upload | Upload PR evidence (screenshots, GIFs) to GCS |
| add-a-new-localization-key-l10n-arb | Add l10n keys to ARB files |
| omi-add-missing-language-keys-l10n | Localize hardcoded strings across all locales |
| omi-l10n-weekly-audit | Weekly l10n audit and translation |

## Testing

- Always run tests before committing:
  - Backend changes: run `backend/test.sh`
  - App changes: run `app/test.sh`
- Run `backend/test-preflight.sh` first to verify tools, packages, and env vars are ready.
- Backend unit tests need: `python3`, `pytest`, packages from `requirements.txt`, `ENCRYPTION_SECRET` (set by test.sh).
- Integration tests optionally need: `OPENAI_API_KEY`, `DEEPGRAM_API_KEY`, `ADMIN_KEY`, Redis connectivity, `GOOGLE_APPLICATION_CREDENTIALS`.
