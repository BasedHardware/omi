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

The app builds fine from any git worktree, but `app/test.sh`'s bootstrap seeds **dev-placeholder** Firebase/env files that point at the wrong project for prod flavor. Before a `--flavor prod` build in a fresh worktree, copy the real config from the primary checkout:

```bash
M=<primary-checkout>/app; W=<worktree>/app
cp $M/.env $W/.env
cp $M/lib/firebase_options_prod.dart $W/lib/firebase_options_prod.dart
cp $M/ios/Config/Prod/GoogleService-Info.plist $W/ios/Config/Prod/GoogleService-Info.plist
cp $M/lib/env/prod_env.g.dart $W/lib/env/prod_env.g.dart   # or rerun build_runner after copying .env
```

**Which flavor:** prefer `prod` on a physical device. The dev flavor's bundle id may have no usable provisioning profile in a fresh worktree — it fails with `Provisioning profile "iOS Team Provisioning Profile: *" doesn't support the App Groups capability`. Prod uses the routinely-provisioned profile. Note: a prod build **replaces the App Store app** on the phone (same bundle id; data/keychain survive, but reinstall from the App Store afterwards if the user wants the signed release back).

## 3. Launch

```bash
flutter devices                                # get the device id (cable connected, phone unlocked)
cd app && flutter run -d <device-id> --flavor prod \
  > /tmp/omi-flutter.log 2>&1 &                # ALWAYS capture stdout — it is the auth token for agent-flutter AND your verification log
# wait for: "A Dart VM Service on <device> is available at: http://127.0.0.1:<port>/<token>/"
```

First build in a worktree ≈ 10 min (pods + Xcode). Incremental relaunches are fast.

**Auth:** if the app boots to onboarding, an agent can drive consent/permission screens, but Sign in with Apple/Google needs the human once (Face ID / device biometrics). Ask, then take over — everything after sign-in is agent-drivable.

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

- **Keep the phone unlocked.** iOS terminates the debug link after prolonged backgrounding: `"The OS has terminated the Flutter debug connection for being inactive"` — the app keeps running but you must relaunch `flutter run` to reattach. This is a session-ender if you're mid-flow; check the phone before long code-reading pauses.
- **Test data**: create-then-delete your own artifacts (e.g. a memory literally named "smoke-test — safe to delete"); never exercise destructive flows on the user's real data. If a leftover survives (session died first), tell the user exactly what to remove.
- **Build side effects**: `flutter run` dirties `app/ios/Flutter/AppFrameworkInfo.plist` and sometimes `app/pubspec.lock` — `git checkout --` them before committing anything.
- **After the session**: the phone carries your branch build. Tell the user; App Store reinstall restores the release binary (data survives).

## 8. Known limitations

- No biometric/OS-dialog control: Sign in with Apple, system permission prompts mid-flow, and Safari OAuth sheets need the human (agent-flutter sees only the Flutter tree).
- Semantic `text` dump is partial — some visual text (image-heavy cards, custom painters) never appears; corroborate with widget-tree types/bounds.
- One session at a time per device; `flutter run` owns the VM Service.
