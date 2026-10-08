# iOS native presentation migration

Tracking: [#20426](https://github.com/BasedHardware/omi/issues/20426).
Route coverage and remaining completion checks: [parity ledger](ios-native-ui-parity.md).

## Native preview

Enable `--dart-define=OMI_IOS_SWIFTUI=true` on iOS 16+. The default build and unsupported
systems keep the current complete app. This switch is temporary and must stay until the
remaining feature parity checks are complete. iOS 26+ uses Apple's `GlassEffectContainer`,
`.glassEffect` and `.buttonStyle(.glass)` for controls. Earlier systems use standard native
controls and materials. Reading content stays opaque and text uses the system type ramp.

Home is one SwiftUI screen: device/header actions, authoritative capture status and controls,
recovery notices, recaps, recordings, dated conversations and the bottom controls share the
same layout. Flutter no longer puts a small native list below its own Home header.

The preview has a persistent native `TabView` bar for Home, Tasks, Memories, Apps and
Settings. iOS 26+ supplies its system Liquid Glass appearance; earlier iOS uses the
standard native tab bar. Screens mount on first visit and retain their existing state.
Pushed details cover the root bar and return to the selected tab. Explicit Home/Tasks
navigation and deep links select the corresponding root tab without adding another Home
route. The bar uses the existing account-scoped command bridge, with no separate data owner.

| Area | Native presentation | Existing feature surfaces retained |
|---|---|---|
| Main navigation | System tab bar, localized labels, selected state and lazy retained root screens | Existing pushed routes and backend/provider owners |
| Home and library | Home, dated lists, local recording entry points, gaps, processing, paging, recap browsing, full rich summary/transcript detail, playback/timeline following, guarded title/summary/transcript/speaker editors, calendar/recording sheets and lazy photo zoom/paging/share | Specialized feedback/review sheets and bulk selection |
| Search and People | Recent searches, folders, starred items, scoped results, People search/filters/pinning/confidence/voice samples/cleanup, create/edit/move/delete folder sheets | Advanced search result selection |
| Tasks and Memories | Lists, dated Tasks, search, completion, menus, create/edit forms with explicit Save and discard guard; memory categories, belief collection, device filter and bulk management | List selection, hierarchy/reorder and Mind Map |
| Apps | Catalog, app detail, owner add/edit/confirmation, gallery, Markdown/MCP setup, filters, declared permission disclosures, enable/disable/subscribe actions and guarded review editor | Secure API-key creation/reveal, AI generator and specialized payout screens |
| Settings | Navigation, profile, display/notifications, language, privacy, permissions, recording groups, device settings, plan selection/management, integrations, Apple Health, vocabulary, JSON transcription editor, developer/webhook forms, export progress/cancel, fair-use status, detailed usage/periods/quotas/share, import history/actions, custom transcription setup, phone/cloud storage settings, Offline Sync and task service configuration (Asana/ClickUp/Todoist/Google Tasks) | Existing checkout/OAuth owners, secure developer credentials, wrapped, Shortcuts setup, recording-file detail/storage management and device-specific controls |
| Diagnostics | Connection summaries, live signal and battery charts, day/week choice, disconnect history, export | Same Bluetooth polling and export owners |
| Chat | Transcript/composer, send/retry, follow-up, scoped context, voice waveform/Stop/Send/Retry/Discard, attachment picker/removal/previews and app picker | Structured interactive message inspector and non-image attachment viewers |
| First run | Sign-in actions, consent, name, primary language, acquisition survey, permission rows, guided voice prompts/waveform/review/edit/save receipts, step navigation and completion | Device discovery, interactive pendant setup and knowledge graph |
| Calls | Setup disclosure, country/phone entry, verification status/retry, caller-ID management, contacts/search/permissions, dialer/DTMF, active-call transcript/controls and audio output | Physical call/audio-route verification |
| Confirmations | System alerts, action menus, guarded native input/opt-out sheets | Specialized dialog widgets that have not yet adopted the shared presentation API |

These retained surfaces are explicit parity work, not a completed full-app migration. Keep them
available while moving them screen by screen; removing access to a feature is not a migration.

## Ownership and bridge

`lib/mobile/native_ui/` projects current providers into versioned snapshots. `ios/Runner/NativeUI/`
renders them in `UIHostingController`s inside Flutter platform views with UIKit child-controller
containment. Both Runner targets compile the same renderer.

- `com.omi.native_ui/config`: `isSupported` gates the OS before constructing a native view;
  `present`/`dismissPresentation` own temporary system alerts and SwiftUI input sheets. Explicit
  selection returns validated input to the current Dart owner; cancellation returns no mutation.
- `com.omi.native_ui/home/<view id>`: localized Home/read snapshots and existing read/navigation
  callbacks (`detail`, `open`, `browse`, `refresh`, `loadMore`, capture and chrome actions).
- `com.omi.native_ui/surface/<view id>`: typed lists, forms, chat and charts; `update`/`invalidate`/bounded explicit `captureImage`
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
  controllers; submit/update occurs only after explicit confirmation. Secure key creation/reveal stays with its existing
  credential owner. Export cancellation completes the original abort signal and cleanup; developer URL edits keep the
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

The standalone fixture compiles the production SwiftUI sources and tests native navigation,
locked rows, retry/empty states, session invalidation, large text, reachable Home controls,
rapid editing, chat submission, system confirmations, explicit modal Save, dirty cancellation
and session dismissal. It is a Simulator-only fixture; it has no live account or
backend. The integration test also exercises the actual Flutter platform view and containment.
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
