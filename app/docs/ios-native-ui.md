# iOS native presentation migration

Tracking: [#20426](https://github.com/BasedHardware/omi/issues/20426).

## Native preview

Enable `--dart-define=OMI_IOS_SWIFTUI=true` on iOS 16+. The default build and unsupported
systems keep the current complete app. This switch is temporary and must stay until the
remaining feature parity checks are complete. iOS 26+ uses Apple's `GlassEffectContainer`,
`.glassEffect` and `.buttonStyle(.glass)` for controls. Earlier systems use standard native
controls and materials. Reading content stays opaque and text uses the system type ramp.

Home is one SwiftUI screen: device/header actions, authoritative capture status and controls,
recovery notices, recaps, recordings, dated conversations and the bottom controls share the
same layout. Flutter no longer puts a small native list below its own Home header.

| Area | Native presentation | Existing feature surfaces retained |
|---|---|---|
| Home and library | Home, dated lists, local recording entry points, gaps, processing, paging, recap browsing, summary/transcript reader | Recording playback, detailed edits and bulk selection |
| Search | Recent searches, folders, starred items, scoped results, conversations/tasks/memories/recaps | People management and advanced folder sheets |
| Tasks and Memories | Lists, search, completion, menus, create/edit forms with explicit Save and discard guard | Bulk selection, hierarchy/reorder, memory management and Mind Map |
| Apps | Catalog lists, search and filters | App detail, integration setup and specialized filters |
| Settings | Navigation, profile, display/notifications, language, privacy, permissions, recording groups, device settings | Billing, custom transcription, integration/developer tools, native Shortcuts setup and device-specific controls |
| Diagnostics | Connection summaries, live signal and battery charts, day/week choice, disconnect history, export | Same Bluetooth polling and export owners |
| Chat | Transcript, native draft/composer, send/retry, follow-up, scoped context | Voice/attachments, structured interactive message inspector and app picker |
| First run | Sign-in actions, consent, name and primary language | Step navigation, device discovery, guided voice, permissions and completion |

These retained surfaces are explicit parity work, not a completed full-app migration. Keep them
available while moving them screen by screen; removing access to a feature is not a migration.

## Ownership and bridge

`lib/mobile/native_ui/` projects current providers into versioned snapshots. `ios/Runner/NativeUI/`
renders them in `UIHostingController`s inside Flutter platform views with UIKit child-controller
containment. Both Runner targets compile the same renderer.

- `com.omi.native_ui/config`: `isSupported` gates the OS before constructing a native view.
- `com.omi.native_ui/home/<view id>`: localized Home/read snapshots and existing read/navigation
  callbacks (`detail`, `open`, `browse`, `refresh`, `loadMore`, capture and chrome actions).
- `com.omi.native_ui/surface/<view id>`: typed lists, forms, chat and charts; `update`/`invalidate`
  and a whitelisted `action` command. Callbacks stay in Dart with their existing owner.
- Native code receives no tokens and adds no backend client, database, recording coordinator or
  persistent conversation cache. Auth/Firebase, HTTP, BLE, microphone, recovery, subscription
  checks, mutations and undo continue through current services and their existing contracts.
- Each native surface captures the auth-session generation. Read completion and commands are
  fenced to it; sign-out/disposal clears native state. Monotonic revisions reject stale updates.
  Locked content is stripped before crossing the bridge. Unknown controls or invalid legacy
  picker values retain the entire existing surface.
- IDs and values are validated on both sides. Duplicate identities, nonfinite charts, invalid
  dates and arbitrary mutation payloads are rejected. Rapid text changes keep the final edit;
  Save waits for pending edits and cannot commit after a rejected edit. A successful chat send
  clears its submitted draft without discarding text typed after that submission.
- Copy, dates and speaker names come from the current localization and formatting primitives.
  System/Dark/Light follows `AppearanceProvider`; native code does not store a second choice.

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
rapid editing and chat submission. It is a Simulator-only fixture; it has no live account or
backend. The integration test also exercises the actual Flutter platform view and containment.
`NATIVE_UI_EVIDENCE_DIR` selects the host screenshot directory for the integration driver.

Run the full hermetic Flutter suite, analyzer ratchet, SwiftLint, `mobile-verify fast --all` and
`make preflight` before pushing. Personal phone installs use a signed `Release-prod` AOT build
over the existing identity, preserving data; never uninstall the release app. Verify production
configuration and compare sanitized account, theme, onboarding and pairing state after launch.
