# React Native app — Developer Guide

One React Native tree ships every product surface: the macOS desktop app
(`react-native-macos`), iOS, Android, and (via `pwa/`) web. Product UI,
routes, state, motion, and lifecycle orchestration live here — never in the
native shells. Objective-C++/Java/Kotlin only do platform bootstrap, macOS
window/material behavior, credential-bearing transport, desktop commands,
and the codec boundary (see the root [`../AGENTS.md`](../AGENTS.md) rules and
[`../docs/desktop-app.md`](../docs/desktop-app.md) for the macOS contracts).

## Commands

Run from `react-native/` unless noted. Bun for every JS/TS command.

```sh
bun run lint                       # eslint .
bun run typecheck                  # tsc --noEmit (root `bun run build` first)
bunx jest src/desktop              # focused desktop shell suite
bunx jest __tests__                # native-boundary + client suites
bun run test                       # everything (root gate runs --runInBand)

# Metro dev server (status: http://localhost:8081/status)
nohup bun ../scripts/start-metro.ts >> /tmp/omi-metro.log 2>&1 &

# macOS Debug build (~40s incremental), then launch the Debug/RnRuntime.app
xcodebuild -workspace macos/RnRuntime.xcworkspace -scheme "RnRuntime-macOS" \
  -configuration Debug \
  -derivedDataPath "$HOME/Library/Developer/Xcode/DerivedData/RnRuntime-edmjpzhjtcykjygsmqbrneqoaoza" \
  CODE_SIGN_STYLE=Automatic CODE_SIGN_IDENTITY="Apple Development" \
  DEVELOPMENT_TEAM=LZ3NL5434Q build
```

- Screenshots: `swift /tmp/winid2.swift` (local scratch helper) for the
  window ID, then `screencapture -x -l<WID> out.png`.
- `../scripts/start-metro.ts` uses Metro's options-object
  `net.Server.listen` because Bun 1.3.14/1.4 never invoke the four-argument
  `(port, host, undefined, callback)` form. Don't revert it.
- **Every rebuild resets the macOS Screen Recording TCC grant.** Re-grant in
  System Settings before testing capture; the capture toggle hides while
  permission is unavailable.
- iOS Pods live under `ios/`+`macos/` (`Pods/` is never committed). The
  checked-in [`README.md`](README.md) is the untouched CLI template — this
  guide and the docs are authoritative.

## Surface map

```
index.js → App.tsx → src/app/AppOrchestrator.tsx
  src/desktop/   macOS shell (routes, chrome, timeline, settings, rewind)
  src/mobile/    mobile shell (MobileAppSurface, MobileChat, MobileOmnibar)
  src/pages/     shared pages (Conversations, Memories, Tasks, Settings, Connectors)
  src/ui/        shared kit: tokens, Pressable/FocusPressable, ChatTranscript,
                 ChatMessageContent (native: react-native-marked; web: Streamdown),
                 TaskEditor, Composer, OmiMark/OmiLoadingMark
  src/app/       orchestration hooks: useDesktopReads, useTaskMutations,
                 useRewindCapture, useNativeDevices, useOnboarding, routes.ts
```

### Desktop shell (`src/desktop/`)

- **Routes** (`DesktopApp.tsx`): `'Home'` (the Activity page), `'Rewind'`
  (capture detail), `'Settings'`. **Chat is a stage destination (`chatOpen`), not a route** — see `../docs/chat-ux.md`.
- **Chrome layout contract** (`DesktopTopChrome.tsx` + `desktopChrome.ts`):
  row 1 = omnibar with the traffic-light inset spacer, plus capture toggle
  and settings gear; row 2 = Activity filters (All / Conversations / Recall
  / Tasks — `desktopActivityFilters`, labels via `desktopFilterLabel`) and
  the group-by segmented control (Date / Type / Topic —
  `desktopTimelineGroupings`). Conversations and Tasks are filters of the
  Activity page, not pages.
- **Interface versions**: `omi.uiVersion` selects `'v5.1'` (Activity IA,
  default) or `'v5'` (pages rail) — `DesktopShellV5.tsx` +
  `DesktopChromeV5.tsx` (`desktopNavItemsV5`, `desktopNavLabelV5`). Both
  must keep working; they share the same stage components.
- **Traffic lights are virtual.** `AppDelegate.mm` hides the native
  standard-window buttons; `DesktopTrafficLights.tsx` renders the dots inside
  the chrome row's window-controls spacer and routes close/minimize/zoom
  through the native `performWindowCommand` (AppKit `performClose:`,
  `miniaturize:`, `performZoom:`). The reserved geometry lives in
  `desktopChrome.ts` (`desktopWindowInset = 12`, `desktopOmnibarHeight = 44`,
  `desktopTrafficLightButton = 14`, spacing 8, trailing 16) and must equal
  `OmiWindowInset = 12.0` / `OmiChromeRowHeight = 44.0` in
  `macos/RnRuntime-macOS/AppDelegate.mm` (the titlebar accessory spacer).
  Change both files together — `__tests__/macOSNativeBoundary.test.ts`
  asserts the hidden buttons, the command routing, the spacer pair, and the
  quit-after-last-window-close policy.
- **Timeline**: `src/desktop/timeline/UnifiedTimeline.tsx` `mergeTimeline` merges
  conversation/memory/task projections with local capture groups into one
  filterable feed, with Date/Type/Topic grouping and collapsible sections.
  `rewindTimeline.ts` `groupRewindFrames` collapses same-window frames
  (12-minute gap bound); `createRewindTimeline` interleaves the local
  captured store with old Omi history. Native capture dedupe lives in
  `apple/OmiRewindCapture.mm` (600 s same-app+window repeat window).
- **Theme**: `DesktopTheme.tsx` provides glass tokens (`src/desktop/tokens.ts`)
  and remaps the shared kit palette for light; it also mounts the Omi design
  language (`src/design/`, rules in `../docs/design-language.md`). Mobile
  mounts it through `src/mobile/MobileTheme.tsx` (System/Light/Dark).
- **Preferences**: `src/desktopSettingsClient.ts` `desktopPreferenceKeys`
  and the `OmiDesktopDefaultsKey` whitelist in
  `macos/RnRuntime-macOS/OmiDesktopCommandsModule.mm` must stay in sync —
  every JS key needs a native defaults mapping (17 today).

## Test tripwires — do not break

- `src/desktop/DesktopApp.test.tsx` reads these files with `readFileSync`
  (`kitFiles`): **`DesktopApp.tsx`, `DesktopTopChrome.tsx`,
  `DesktopHome.tsx`, `DesktopPages.tsx`, `DesktopRows.tsx`,
  `DesktopSettings.tsx`**. They must continue to exist, and:
  - the strings `accessibilityLabel="Home currents"` and
    `accessibilityLabel="Home tasks"` must stay in the kit sources
    (currently `DesktopHome.tsx`, which also exports the banner/glance
    cards `DesktopActivity.tsx` imports);
  - `DesktopPages.tsx` must keep exporting `TasksPage`/`LibraryPage`
    (`DesktopPages.test.tsx` imports them);
  - forbidden strings: `"I'm ready."`, `Ask a follow-up`,
    `function GlassSurface`, `omnibarError`; required: `ScrollView`,
    `visibleChatError`;
  - chrome assertions: `height: desktopOmnibarHeight`,
    `width: desktopTrafficLightRowWidth`, the filter tablist
    (`accessibilityLabel="Activity filters"`), omnibar input
    `textAlignVertical: 'center'` + `paddingVertical: 6`, `minWidth: 220`;
    the sliding nav pill lives in `DesktopChromeV5.tsx` (`styles.navPill`,
    `placed.current`, `navFrameMoved` with its 0.5 px epsilon);
  - behavior tests assert the filter labels (`Filter All/Conversations/
    Recall/Tasks`, plus `Settings`), the signed-out
    gate (no nav pills, omnibar, Home currents, or Settings until the
    session is ready), and that Settings' Apps gallery never invents
    catalog entries (mocked `loadConnectors`).
- `__tests__/macOSNativeBoundary.test.ts` also pins `AppDelegate.mm`
  word-for-word on the glass window setup, hit-test guards, and drag path.

## Native boundary layer

JS never performs authenticated networking or holds session tokens —
`src/omiNative.ts` (+ `.web`) and `src/native-component.ts` wrap the native
modules; `src/base64.ts` replaces
`atob`/`btoa` (absent in the macOS runtime); transport policy (capture-path
allowlist, timeouts, hostname classes) lives in `native-core/`
([`../native-core/AGENTS.md`](../native-core/AGENTS.md)) and must not be
re-derived in JS. Auth flows and the wire contract:
[`../docs/auth-and-sessions.md`](../docs/auth-and-sessions.md). Mobile
surface behavior: [`../docs/mobile.md`](../docs/mobile.md).
