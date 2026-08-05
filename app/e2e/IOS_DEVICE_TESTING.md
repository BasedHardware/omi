# Testing the Omi App on a Physical iPhone (Agent Playbook)

How an AI agent builds, drives, and verifies the Flutter app end-to-end on a real iPhone — no screenshots required, no human at the keyboard except for auth. Written from a real session (2026-07-11, iPhone XR, iOS 18.7.9, app 1.0.543) that smoke-tested PR #9484 on production backend with a signed-in account.

Quick-reference version: [`SKILL.md`](./SKILL.md) → "Setup (iOS physical device)". This file is the full setup + playbook + troubleshooting.

---

## 1. One-time host setup

```bash
# agent-flutter CLI (widget-tree driving over Flutter's Marionette debug protocol)
npm install -g agent-flutter-cli          # provides `agent-flutter`

# marionette MCP server (needed ONLY for enter_text-by-key and rich widget dumps;
# already registered in the repo's .mcp.json → just install the binary)
dart pub global activate marionette_mcp   # installs ~/.pub-cache/bin/marionette_mcp
```

The repo's `.mcp.json` already maps `marionette` to `~/.pub-cache/bin/marionette_mcp`, so Claude Code agents in this repo get the MCP tools (`mcp__marionette__*`) automatically once the binary exists.

Device prerequisites (human, once): iPhone in Developer Mode, cable to the Mac, host trusted, and **screen unlocked for the whole session** (see §7 — iOS kills the debug link when the app backgrounds too long).

## 2. Per-worktree app setup

Use an isolated dev app backed by the production API and the production
Firebase project. This preserves the App Store app while still exercising the
real auth and transcription path. A staging Firebase registration with the
production API fails custom-token exchange with
`firebase_auth/custom-token-mismatch`; an Android Firebase app ID placed in the
iOS options crashes Firebase initialization.

Seed these ignored files from the maintainer's known-good iOS physical-test
fixture (never commit their credentials):

```bash
M=<maintainer-config-source>/app; W=<worktree>/app
cp "$M/.dev.env" "$W/.dev.env"
cp "$M/lib/firebase_options_dev.dart" "$W/lib/firebase_options_dev.dart"
cp "$M/ios/Config/Dev/GoogleService-Info.plist" "$W/ios/Config/Dev/GoogleService-Info.plist"
cp "$M/lib/env/dev_env.g.dart" "$W/lib/env/dev_env.g.dart"
```

Then run the mandatory preflight:

```bash
cd "$W"
scripts/verify_ios_physical_test_auth_config.sh
```

It checks only project/platform metadata and the generated API target; it does
not print credentials. A passing check means the dev flavor has the canonical
`https://api.omi.me/` customer API, a `based-hardware` Firebase project, and an
iOS (not Android) Firebase app registration. It explicitly rejects
`api.omiapi.com`. Signing and the isolated bundle ID remain local maintainer
concerns.

## 3. Launch

```bash
flutter devices                                # get the device id (cable connected, phone unlocked)
cd app && scripts/verify_ios_physical_test_auth_config.sh
flutter run -d <device-id> --flavor dev \
  > /tmp/omi-flutter.log 2>&1 &                # ALWAYS capture stdout — it is the auth token for agent-flutter AND your verification log
# wait for: "A Dart VM Service on <device> is available at: http://127.0.0.1:<port>/<token>/"
```

First build in a worktree ≈ 10 min (pods + Xcode). Incremental relaunches are fast.

**Auth:** if the app boots to onboarding, an agent can drive consent/permission screens, but Sign in with Apple/Google needs the human once (Face ID / device biometrics). Ask, then take over — everything after sign-in is agent-drivable.

### Final unattended handoff is profile/AOT, never debug/JIT

`flutter run` is an attached test session, not the build to leave on the phone
for a drain or day-long dogfood run. A detached debug/JIT build can die later
and its next SpringBoard launch can crash in generated native plugin
registration before Dart starts. That exact failure was observed after about
23 minutes on 2026-08-05.

Before giving the phone back, build and install the signed profile/AOT app over
the same isolated bundle identifier:

```bash
cd app
PROFILE_APP="$(e2e/scripts/build_signed_ios_physical_dev.sh | tail -1)"
e2e/scripts/install_ios_dogfood_profile.sh "$PROFILE_APP"
```

The local-only signing and device identities live in
`~/.config/omi-mobile-test/ios-physical-test.env`; the scripts fail closed when
that ignored config is absent. Never put a personal team ID, signing identity,
provisioning-profile path, or physical device UUID in the repository.

The final installer rejects any Flutter artifact containing the JIT
`kernel_blob.bin`, verifies the physical-test identity, updates in place so
auth/pairing/recordings/sync state survive, and proves a terminate/relaunch
cycle. Do not uninstall to change modes. A successful debug run or detach does
not satisfy the handoff gate.

## 4. Connect and drive

```bash
export AGENT_FLUTTER_LOG=/tmp/omi-flutter.log
agent-flutter connect                          # auto-detects ws URI from the log
```

Primary command palette (all verified on iOS):

| Goal | Command |
|---|---|
| What's on screen (orientation + assertions) | `agent-flutter text` — semantic text dump; **your main tool** |
| Element inventory with bounds | `agent-flutter snapshot -i` (labels are EMPTY on marionette_flutter 0.3.0 — identify by `flutterType` + bounds geometry) |
| Tap by visible text | `agent-flutter find text "Save Memory" press` |
| Tap by ref | `agent-flutter press @e5` (re-snapshot in the SAME shell step — refs go stale between calls) |
| Rich widget properties (controller text, enabled state, keys) | MCP `mcp__marionette__get_interactive_elements` |
| Text entry that actually works | MCP `mcp__marionette__enter_text` with a `ValueKey` (see §6) |
| Screenshot (last resort / human evidence) | `agent-flutter screenshot /tmp/x.png` — path **must** be under `/tmp` |

Navigation facts and the current screen map live in [`SKILL.md`](./SKILL.md) — notably: chat opens from the **"Ask Omi anything…" input bar on home**, not a nav tab; back is the **in-app top-left IconButton** (`agent-flutter back` is adb/Android-only).

## 5. Verify like an agent (no screenshots)

Three assertion channels, use all of them:

1. **Text presence** — after an action, `agent-flutter text` and check the expected string appeared. e.g. pressing an AI message's copy button must surface `"✨ Message copied to clipboard"`; saving a memory must make its text appear in the list dump. This is stronger than a screenshot: nothing has to eyeball it.
2. **The run log** — `grep -iE 'exception|error' /tmp/omi-flutter.log` after every flow, and read the tail to confirm the action actually fired (an API call you expected, or its absence proving a tap missed). Known-benign: `PlatformException(4001 …)` from Intercom when notifications aren't granted.
3. **Widget properties** — MCP `get_interactive_elements` shows `TextEditingController` contents, button `enabled` state, and `Key:` values. This is how you prove a fill really landed (the CLI can claim success while the field stays empty — §6).

## 6. The escalation ladder (when a target won't respond)

Verified order of attack; stop at the first rung that works:

1. `find text "…" press` — works for real text-bearing widgets; silently hits inert labels sometimes (verify via log/text-dump that something happened).
2. `snapshot -i` → identify by `flutterType` + bounds → `press @ref` in the same step. Geometry knowledge helps: bottom-nav slots at y≈816 / x=20·114·207·300; "Ask Omi" bar y≈756 full-width; per-message action InkWells w≈12–14 at x≈22/54/88/122.
3. **Do NOT bother on iOS**: `press x y` (adb), `back` (adb), `dismiss` (adb), `text --press/--fill` (UIAutomator). They fail with device/adb errors.
4. **ValueKey + hot reload** — the durable fix when a field/button can't be targeted (e.g. keyless `TextField`s where `fill @ref` reports success but the controller stays empty):
   - Add `key: const ValueKey('descriptive_name')` to the widget in source.
   - `mcp__marionette__hot_reload` (ignore a spurious "may need full restart" message if the key then shows up; **open-sheet state survives hot reload**).
   - `mcp__marionette__enter_text {key: descriptive_name, input: …}` / `tap {key: …}`.
   - **Keep the keys** — commit them (`chore(app): add automation keys to …`). AGENTS.md endorses keys on interactive widgets; they're how the next agent avoids this ladder entirely. Existing precedent: `memory_content_field` / `memory_save_button` (PR #9484), 10 more in PR #9543.

## 7. Session hygiene & gotchas

- **Keep the phone unlocked during an attached debug session.** iOS terminates
  the debug link after prolonged backgrounding: `"The OS has terminated the
  Flutter debug connection for being inactive"`. The process may continue
  temporarily, but it is not a standalone handoff and may later die or fail to
  relaunch. Reattach for more debug testing, or install profile/AOT before
  unattended use.
- **Test data**: create-then-delete your own artifacts (e.g. a memory literally named "smoke-test — safe to delete"); never exercise destructive flows on the user's real data. If a leftover survives (session died first), tell the user exactly what to remove.
- **Build side effects**: `flutter run` can dirty `app/ios/Podfile.lock`,
  `app/ios/Flutter/AppFrameworkInfo.plist`, and `app/pubspec.lock`. Restore only
  the mechanical build changes you inspected; do not discard unrelated user
  edits.
- **After the session**: the phone must carry the guarded profile/AOT branch
  build, not the debug/JIT runner. Tell the user which artifact is installed.
  App Store reinstall restores the release binary (data survives).

## 8. Known limitations

- No biometric/OS-dialog control: Sign in with Apple, system permission prompts mid-flow, and Safari OAuth sheets need the human (agent-flutter sees only the Flutter tree).
- XCTest/Appium can fail before a session with `Timed out while enabling
  automation mode` even while the phone is unlocked. Record radio-toggle cases
  as unrun; an app-process outage proves storage recovery but is not evidence
  for the iOS Bluetooth Settings toggle itself.
- Semantic `text` dump is partial — some visual text (image-heavy cards, custom painters) never appears; corroborate with widget-tree types/bounds.
- One session at a time per device; `flutter run` owns the VM Service.
