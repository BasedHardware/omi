# iOS native presentation migration

Tracking: [#20426](https://github.com/BasedHardware/omi/issues/20426).
Route coverage and remaining completion checks: [parity ledger](ios-native-ui-parity.md).

## Native preview

Enable `--dart-define=OMI_IOS_SWIFTUI=true` on iOS 16+. The default build and unsupported
systems keep the current complete app. This switch is temporary and must stay until the
remaining feature parity checks are complete. iOS 26+ uses Apple's `GlassEffectContainer`,
`.glassEffect` and `.buttonStyle(.glass)` for controls. Earlier systems use standard native
controls and materials. Reading content stays opaque and text uses the system type ramp.

Shared presentation rules live in Swift only and use snapshot copy alone: `NativeMetrics` (card
radius matching inset-grouped cells, block radius, 44 pt rows, system-blue accent for selection
marks and tags), centred `NativeEmptyState` (ContentUnavailableView on iOS 17+), one
`NativeSectionHeader` with a View All action for Home's titled sections (one recap fills the row;
several page as a carousel), and `NativeBadge` for a subtitle that is a short all-caps tag. Rich
text uses a heading ramp, secondary list markers, a quote bar and translucent code/table blocks.
Transcript speakers get a stable `NativeSpeakerTint` hue from their label (never purple, INV-UI-1).
Round controls (composer, player, bottom bars, Home footer) are 44 pt `NativeCircleButtonStyle`
circles; a screen's one primary action (Send, play/pause, a stage's Continue, Copy) is the neutral
accent with inverse ink, and plain glass while it cannot act. The chat composer follows Messages
order (attachment menu, a 44 pt capsule field that grows to six lines, Send); the reader player has a
56 pt play/pause. On iOS 26 both sit in `safeAreaBar`, so content gets the system scroll-edge effect.
Modal sheets place Cancel and Save with `.cancellationAction`/`.confirmationAction`. Switches use the
system on-state green, because a white track hides the white knob. Toasts and the activity HUD tint
their glass with their own background so text keeps its contrast over any page; graph labels keep
a faded backing and a 10 pt floor.

Home is one SwiftUI screen: device/header actions, authoritative capture status and controls,
recovery notices, recaps, recordings, dated conversations and the bottom controls share the
same layout. Flutter no longer puts a small native list below its own Home header.

The preview has a persistent native `TabView` bar for Home, Tasks, Memories, Apps and
Settings. iOS 26+ supplies its system Liquid Glass appearance; earlier iOS uses the
standard native tab bar. Screens mount on first visit and retain their existing state.
Pushed details cover the root bar and return to the selected tab. Explicit Home/Tasks
navigation and deep links select the corresponding root tab without adding another Home
route. The bar uses the existing account-scoped command bridge, with no separate data owner.

| Area | Native presentation | Stays classic or owned elsewhere |
|---|---|---|
| Main navigation | System tab bar, localized labels, selected state and lazy retained root screens | |
| Home and capture | Home, capture card, live capture and processing pages, record options/listening and problem sheets, recaps with journey, memories-learned review and stats | Static map images with explicit Maps hand-off (no MapKit tiles); upstream's Review entry and its Review/Recent changes pages |
| Library and search | Dated lists, paging, bulk select/merge/delete/move, row menus, day list, folders, Places map and cluster chooser, recent/starred, scoped search with People and date filter | |
| Conversations | Full summary/transcript reader, playback/timeline following, editors, speaker review and earlier voice matches, feedback/template/visibility/share sheets, test prompt, calendar/recording sheets, photo zoom/paging/share, recording-file detail and local recording sheet | Upstream entity pages |
| People | Search, filters, pinning, confidence, voice samples, cleanup, create/edit/move/delete sheets | |
| Tasks and Goals | Dated Tasks, project grouping, cascade selection with bulk delete/export, indent, reorder, due-date moves, collapsible sections, swipe complete/delete, guarded forms, Goals page/form, accept shared tasks | |
| Memories | Lists with review/use/revert, filters, bulk management, Mind Map card, Memory Graph page with selection/share | |
| Chat | Transcript/composer, voice, attachments, app picker, rich AI replies (Markdown, structured blocks, citations, charts, activity timeline, memory review), feedback and options sheets | Viewers for historical non-image attachments (no stored copy in Flutter or the backend) |
| Apps | Catalog, detail, reviews with star filter/owner reply, app options, capability/category pages, owner add/edit, one-time API keys, AI app generator, payouts and Stripe Connect setup | App web home (WKWebView), Stripe onboarding in the browser |
| Settings | Navigation, profile/name, appearance, notifications, language, privacy with the App Shortcuts link, permissions, assistant voice, conversation timeout, transcription tools/import, usage, plans and leave flows, developer API/MCP keys and debug logs, Wrapped 2025, integrations, task services, Apple Health | Checkout/customer-portal web view, referral web page, dormant training-data opt-in |
| Devices | Discovery/pairing (Apple Watch, Ray-Ban Meta, guides, Bluetooth guidance), device settings with level controls, diagnostics/support, firmware update/OTA/flash, Offline Sync pages, storage sheets and confirmations, synced conversations | |
| First run and prompts | Auth, consent, name, language, acquisition, permissions, guided voice, knowledge graph step, interactive device tutorial, announcements, feature screens, What's New, upgrade/rating prompts, language sheet | Signed-out welcome video |
| Calls | Setup disclosure, phone entry/verification, caller ID, contacts, dialer/DTMF, active-call transcript/controls and audio output | |
| Feedback | System alerts, action menus, input sheets, blocking activity HUD, toasts | Crash and startup-failure screens |

The last column lists what stays classic on purpose: web content and checkout whose navigation
and cookies stay with their WKWebView owners, a branded video, crash/startup fallbacks that must
not depend on the bridge, and system UIs (share sheet, Maps, Intercom, StoreKit review, Shortcuts).
Decorative animations (tutorial demos, Wrapped story paging, shimmer, scanning ripple) are not
reproduced; native screens present the same data and actions, and the animated versions remain in
each classic fallback. Screens merged from upstream after the migration batches (the October 8
Review entry, Review questions, Recent changes and entity pages) still use Flutter, and native Home
does not show the Review entry yet.

## Fallback

- Flag off, Android or iOS below 16: the complete classic app. `isSupported` is checked before a
  native view is constructed, and `NativeFeedbackHost.active` stays false, so feedback stays Flutter.
- A row that fails Dart validation, or a snapshot Swift's decoder rejects (`invalid_native_snapshot`),
  shows the entire classic Flutter screen for that page's lifetime, never a blank or half-native page.
  Unknown controls and invalid legacy picker values do the same.
- `showIosNativeModal` returns null for invalid rows or an unsupported host and the caller shows its
  Flutter dialog; a cancel is a non-null result without an action. `showOmiSheet` keeps the Flutter
  body beside its `nativeBuilder`. A toast, activity or secret sheet the host does not present falls
  back to the Flutter snackbar, spinner or classic sheet.
- Capability rows appear only when the host reports them (`shortcuts_link`); inputs over a bounded
  native editor (JSON above 262,144 text units) keep the complete classic editor.

## Ownership and bridge

`lib/mobile/native_ui/` projects current providers into versioned snapshots. `ios/Runner/NativeUI/`
renders them in `UIHostingController`s inside Flutter platform views with UIKit child-controller
containment. Both Runner targets compile the same renderer.

- `com.omi.native_ui/config`: `isSupported` gates the OS before constructing a native view;
  `present`/`dismissPresentation` own temporary system alerts and SwiftUI input sheets. Explicit
  selection returns validated input to the current Dart owner; cancellation returns no mutation.
  `presentActivity` shows a blocking activity overlay in the same single slot; callers dismiss it
  before awaiting any route or sheet, and it ends on its own after 120 s. Swift reports 'action',
  'cancel' and 'dismissed' itself, and 'programmatic' when it closes a presentation for
  `dismissPresentation`. Dart sends that only for its own reason (a dismissal signal or activity
  dismissal: 'programmatic'; a session change: 'invalidated'; an unmounted caller: 'unmounted') and
  reports that reason in place of Swift's reply.
- `com.omi.native_ui/home/<view id>`: localized Home/read snapshots and existing read/navigation
  callbacks (`detail`, `open`, `browse`, `refresh`, `loadMore`, capture and chrome actions).
- `com.omi.native_ui/surface/<view id>`: typed lists, forms, chat, charts and graphs; `update`/`invalidate`/bounded explicit `captureImage`
  and a whitelisted `action` command. Callbacks stay in Dart with their existing owner.
- Native code receives no app-auth tokens and adds no backend client, database, recording coordinator or
  persistent conversation cache. Auth/Firebase, HTTP, BLE, microphone, recovery, subscription
  checks, mutations and undo continue through current services and their existing contracts.
- Native chat mounts the existing voice widget offstage only when the supported native renderer
  is active, with its animations disabled. Its microphone arbitration, transcription callbacks
  and recoverable files remain with the existing owner; callbacks are fenced to the captured
  account session. Unsupported systems mount only the complete current chat composer.
- Attachment thumbnails use existing HTTPS asset URLs or selected files inside the app's own
  container. Local images are downsampled off the main thread. Picker, upload, removal and
  attachment-send gating stay with `MessageProvider`.
- Native billing projects the existing filtered plan cards, backend price identities, disclosures,
  badges and exact selection handlers. The existing visibility/Continue rules and upgrade,
  cancellation, downgrade, consent and payment owners still apply. It introduces no SKU or price.
- Each native surface captures the auth-session generation. Read completion and commands are
  fenced to it; sign-out/disposal clears native state. Monotonic revisions reject stale updates.
  Locked content is stripped before crossing the bridge. Unknown controls or invalid legacy
  picker values retain the entire existing surface.
- IDs and values are validated on both sides. Duplicate identities, nonfinite charts, invalid
  dates and arbitrary mutation payloads are rejected. Rapid text changes keep the final edit;
  Save waits for pending edits and cannot commit after a rejected edit. A successful chat send
  clears its submitted draft without discarding text typed after that submission.
- Native navigation chrome comes from the current onboarding owner and shares the child's
  SwiftUI screen. An unsupported child restores the complete original step and its navigation.
  Phone setup/caller-ID presentation also keeps the original number parser, input formatters,
  verification polling and confirmed deletion. Text keyboard metadata is a typed allowlist;
  country choices open a searchable native sheet that matches country names, dial codes and
  country IDs. The selected country has its own full-width row above the phone input.
  Entering or selecting a number never starts verification before explicit Continue.
  Calls retain their existing provider and native call engine. Dialer edits never start a call before
  explicit Call; contact selection uses the original number normalization and verified-country
  prefix. DTMF is a typed keypad command with a FIFO queue, never latest-edit coalescing; subsequent
  actions wait for its acknowledgment and a rejected command stops the queue. Dialer zero/erase
  holds exclude their tap actions. Raw call transcript text remains literal, including translations.
  Guided voice actions project the existing action group; microphone, transcription, voice
  enrollment, memory/goal persistence and capture restoration stay with the existing controller.
- Conversation detail mounts the current audio and transcript owners once, offstage with their animations disabled.
  SwiftUI projects their wall-time waveform, missing spans, scrub position, search matches and reader follow state;
  Play/seek/edit commands return to those owners. No second audio player or transcript cache is created.
  Rich summaries preserve headings, lists, task states, quotes, code, links and tables. Transcript text stays literal.
  Links go through a whitelisted callback to the existing Dart URL owner; setup links add account context only there.
  Speaker, title, summary, transcript, calendar and recording actions retain their original save and permission handlers.
- Photo pages lazily load through the existing authenticated loader and cache. Only the current image crosses as a
  temporary sandbox file. Native UIScrollView owns pinch/pan/double-tap zoom; the existing share owner retains its
  file handoff. Session changes and disposal delete temporary presentation images, including late loader completions.
- App-owner metadata/prompts/pricing keep the mounted original forms and validators. Native edits update their existing
  controllers; submit/update occurs only after explicit confirmation. Key creation stays with its existing credential
  owner, which shows the new key once through the secret sheet. Export cancellation completes the original abort signal and cleanup; developer URL edits keep the
  original explicit Save/discard semantics, while existing switches retain immediate persistence.
- Custom transcription keeps the current provider/configuration owner and explicit Save/import/export.
  A replacement key starts in a blank native SecureField; routine snapshots omit the saved key.
  Explicit reveal shows the current draft, and provider changes or Clear withdraw the previous input.
  Explicit JSON configuration editing can contain third-party provider credentials; it is not an
  app-auth channel. Logs remain closed until requested. Native JSON input is capped at 262,144 text units;
  larger configurations restore the complete original editor.
- Usage keeps the existing period/timezone/bucket/quota owners. Explicit Share captures the visible
  native view with size bounds, checks the account generation around asynchronous work, and hands
  watermark/file/share cleanup back to the existing owner. Capture is unavailable after native
  invalidation, detach or account-session change; no native screenshot cache is added.
- Offline Sync uses the same extracted status-priority calculation for native and original cards.
  Retry/cancel/download/import/storage/retention commands continue through the existing owners;
  merely projecting status does not initiate sync or alter recordings.
- List interactions (`NativeSelection`, `bottomBar`, `NativeSection.reorder`/`collapsible`, row `indent` and
  `swipeLeading`/`swipeTrailing`) render in list mode only. `_selection` and `_reorder:<section>` carry the complete
  desired id list, validated against the current projection; owners apply it idempotently, and Swift shows it
  optimistically until a newer snapshot or a refusal. Swipes repeat context-menu options; collapsing is presentation
  only. Owners exit their selection mode when their route pops or is disposed; native code only drops its
  optimistic state on invalidation.
- Toasts: `OmiFeedback` (and `AppSnackbar` through it) sends confirm/info/error/undo/progress requests
  over config `toast` with the same kinds, timings and outcomes. `NativeToastPresenter` shows one at a
  time in a window above sheets and the activity HUD, so Undo stays tappable while other taps reach the
  page. Undo resolves true only for its action; replaced, timed-out, swiped and invalidated toasts do not
  undo. A session change dismisses the toast.
- One-time secrets: `showIosNativeSecretSheet` shows a newly created developer, MCP or app-owner key once,
  in a non-dismissible `sensitive` surface with a single `secret` row (printable ASCII, at most 4,096)
  whose only command is Copy. Sensitive surfaces refuse `captureImage` and modals refuse secret rows; the
  key is never logged, cached or used in an id. Done or a session change closes the sheet.
- Rich chat: `message_ai` rows carry the same rich blocks as `rich_text` (at most 2,000). A link opens
  only when its URL is one of the row's options, which Dart builds from that reply's Markdown and opens
  through the existing URL owner; other URLs are dropped. `chart` rows with `chartStyle` `bar` or `line`
  draw categorical points (index x, finite y, labels up to 64) with thinned axis labels; Usage keeps its
  time-series chart.
- `NativeGraph` (`native_graph.dart`) projects the knowledge graph as a `graph` row: 1-1,024 typed nodes,
  at most 4,096 edges and one fixed user node, as an inert `card` preview or one interactive `fill`
  stage per screen. A SwiftUI Canvas reproduces the Flutter projection, rotation and zoom; selection
  returns a current node id. `captureImage(target:)` renders only a current graph row for the existing
  share owner.
- Capabilities: config `capabilities` reports `shortcuts_link` only from builds compiled with
  `#if compiler(>=6.4)` and AppIntents on iOS 16+. Dart emits the `ShortcutsLink` row only then; without
  it, Data & Privacy keeps its classic page whenever the Shortcuts card applies.
- `level` rows are labelled stepped controls (LED brightness, mic gain, goal progress). Bounds and step
  (at most 1,000 steps) are validated on both sides, the trailing value is Dart's localized label, a drag
  commits once on release (VoiceOver per increment) and a refused value reverts. Playback keeps `slider`.
- Migrated screens keep their owners: recording detail reuses the sync player and sends only waveform
  levels; pairing, firmware and OTA keep their BLE/DFU owners; leave flows keep their typed confirmation
  and billing owners; maps stay Dart-fetched static images. Bundled artwork crosses only as
  `nativeAssetImageUri` copies of `assets/images/` files, never user data.
- Copy, dates and speaker names come from the current localization and formatting primitives.
  System/Dark/Light follows `AppearanceProvider`; native code does not store a second choice.
  The embedded UIKit host applies that choice to its traits too, including live changes and
  returning to System, so Flutter containment cannot leave native controls in the wrong theme.

The presentation contract can support Kotlin later without changing backend wire schemas or
moving service ownership into the platform UI. Android presentation is outside this iOS change.

## Verification

From `app/`:

```sh
flutter test test/mobile/native_ui test/parity/conversation_summary_selection_test.dart
ruby ios/test/native_home_contract_test.rb
ruby ios/test/native_surface_contract_test.rb
flutter drive --driver integration_test/native_ui_host_driver.dart \
  --target integration_test/native_ui_host_test.dart --flavor dev \
  --dart-define=OMI_APP_PROFILE=local_dev --dart-define=OMI_IOS_SWIFTUI=true -d <simulator-id>
xcodebuild -project ios/test/native_ui_preview/Preview.xcodeproj -scheme Preview \
  -destination 'platform=iOS Simulator,id=<simulator-id>' \
  -derivedDataPath ~/Library/Developer/Xcode/DerivedData/omi-native-ui-preview test
```

Each migrated area also has its own host target, `integration_test/native_<area>_host_test.dart`
(21 targets), run with the same driver and defines; their projection and owner tests live in
`test/mobile/native_ui/`.

The standalone fixture compiles the production SwiftUI sources and tests native navigation,
locked rows, retry/empty states, session invalidation, large text, reachable Home controls,
rapid editing, chat submission, system confirmations, explicit modal Save, dirty cancellation,
session dismissal, toasts, activity, secret reveal, list selection/reorder/indent/swipe, rich
replies, charts, graphs and level controls (83 UI tests). It launches with `-ui-test-no-animations`
except for the cases that need animation, and saves review captures in light, dark, right-to-left
and large text. It is a Simulator-only fixture; it has no live account or backend.
The integration test also exercises the actual Flutter platform view and containment.
`NATIVE_UI_EVIDENCE_DIR` selects the host screenshot directory for the integration driver.
The host test opens the actual Settings route, retaining NEW/BETA copy and native navigation,
then checks rendered Dark/Light/System screenshots rather than only snapshot values.
It also opens the real People, folder-edit, memory-management, phone-entry and guided voice
review surfaces, checking native containment and the existing selection/edit owners with inert I/O.
The voice owner and platform view must survive an onboarding-parent rebuild. Phone entry
must preserve international validation and invoke verification only on explicit Continue.
Simulator host tests also compare the current UIKit toolbar IDs with the Dart projection;
that inspection method is absent from physical-device builds and returns no private text.

For synchronized display screenshots, set `NATIVE_UI_SCREENSHOT_PORT` to an unused loopback
port and `NATIVE_UI_SIMULATOR_ID` to the same explicitly selected Simulator ID in the driver
environment, and add `--dart-define=NATIVE_UI_SCREENSHOT_PORT=<port>` to `flutter drive`.
The test-only driver captures CoreSimulator display pixels before the test advances, alongside
the integration plugin's UIKit screenshots. Files ending in `-display.png` are display captures.
Leave the port unset for the ordinary host checks. This seam has no production app endpoint.

Run the full hermetic Flutter suite, analyzer ratchet, SwiftLint, `mobile-verify fast --all` and
`make preflight` before pushing. Personal phone installs use a signed `Release-prod` AOT build
over the existing identity, preserving data; never uninstall the release app. Verify production
configuration and compare sanitized account, theme, onboarding and pairing state after launch.

For a focused advanced-host rerun, add `--dart-define=NATIVE_UI_ADVANCED_ONLY=true`.
`integration_test/native_ui_inspection.dart` is a separate local-dev Debug Simulator entry for
agent-flutter/native accessibility inspection with synthetic Markdown, MCP and image routes.
It never boots a real account or BLE device and refuses non-Debug/non-local-dev builds.

For the focused Settings/Offline Sync host checks, add
`--dart-define=NATIVE_UI_REMAINING_ONLY=true`. The interactive inspection entry also
exposes synthetic import, usage and custom-transcription routes; its saved key is a fixture.
