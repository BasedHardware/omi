# Load-bearing PostHog events

This is the maintained dictionary for events that drive a product funnel,
reliability or compliance check, or a regression alert. It deliberately does
not inventory every analytics wrapper: most of those events are not
load-bearing, and a generated list of method names would not identify the
product boundary that owns emission.

The **authoritative emitter** below is the state or user-action boundary that
decides whether an event happened. Analytics-manager methods only shape and
send its payload.

## Maintenance contract

- Update this file in the same change when a listed event is renamed, moved,
  starts or stops emitting, changes a listed property/person property, or
  changes alert coverage.
- Add an event when a production funnel, reliability/compliance check, or
  regression alert begins to depend on it. Do not add every analytics method.
- Keep dimensions bounded and content-free. Normalize unknown values to
  `unknown`; never send transcripts, chat text, deletion errors, email, or
  device names in the properties documented here.
- **macOS and Windows are separate surfaces.** Windows has no BLE stack and
  cannot emit pairing, connection, or pendant-session events. Never report a
  blended "desktop" hardware funnel.
- Alert links below point to the checked-in configuration contract. The alerts
  are not live until their PostHog insight/alert links replace that local link;
  creating them is a separate production write.

`device_vendor` is the shared closed dimension:
`omi`, `limitless`, `plaud`, `bee`, `apple`, `fieldlabs`, `friend`,
`neosapien`, `above`, `utami`, `meta`, or `unknown`.

## Connection and purchase funnel

| Event | Owning surface | Emission contract and authoritative emitter | Key properties / person properties | Alert |
|---|---|---|---|---|
| `Connect Device Page Opened` | Flutter mobile (iOS/Android) | Once when the connect-device page initializes: [`ConnectDevicePage.initState`](../../app/lib/pages/capture/connect.dart) | No event or person properties. | Not alerted; funnel denominator for `Get Omi Device Clicked`. |
| `Get Omi Device Clicked` | Flutter mobile (iOS/Android) | Before launching the external Omi store URL: [`openOmiStore`](../../app/lib/pages/capture/connect.dart) | No event or person properties. | [Specified: weekly unique people](posthog-alerts.md#weekly-volume-contract); not yet provisioned. |
| `Permissions Interstitial Shown` | Flutter mobile (fresh-install permissions flow; repaired for Android) | Once per mounted interstitial: [`_PermissionsInterstitialPageState.initState`](../../app/lib/pages/onboarding/permissions/permissions_checker.dart) | No event or person properties. | Not alerted; must be greater than or equal to `Permissions Interstitial Completed` by platform. |
| `Permissions Interstitial Completed` | Flutter mobile (iOS/Android) | When the user completes the permission actions and continues: [`PermissionsInterstitialPage`](../../app/lib/pages/onboarding/permissions/permissions_checker.dart) | No event or person properties. | Not alerted; completion numerator for the shown/completed invariant. |
| `Device Connected` | Flutter mobile BLE (iOS/Android) | Once for each disconnected/different-device → connected transition, regardless of connection path: [`DeviceProvider.setConnectedDevice`](../../app/lib/providers/device_provider.dart) | Event: closed `device_vendor`, enum-name `type`; other legacy device fields are not stable analysis dimensions. Person: `device_vendor`. | Specified: [weekly unique people](posthog-alerts.md#weekly-volume-contract) and [connected/disconnected ratio](posthog-alerts.md#connection-balance-contract); not yet provisioned. |
| `Device Disconnected` | Flutter mobile BLE (iOS/Android) | On the BLE disconnect callback after state cleanup: [`DeviceProvider.onDeviceDisconnected`](../../app/lib/providers/device_provider.dart) | No event or person properties. | [Specified: weekly unique people and connected/disconnected ratio](posthog-alerts.md#connection-balance-contract); not yet provisioned. |
| `Device Paired` | Flutter mobile BLE (iOS/Android) | First successful connection to a `device.id` for the current local `uid`, deduped in local preferences: [`DeviceProvider.setConnectedDevice`](../../app/lib/providers/device_provider.dart) | Event: closed `device_vendor`, enum-name `type`. Person: `has_paired_device=true`, ISO-8601 `first_paired_at`, `device_vendor`. | [Specified: weekly unique people](posthog-alerts.md#weekly-volume-contract); not yet provisioned. |
| `Device Paired` | macOS desktop BLE | After a successful connection, once per new device ID in local preferences; a previously persisted device is seeded so an upgrade/reconnect is not mislabeled as a new pair: [`DeviceProvider.recordPairingAnalytics`](../../desktop/macos/Desktop/Sources/Providers/DeviceProvider.swift) | Event: closed `device_vendor`, enum `device_type`, normalized `model`, boolean `is_first_pair`. Person: `has_paired_device=true`, `paired_device_type`, `device_vendor`, ISO-8601 `first_paired_at` when known. | Same shared weekly alert contract; report macOS separately from mobile. |
| `App Launched` | Windows desktop | Once when the authenticated, onboarded main app shell mounts: [`AppShellInner`](../../desktop/windows/src/renderer/src/App.tsx), through [`trackEvent`](../../desktop/windows/src/renderer/src/lib/analytics.ts) | `$lib=omi-windows`, `$os=Windows`, `platform=windows`, and authenticated `distinct_id`. | Not alerted; Windows session/retention denominator. |
| `Onboarding How Did You Hear` | Windows desktop | When the Windows onboarding source is selected: [`Onboarding.handleHowDidYouHear`](../../desktop/windows/src/renderer/src/pages/Onboarding.tsx), through [`trackHowDidYouHear`](../../desktop/windows/src/renderer/src/lib/analytics.ts) | Event: allowlisted `source`, boolean `is_referral`; every Windows event also carries `$lib=omi-windows`, `$os=Windows`, `platform=windows`, and `distinct_id`. | Not alerted; this is the Windows transport canary. It is not a hardware-conversion event. |
| `Hardware Purchased` | External order-fulfilment system (not present in this repository) | **Not emitted today.** Emit only after fulfilment and email/order identity has been authoritatively reconciled to an Omi `uid`, using the backend's fail-open [`emit_posthog_event`](../../backend/utils/integration_telemetry.py). Checkout intent or a client redirect is not fulfilment. | Planned event: `order_id`, normalized `sku`, `device_vendor=omi`, normalized `channel`, ISO country; `distinct_id=uid`. No person properties. | Not alerted until a real fulfilment emitter exists and has two completed weeks. |

## Reliability and deletion outcomes

`Encoded Audio Duration Measured` is emitted by the live listen receiver at session teardown from authoritative decoded mono PCM bytes and negotiated sample rate. It carries recording/conversation identity, codec, decoded bytes, and audio duration; malformed frames are excluded.

`Speech Positive Duration Measured` is emitted by the live listen receiver at session teardown from the server VAD's cumulative speech clock. It carries recording/conversation identity, seconds, VAD mode, and the closed `server_vad` measurement source.

`Diarization Completed` is emitted after the live transcript loop drains speaker work and durably flushes assignments. It carries recording/conversation identity, distinct STT speaker count, and the closed `stt_provider` source; no labels or transcript content.

| Event | Owning surface | Emission contract and authoritative emitter | Key properties / person properties | Alert |
|---|---|---|---|---|
| `Transcript Started` | Backend `/v4/listen` provider lane | Once, when an Omi-owned live STT attempt receives its first nontrivial audio frame: [`LiveSTTAttempt`](../../backend/utils/observability/transcription.py) | `recording_id`, `conversation_id` when allocated, closed `transcription_source`, bounded `stt_provider`, configured `stt_model`, `transcript_language`, and bounded `app_platform`. `uid` is only the PostHog `distinct_id`. No transcript content. | Not alerted; live transcription denominator. |
| `Transcript Completed` | Backend `/v4/listen` provider lane | Exactly once when a nonempty transcript is successfully delivered to the client WebSocket: [`LiveSTTAttempt.finish`](../../backend/utils/observability/transcription.py) | Start-event fields plus non-negative `duration_seconds` and bounded terminal `phase`. | Not alerted; terminal success and first-transcript latency joined by `recording_id`. |
| `Transcript Failed` | Backend `/v4/listen` provider lane | Exactly once when an accepted live STT attempt terminates on a provider or pipeline failure before successful delivery: [`ListenSessionRuntime._finish_live_transcription`](../../backend/routers/listen/runtime.py) | Start-event fields plus non-negative `duration_seconds` and bounded failure `phase`. Raw provider errors are excluded. | Not alerted; terminal failure numerator joined by `recording_id`. |
| `Transcript Cancelled` | Backend `/v4/listen` provider lane | Exactly once when accepted audio ends normally before any nonempty transcript is delivered: [`ListenSessionRuntime._finish_live_transcription`](../../backend/routers/listen/runtime.py) | Start-event fields plus non-negative `duration_seconds` and `phase=teardown`. | Not alerted; separate from failures so silence/user cancellation does not inflate failure rate. |
| `Speaker Identity Proposed` | Backend `/v4/listen` speaker identification | Once for each speaker-label suggestion sent to the capture client: [`ListenSessionRuntime.emit_speaker_suggestion`](../../backend/routers/listen/runtime.py) | `recording_id`, `conversation_id`, numeric session-local `speaker_id`, booleans `matched_existing_person` and `auto_assign_enabled`, and closed `proposal_source=live_speaker_identification`. Person IDs and names are excluded. | Not alerted; proposal denominator joined to the recording. |
| `Speaker Identity Confirmed` | Backend conversation speaker-assignment mutations | After the updated transcript segments are durably written by the single-segment, whole-speaker, or bulk assignment endpoint: [`conversations.py`](../../backend/routers/conversations.py) | `conversation_id`, closed `confirmation=accepted|corrected`, closed `assignment=self|person|unassigned|mixed`, closed `scope=segment|speaker|bulk`, and `affected_segment_count`. Person IDs, names, and transcript content are excluded. | Not alerted; acceptance/correction numerator joined to its conversation. |
| `Task Extracted` | Backend conversation post-processing | After transcript-derived action items enter the canonical candidate path or are durably written to the legacy projection: [`_save_action_items`](../../backend/utils/conversations/process_conversation.py) | `task_count`, identical `conversation_id` and legacy-compatible `memory_id`, closed `task_source=transcript`, and closed `persistence_path=canonical_candidate|legacy_projection`. No task descriptions. | Not alerted; extracted-task volume joined directly to its source recording. |
| `Task Assignee Corrected` | Backend canonical action-item update | After an action item's `owner` changes and the updated task is read back successfully: [`update_action_item`](../../backend/routers/action_items.py) | `action_item_id`, `conversation_id` when present, closed `previous_assignee` and `new_assignee` (`user|other|unknown`), and `field_changed=owner`. No task description. | Not alerted; task-assignee correction volume. |
| `Device Session Ended` | Flutter mobile BLE (iOS/Android) | When `setConnectedDevice(null)` closes a session that has a recorded start: [`DeviceProvider.setConnectedDevice`](../../app/lib/providers/device_provider.dart) | Native `duration_seconds`, bounded `reason`, and raw `hci_reason_code` when available; local duration/`unknown` fallback; closed `device_vendor`, normalized `model` and `firmware_revision`, `reconnect_attempt_count` (currently `0` because native retry starts after emission). No person properties. | Not alerted; reliability trend segmented by platform/vendor/model/firmware. |
| `Mobile Background Resource Session` | Flutter mobile (iOS/Android) | Once on foreground resume after at least 60 seconds backgrounded: [`BackgroundResourceTelemetry`](../../app/lib/utils/analytics/background_resource_telemetry.dart), with lifecycle ownership in [`HomePage`](../../app/lib/pages/home/page.dart) | Opaque `background_session_id`; duration; start/end recording state, connected booleans, and enum device type; batch/foreground-task booleans; Dart BLE/WebSocket byte deltas and rates; iOS native offline-writer byte/packet totals for the same background window; bounded BLE disconnect, timeout, fail-to-connect, reconnect, and history-saturation diagnostics. No device ID/name, audio, transcript, or location. | Not yet alerted; root-cause dataset for elevated iOS background energy reports. |
| `Delete Account Confirmed` | Flutter mobile and macOS desktop | User confirms deletion, before the backend wipe: [`DeleteAccountPage`](../../app/lib/pages/settings/delete_account.dart) and [`SettingsContentView`](../../desktop/macos/Desktop/Sources/MainWindow/Pages/Settings/Components/SettingsContentView+SettingsUpdates.swift) | No event or person properties. | Not alerted; intent denominator only. It is not proof that the wipe completed. |
| `Account Deletion Wipe Completed` | Backend account-deletion worker | Only after required derived-data deletion and authoritative Firestore deletion succeed; completion-status persistence is then attempted: [`background_wipe_user_data`](../../backend/services/users/account_deletion.py) | `duration_seconds`, `vectors_deleted`, `recordings_deleted`, required/best-effort failure counts, bounded operation names in `failed_operations`. No `uid` property beyond PostHog `distinct_id`. | [Specified: weekly unique people](posthog-alerts.md#weekly-volume-contract); not yet provisioned. |
| `Account Deletion Wipe Failed` | Backend account-deletion worker/reconciler | On a wipe exception and when the reconciler claims a stale `running` wipe: [`background_wipe_user_data` and `reconcile_pending_deletion_wipes`](../../backend/services/users/account_deletion.py) | Bounded operation names in `failed_operations`, non-negative `retry_count`, boolean `terminal`. No raw error and no `uid` property beyond `distinct_id`. | Not alerted by the weekly volume contract; investigate alongside the completed/confirmed gap. |

## Other regression-alert events

| Event | Owning surface | Emission contract and authoritative emitter | Key properties / person properties | Alert |
|---|---|---|---|---|
| `Sign In Completed` | macOS desktop | After a successful Apple or Firebase-provider sign-in: [`AuthService`](../../desktop/macos/Desktop/Sources/AuthService.swift) | Bounded auth `provider`. No event-level email/name. | [Specified: weekly unique people](posthog-alerts.md#weekly-volume-contract); not yet provisioned. |
| `Memory Created` | Flutter mobile and macOS desktop | After a server conversation/recording is created and reconciled: [`CaptureController`](../../app/lib/services/capture/capture_controller.dart), [`AppState+ListenEvents`](../../desktop/macos/Desktop/Sources/AppState/AppState+ListenEvents.swift), and [`TranscriptionStorage`](../../desktop/macos/Desktop/Sources/Rewind/Core/TranscriptionStorage.swift) | Mobile: bounded `memory_result`, `conversation_source`, language and shape/count fields; macOS: bounded `conversation_source` plus `duration_seconds` when known. No transcript text. | [Specified: weekly unique people](posthog-alerts.md#weekly-volume-contract); not yet provisioned. |
| `Chat Message Sent` | Flutter mobile and macOS desktop | On the user-send boundary: [`MessageProvider`](../../app/lib/providers/message_provider.dart) and the macOS chat surfaces through [`AnalyticsManager.chatMessageSent`](../../desktop/macos/Desktop/Sources/AnalyticsManager.swift) | Message length/count only, attachment/context booleans and counts, bounded source; no message text. No person properties. | [Specified: weekly unique people](posthog-alerts.md#weekly-volume-contract); not yet provisioned. |
| `Upgrade Succeeded` | Flutter mobile | After the subscription purchase/restore result succeeds: [`PlansSheet`](../../app/lib/pages/settings/widgets/plans_sheet.dart) | No event or person properties. | [Specified: weekly unique people](posthog-alerts.md#weekly-volume-contract); not yet provisioned. |

`Conversation Created` is not an Omi PostHog event: both current conversation
emitters retain the historical name `Memory Created`.
