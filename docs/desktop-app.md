# macOS desktop app

The desktop product is the React Native tree (`react-native/`) running under
`react-native-macos` inside a native glass window. React owns all product UI,
routes, state, motion, and lifecycle; Objective-C++ (`react-native/macos/`)
only does window/material bootstrap, traffic-light geometry, credential
transport, desktop commands, and the codec boundary. Guide-level rules:
[`react-native/AGENTS.md`](../react-native/AGENTS.md).

## Entry chain and file map

```
react-native/
  index.js → App.tsx → src/app/AppOrchestrator.tsx   # session, reads, chat orchestration
  src/desktop/
    DesktopApp.tsx            # route state, session gate, chat overlay, theme provider
    DesktopTopChrome.tsx      # v5.1 chrome: DesktopChrome (omnibar + filters + gear)
    DesktopShellV5.tsx,
    DesktopChromeV5.tsx       # v5 pages IA, kept selectable via omi.uiVersion
    desktopChrome.ts          # layout constants, nav/filter labels, motion tokens
    DesktopActivity.tsx       # Home page = unified Activity timeline + filters
    timeline/UnifiedTimeline.tsx  # mergeTimeline + grouping of conversations/memories/tasks/captures
    DesktopRewind.tsx,
    rewindTimeline.ts         # Recall: captured + shipping interleave, groupRewindFrames
    DesktopHome.tsx           # Home currents/tasks cards (also exports banner/glance used by Activity)
    DesktopPages.tsx          # Library/Tasks pages (v5 IA; tests import them)
    DesktopChat.tsx, DesktopSettings.tsx, DesktopOnboarding.tsx,
    DesktopRows.tsx, DesktopTheme.tsx, tokens.ts, ScrollFade.tsx,
    ShippingStage.tsx, ShippingPressable.tsx, exploreChecklist.ts,
    PostSetupOverlay.tsx, ConnectionGallery.tsx
  src/ui/                     # shared kit (Pressable, tokens, ChatMessageContent, TaskEditor, …)
  src/app/useRewindCapture.ts # JS side of the capture session lifecycle
  macos/RnRuntime-macOS/
    AppDelegate.mm            # window dressing, traffic lights, permission guide, Cmd+K
    OmiGlassPanelView.mm      # NSVisualEffectView backdrop
    OmiDesktopCommandsModule.mm  # preferences ↔ NSUserDefaults, permission + search commands
    OmiRewindModule.mm + apple/OmiRewindCapture.mm  # capture, JPEG + Vision text, frame store
    OmiAuthModule.mm, OmiBackendModule.mm, OmiNativeModule.mm
  __tests__/macOSNativeBoundary.test.ts  # asserts AppDelegate ↔ desktopChrome contract
```

## Window and glass contract

- The window backdrop is a real behind-window `NSVisualEffectView`
  (`OmiGlassPanelView.mm`, `NSVisualEffectMaterialHUDWindow` dark /
  `UnderWindowBackground` light), including on macOS 26. Do not substitute an
  empty `NSGlassEffectView` behind React content: [Apple's
  guidance](https://developer.apple.com/videos/play/wwdc2025/310/?time=1093)
  puts content inside that glass view rather than using it as a sibling
  backdrop. Backdrop geometry updates without implicit layer animations.
  `scripts/test-apple-auth` covers material bounds, remounting, and Reduce
  Transparency; native rendering still requires verification on a Mac.
- React content stays transparent over the glass in dark mode; light mode
  paints an opaque paper background (a light native glass film reads milky
  under translucent RN surfaces — see `DesktopRoot` in `DesktopApp.tsx`).
- Window dragging is AppKit's `movableByWindowBackground` path: RN pressables
  opt out per-host, so buttons stay clickable while bare areas drag. A
  swizzled hitTest depth guard (`AppDelegate.mm`) survives cyclic view graphs
  after dev bundle reloads.
- `AppDelegate.mm` also: hides the titlebar material, installs a titlebar
  accessory spacer (`OmiChromeRowHeight + OmiWindowInset`), positions traffic
  lights by shifting the whole titlebar container (never individual buttons —
  hover glyphs desync), sizes the window per presentation (app ≥ 800×680,
  onboarding ≥ 640×620, permission guide ≥ 340×420, default 900×700), drives
  the System Settings permission guide, and publishes the Edit → Search
  (Cmd+K) menu item as the `desktopSearchCommand` event
  (`react-native/src/desktopCommands.ts`).

## Chrome layout contract (v5.1 Activity IA)

Implemented across `DesktopTopChrome.tsx` + `desktopChrome.ts`:

- **Row 1** — the omnibar (Ask / Search mode pill, input), with a spacer
  reserving the traffic-light cluster (`desktopTrafficLightRowWidth`), the
  persistent capture toggle, and the settings gear. Capture toggle hides
  while capture is unavailable (`onToggleCapture === null`).
- **Row 2** — Activity filters **All / Conversations / Recall / Tasks**
  (`desktopActivityFilters`, human labels via `desktopFilterLabel` — the
  `recall` filter is labeled "Recall") plus the group-by segmented control
  **Date / Type / Topic** (`desktopTimelineGroupings`). Filters select a
  slice of the Activity page; they are not routes.
- Routes are `'Home' | 'Rewind' | 'Settings'`; **Chat is an overlay, not a
  route** (`DesktopApp.tsx` renders it over the stage so the omnibar that
  feeds it stays visible). `Rewind` is the capture-detail page reached from
  timeline entries or Search.
- The v5 pages IA (rail: Home / Chat / Conversations / Recall / Tasks) is
  kept behind the `omi.uiVersion` preference (`'v5' | 'v5.1'`, default
  `v5.1`): `DesktopShellV5.tsx` + `DesktopChromeV5.tsx`
  (`desktopNavItemsV5`, labels via `desktopNavLabelV5`). Both IAs share the
  same stage components and must both keep working.

### Traffic lights mirror the JS row geometry

`desktopChrome.ts` pins `desktopWindowInset = 12` and
`desktopOmnibarHeight = 44`; `AppDelegate.mm` pins `OmiWindowInset = 12.0` and
`OmiChromeRowHeight = 44.0` and centers the lights on that row. The pair is
asserted by `react-native/__tests__/macOSNativeBoundary.test.ts` (values, the
container-shift implementation, the accessory spacer, click-through). Change
both sides together.

## Timeline and Recall

- `timeline/UnifiedTimeline.tsx` — `mergeTimeline(outcomes, query, captures,
  filter)` flattens conversation, memory, task, and capture projections into
  one normalized feed (epoch seconds vs milliseconds handled per entry),
  bucketed into the Activity filters, with Date / Type / Topic grouping and
  collapsible sections. Failures surface per source; missing sources never
  claim an empty timeline.
- `rewindTimeline.ts` — `groupRewindFrames` collapses consecutive frames of
  the same app + window title into one moment, split when the gap exceeds
  `GROUP_GAP_MS` (12 min) so sleep/stop-start doesn't merge sessions.
  `createRewindTimeline` interleaves the local captured store with old Omi
  history ("shipping"), newest first; auth/owner errors retire the timeline,
  a partial source only warns.
- Capture dedupe: `apple/OmiRewindCapture.mm` skips minting a new timeline
  row when the same app + window title repeats within a 600 s window, so a
  3-second tick over a static window does not duplicate history.

## Recall capture behavior

- The persistent Capture toggle (chrome row 1) and the General screen-capture
  switch control the same session (`useRewindCapture` ↔ `OmiRewindModule`).
  Starting explicitly requests Screen Recording permission; a newly granted
  permission requires relaunch.
- Capture takes one active-window frame at a time, stores JPEG plus local
  Vision fast-recognition text, and continues while navigating the app.
  Stop, sign-out, lock, and sleep retire pending work; capture never resumes
  automatically.
- Password-manager and configured Omi app exclusions apply before capture
  and publication (`OmiRewindCapture.mm`); new captures honor the existing
  retention setting and stop at a 1 GiB storage cap.
- Local Rewind is bound to the existing `based-hardware` Firebase identity;
  a different project's same user ID cannot open its files. Account identity
  and file paths stay native; changing accounts retires old pages and frame
  handles. Semantic embeddings and proactive extraction are out of scope.
- The Recall destination combines this app's captures with the signed-in
  account's existing `Omi/users/<uid>/omi.db` history — read-only, no
  migrations or writes — into one chronological timeline with pagination and
  frame previews. The shared omnibar supplies its text search; there is no
  separate search field or source selector. Recall does not depend on
  selecting Old or New backend. See
  [native-recording-journal.md](native-recording-journal.md) for the
  encrypted journal contract.

## Chat and the omnibar

- The shared omnibar has Ask and Search modes (`OmnibarMode`); Search
  routes to the Recall destination (`'Rewind'`). Ask keeps the
  omnibar in place, answers small asks inline under it, and opens the full
  chat overlay on demand; the close control restores the previous page.
  Enter submits from the omnibar and follows the measured bottom through
  reply layout changes; scrolling away or loading earlier messages pauses
  following until you return to the bottom or send again.
- Assistant Markdown renders with Streamdown on web and React Native Marked
  on native (`src/ui/ChatMessageContent.{tsx,web.tsx}`). Model-authored
  images do not load remotely, raw HTML is inert, and links open only on
  explicit activation. The current native chat transport delivers terminal
  replies; renderer support for incremental Markdown does not imply token
  streaming.
- Omi replies use bubbles; user messages stay unboxed; pending replies show
  a skeleton with the animated Omi dot. The mark and subtle press feedback
  respect Reduce Motion. Scrollable Home, Chat, and Recall content fades
  into the native window glass (`ScrollFade.tsx`) only when more content
  remains below.
- Chat transport errors never take over the stage; they surface under the
  omnibar that owns chat (`visibleChatError` in `desktopChrome.ts`) and only
  once the session is ready.

## Home, Conversations, Settings

- Home is the Activity page: one unified timeline (above). The v5 IA's Home
  shows three tasks and three conversation/memory previews with links to
  their destinations. Home links to Recall instead of claiming capture is
  ready.
- Conversations open shared summary and transcript details; old-backend
  details use the native authenticated conversation endpoint, and locked or
  unavailable transcripts stay explicit. The Conversations filter includes
  loaded memory previews with readable memory details. Pagination uses the
  existing server cursor.
- Desktop onboarding introduces data use before sign-in, offers optional
  permissions without starting capture, and requires explicit setup
  completion. Device connection lives in Settings. First-run explore hints
  (`exploreChecklist.ts`) persist through the `omi.onboarding.exploreProgress`
  preference and are per-IA.
- Settings → General → Backend selects **Old backend** (the existing
  `api.omi.me` account) or **New backend** (the configured v5 origin). The
  same control exists under AI & Automation. Switching persists the
  selection and reloads the workspace; stop an active response first. New
  without a valid configured origin fails as unconfigured rather than
  silently using Old. Account, apps, and privacy controls continue using the
  production Omi API.

## Theme and preferences

- `DesktopTheme.tsx` provides `tokens` (dark/light glass palettes in
  `desktop/tokens.ts`) plus `kit` — the shared `src/ui/tokens.ts` palette
  remapped for light. `src/ui/tokens.ts` itself stays static-dark by design:
  mobile surfaces render without the desktop provider.
- JS preference keys in `src/desktopSettingsClient.ts`
  (`desktopPreferenceKeys`) must stay in sync with the `OmiDesktopDefaultsKey`
  whitelist in `macos/RnRuntime-macOS/OmiDesktopCommandsModule.mm` — 17 keys
  mapping to `NSUserDefaults`, including `omi.backend.softwarePlane`,
  `omi.uiVersion`, `omi.appearance`, `omi.onboarding.exploreProgress`. Add
  both sides or the native snapshot drops the key.

## Build, run, debug (verified recipes)

From `react-native/` unless noted:

```sh
# Metro (status: http://localhost:8081/status)
nohup bun ../scripts/start-metro.ts >> /tmp/omi-metro.log 2>&1 &

# Debug build (~40s incremental)
xcodebuild -workspace macos/RnRuntime.xcworkspace -scheme "RnRuntime-macOS" \
  -configuration Debug \
  -derivedDataPath "$HOME/Library/Developer/Xcode/DerivedData/RnRuntime-edmjpzhjtcykjygsmqbrneqoaoza" \
  CODE_SIGN_STYLE=Automatic CODE_SIGN_IDENTITY="Apple Development" \
  DEVELOPMENT_TEAM=LZ3NL5434Q build
# then launch …/DerivedData/RnRuntime-…/Build/Products/Debug/RnRuntime.app

# Focused tests
cd react-native && bunx jest src/desktop
cd react-native && bunx jest __tests__/macOSNativeBoundary.test.ts
```

- Screenshots: `swift /tmp/winid2.swift` to get the window ID, then
  `screencapture -x -l<WID> out.png` (helper is a local scratch script, not
  committed).
- Bun 1.3.14/1.4 do not invoke Metro's four-argument
  `net.Server.listen(port, host, undefined, callback)` readiness callback;
  `scripts/start-metro.ts` uses the options-object listener instead. Don't
  "fix" it back.
- **Every rebuild resets the macOS Screen Recording TCC grant** — re-grant in
  System Settings after rebuilding, or capture stays unavailable and the
  capture toggle hides.
- More verification: [verification.md](verification.md).
