# iOS native presentation migration

Tracking: [#20426](https://github.com/BasedHardware/omi/issues/20426).

## Stage 1

Home conversation browsing and read-only summary/transcript navigation use SwiftUI on iOS 16+.
The Home header, capture/recovery cards, Daily Recaps and other tabs stay in the current app.
View All opens the complete library, including local recordings, capture gaps, filters and selection.
The detail toolbar opens the current detail page for editing, sharing, audio playback and other actions.
Locked and processing rows also open that page. The existing paywall remains authoritative.

This stage is a personal preview, enabled with `--dart-define=OMI_IOS_SWIFTUI=true`.
The default build keeps the current UI; older iOS versions also use it. Remove this temporary
compile-time switch when the migration and parity checks in #20426 are complete.

## Ownership and bridge

`lib/mobile/native_ui/ios_native_home.dart` projects the current `ConversationProvider` into
version-1 snapshots. `ios/Runner/NativeUI/` renders them in a `UIHostingController` inside a
Flutter platform view, with UIKit child-controller containment. Both Runner targets include it.

- `com.omi.native_ui/config`: `isSupported` checks the OS before constructing the native view.
- `com.omi.native_ui/home/<view id>`: Dart sends `update` and `invalidate`; Swift sends
  `detail`, `open`, `browse`, `refresh` and `loadMore` through the same view-specific channel.
- Snapshots carry localized copy, formatted dates, appearance, groups and list state. Detail reads
  use `ConversationSummarySelection` and `SpeakerNames`, matching the existing reader.
- Native code receives no authentication tokens and creates no backend client, database,
  recording coordinator or persistent conversation cache. Firebase/auth, HTTP, BLE, microphone,
  account-cutover gates and recording ownership continue through their current services.
- Each native surface captures the existing auth-session generation. Read completion and actions
  are fenced to it; sign-out/disposal invalidates the native view. Monotonic revisions reject
  stale updates. Locked content is stripped in Dart and rejected by the native snapshot decoder.
  A deleted or newly locked list row immediately stops displaying a cached native detail.

The presentation contract can also support a Kotlin renderer later. It does not change backend
wire schemas or move shared service ownership into either platform's UI.

## Following stages

1. Complete native Home/library parity: recordings, gaps, recaps, search/filter/selection and detail actions.
2. Migrate Tasks, Memories and Apps, retaining existing mutations and entitlement checks.
3. Migrate Settings and account/device surfaces, including diagnostics and permissions.
4. Migrate chat, onboarding and remaining flows; audit accessibility, localization and lifecycle parity.
5. Remove the preview switch after production readiness. Begin Android Kotlin presentation separately.

## Verification

```sh
flutter test test/mobile/native_ui test/parity/conversation_summary_selection_test.dart
ruby ios/test/native_home_contract_test.rb
```

The shared fixture is `test/fixtures/native_home_v1.json`. The Swift test compiles the production
decoder and checks version/identity validation, revision ordering, appearance and locked-content
rejection. Dart tests exercise session changes during pending reads and the actual redacted projection.
Compile the SwiftUI renderer with the iOS SDK and verify navigation, text selection, dark/light/system,
large text and VoiceOver before promoting the preview into the default app.
