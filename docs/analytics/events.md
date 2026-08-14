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

Every Flutter mobile event is stamped centrally with closed `app_platform` (`ios`, `android`, or `unknown`), semantic `app_version`, and store `app_build`. These canonical fields override conflicting call-site values; PostHog SDK-reserved version fields are not the cross-platform contract.

## Connection and purchase funnel

| Event | Owning surface | Emission contract and authoritative emitter | Key properties / person properties | Alert |
|---|---|---|---|---|
| `Connect Device Page Opened` | Flutter mobile (iOS/Android) | Once when the connect-device page initializes: [`ConnectDevicePage.initState`](../../app/lib/pages/capture/connect.dart) | No event or person properties. | Not alerted; funnel denominator for `Get Omi Device Clicked`. |
| `Get Omi Device Clicked` | Flutter mobile (iOS/Android) | Before launching the external Omi store URL: [`openOmiStore`](../../app/lib/pages/capture/connect.dart) | No event or person properties. | [Specified: weekly unique people](posthog-alerts.md#weekly-volume-contract); not yet provisioned. |
| `Permissions Interstitial Shown` | Flutter mobile (fresh-install permissions flow; repaired for Android) | Once per mounted interstitial: [`_PermissionsInterstitialPageState.initState`](../../app/lib/pages/onboarding/permissions/permissions_checker.dart) | No event or person properties. | Not alerted; must be greater than or equal to `Permissions Interstitial Completed` by platform. |
| `Permissions Interstitial Completed` | Flutter mobile (iOS/Android) | When the user completes the permission actions and continues: [`PermissionsInterstitialPage`](../../app/lib/pages/onboarding/permissions/permissions_checker.dart) | No event or person properties. | Not alerted; completion numerator for the shown/completed invariant. |
| `Device Connected` | Flutter mobile BLE (iOS/Android) | Once for each disconnected/different-device → connected transition, regardless of connection path: [`DeviceProvider.setConnectedDevice`](../../app/lib/providers/device_provider.dart) | Event: closed `device_vendor`, closed `hardware_family`, enum-name `type`; `hardware_id` only when the device exposes a manufacturer serial, with `hardware_id_kind` and `hardware_id_stable`; the BLE `transport_device_id` is explicitly labeled `platform_dependent`. Person: `device_vendor`, `hardware_family`. | Specified: [weekly unique people](posthog-alerts.md#weekly-volume-contract) and [connected/disconnected ratio](posthog-alerts.md#connection-balance-contract); not yet provisioned. |
| `Device Disconnected` | Flutter mobile BLE (iOS/Android) | On the BLE disconnect callback after state cleanup: [`DeviceProvider.onDeviceDisconnected`](../../app/lib/providers/device_provider.dart) | No event or person properties. | [Specified: weekly unique people and connected/disconnected ratio](posthog-alerts.md#connection-balance-contract); not yet provisioned. |
| `Device Paired` | Flutter mobile BLE (iOS/Android) | First successful connection to a `device.id` for the current local `uid`, deduped in local preferences: [`DeviceProvider.setConnectedDevice`](../../app/lib/providers/device_provider.dart) | Event: closed `device_vendor`, closed `hardware_family`, enum-name `type`; `hardware_id` only when the device exposes a manufacturer serial, with `hardware_id_kind` and `hardware_id_stable`; the BLE `transport_device_id` is explicitly labeled `platform_dependent`. Person: `has_paired_device=true`, ISO-8601 `first_paired_at`, `device_vendor`, `hardware_family`. | [Specified: weekly unique people](posthog-alerts.md#weekly-volume-contract); not yet provisioned. |
| `Device Paired` | macOS desktop BLE | After a successful connection, once per new device ID in local preferences; a previously persisted device is seeded so an upgrade/reconnect is not mislabeled as a new pair: [`DeviceProvider.recordPairingAnalytics`](../../desktop/macos/Desktop/Sources/Providers/DeviceProvider.swift) | Event: closed `device_vendor`, enum `device_type`, normalized `model`, boolean `is_first_pair`. Person: `has_paired_device=true`, `paired_device_type`, `device_vendor`, ISO-8601 `first_paired_at` when known. | Same shared weekly alert contract; report macOS separately from mobile. |
| `App Session Started` | Flutter mobile (iOS/Android) | Once at cold launch and once for each background-to-foreground transition; repeated resume callbacks without a background transition are ignored: [`AppSessionTelemetry`](../../app/lib/utils/analytics/app_session_telemetry.dart) | Fresh opaque `app_session_id`; closed `start_kind` (`coldStart` or `foreground`). No person properties. | Not alerted; mobile session/retention denominator. |
| `App Launched` | Windows desktop | Once when the authenticated, onboarded main app shell mounts: [`AppShellInner`](../../desktop/windows/src/renderer/src/App.tsx), through [`trackEvent`](../../desktop/windows/src/renderer/src/lib/analytics.ts) | `$lib=omi-windows`, `$os=Windows`, `platform=windows`, and authenticated `distinct_id`. | Not alerted; Windows session/retention denominator. |
| `Onboarding How Did You Hear` | Windows desktop | When the Windows onboarding source is selected: [`Onboarding.handleHowDidYouHear`](../../desktop/windows/src/renderer/src/pages/Onboarding.tsx), through [`trackHowDidYouHear`](../../desktop/windows/src/renderer/src/lib/analytics.ts) | Event: allowlisted `source`, boolean `is_referral`; every Windows event also carries `$lib=omi-windows`, `$os=Windows`, `platform=windows`, and `distinct_id`. | Not alerted; this is the Windows transport canary. It is not a hardware-conversion event. |
| `Hardware Purchased` | External order-fulfilment system (not present in this repository) | **Not emitted today.** Emit only after fulfilment and email/order identity has been authoritatively reconciled to an Omi `uid`, using the backend's fail-open [`emit_posthog_event`](../../backend/utils/integration_telemetry.py). Checkout intent or a client redirect is not fulfilment. | Planned event: `order_id`, normalized `sku`, `device_vendor=omi`, normalized `channel`, ISO country; `distinct_id=uid`. No person properties. | Not alerted until a real fulfilment emitter exists and has two completed weeks. |

## Reliability and deletion outcomes

| Event | Owning surface | Emission contract and authoritative emitter | Key properties / person properties | Alert |
|---|---|---|---|---|
| `Recording Started` | Flutter mobile capture (phone mic and pendant; live and Transcribe Later) | Exactly once after the native/BLE capture path confirms it started producing audio: [`RecordingLifecycleTelemetry`](../../app/lib/services/capture/recording_lifecycle_telemetry.dart), owned by [`CaptureController`](../../app/lib/services/capture/capture_controller.dart) | Client-minted `recording_id` UUID and closed `recording_source=phone_mic_live|phone_mic_batch|phone_mic_batch_auto|pendant_live|pendant_batch`. Live sessions send the same UUID to `/v4/listen` as `client_conversation_id`, making it the resulting conversation and backend recording-session ID. | Not alerted; denominator for the mobile recording pipeline. |
| `Recording Completed` | Flutter mobile capture | Exactly once when a started phone-mic or pendant capture stops, including controller disposal: [`RecordingLifecycleTelemetry`](../../app/lib/services/capture/recording_lifecycle_telemetry.dart) | Start-event fields plus non-negative `duration_seconds` and closed `reason=user_stopped|device_disconnected|mode_changed|pipeline_closed|unknown`. | Not alerted; terminal completion joined by `recording_id`. |
| `Recording Start Failed` | Flutter mobile capture | Exactly once when an ID was prepared but capture could not start; no `Recording Started` event is emitted for that attempt: [`RecordingLifecycleTelemetry`](../../app/lib/services/capture/recording_lifecycle_telemetry.dart) | `recording_id`, `recording_source`, and closed `failure_class=permission_denied|capture_unavailable|pipeline_unavailable|unknown`. No raw errors. | Not alerted; start-failure numerator joined by `recording_id`. |
| `Device Session Ended` | Flutter mobile BLE (iOS/Android) | When `setConnectedDevice(null)` closes a session that has a recorded start: [`DeviceProvider.setConnectedDevice`](../../app/lib/providers/device_provider.dart) | Native `duration_seconds`, bounded `reason`, and raw `hci_reason_code` when available; local duration/`unknown` fallback; closed `device_vendor`, normalized `model` and `firmware_revision`, `reconnect_attempt_count` (currently `0` because native retry starts after emission). No person properties. | Not alerted; reliability trend segmented by platform/vendor/model/firmware. |
| `Delete Account Confirmed` | Flutter mobile and macOS desktop | User confirms deletion, before the backend wipe: [`DeleteAccountPage`](../../app/lib/pages/settings/delete_account.dart) and [`SettingsContentView`](../../desktop/macos/Desktop/Sources/MainWindow/Pages/Settings/Components/SettingsContentView+SettingsUpdates.swift) | No event or person properties. | Not alerted; intent denominator only. It is not proof that the wipe completed. |
| `Account Deletion Wipe Completed` | Backend account-deletion worker | Only after required derived-data deletion and authoritative Firestore deletion succeed; completion-status persistence is then attempted: [`background_wipe_user_data`](../../backend/services/users/account_deletion.py) | `duration_seconds`, `vectors_deleted`, `recordings_deleted`, required/best-effort failure counts, bounded operation names in `failed_operations`. No `uid` property beyond PostHog `distinct_id`. | [Specified: weekly unique people](posthog-alerts.md#weekly-volume-contract); not yet provisioned. |
| `Account Deletion Wipe Failed` | Backend account-deletion worker/reconciler | On a wipe exception and when the reconciler claims a stale `running` wipe: [`background_wipe_user_data` and `reconcile_pending_deletion_wipes`](../../backend/services/users/account_deletion.py) | Bounded operation names in `failed_operations`, non-negative `retry_count`, boolean `terminal`. No raw error and no `uid` property beyond `distinct_id`. | Not alerted by the weekly volume contract; investigate alongside the completed/confirmed gap. |

## Other regression-alert events

| Event | Owning surface | Emission contract and authoritative emitter | Key properties / person properties | Alert |
|---|---|---|---|---|
| `Sign In Completed` | macOS desktop | After a successful Apple or Firebase-provider sign-in: [`AuthService`](../../desktop/macos/Desktop/Sources/AuthService.swift) | Bounded auth `provider`. No event-level email/name. | [Specified: weekly unique people](posthog-alerts.md#weekly-volume-contract); not yet provisioned. |
| `Account Created` | Flutter mobile OAuth | Once when Firebase's successful credential result authoritatively reports `isNewUser=true`: [`AuthenticationProvider`](../../app/lib/providers/auth_provider.dart) | `is_first_auth=true`, bounded auth provider, and `mobile_oauth` acquisition source. Identify also sets `auth_method`, UTC `user_created_at`, and closed `user_role`. | Not alerted; account acquisition denominator. |
| `Memory Created` | Flutter mobile and macOS desktop | After a server conversation/recording is created and reconciled: [`CaptureController`](../../app/lib/services/capture/capture_controller.dart) and [`AppState+ListenEvents`](../../desktop/macos/Desktop/Sources/AppState/AppState+ListenEvents.swift) | Mobile: bounded `memory_result`, `conversation_source`, language and shape/count fields plus recording hardware type and firmware revision (`not_applicable` for phone); macOS: bounded `source` plus `duration_seconds` when known. No transcript text. | [Specified: weekly unique people](posthog-alerts.md#weekly-volume-contract); not yet provisioned. |
| `Chat Message Sent` | Flutter mobile and macOS desktop | On the user-send boundary: [`MessageProvider`](../../app/lib/providers/message_provider.dart) and the macOS chat surfaces through [`AnalyticsManager.chatMessageSent`](../../desktop/macos/Desktop/Sources/AnalyticsManager.swift) | Message length/count only, attachment/context booleans and counts, bounded source; no message text. No person properties. | [Specified: weekly unique people](posthog-alerts.md#weekly-volume-contract); not yet provisioned. |
| `Upgrade Succeeded` | Flutter mobile | After the subscription purchase/restore result succeeds: [`PlansSheet`](../../app/lib/pages/settings/widgets/plans_sheet.dart) | No event or person properties. | [Specified: weekly unique people](posthog-alerts.md#weekly-volume-contract); not yet provisioned. |
| `Firmware Update Started/Completed/Failed` | Flutter mobile Omi pendant DFU | At the authoritative Nordic DFU or MCU Manager start and terminal callbacks: [`FirmwareMixin`](../../app/lib/pages/home/firmware_mixin.dart) | Opaque attempt ID, closed protocol, from/to firmware versions, and bounded failure class. Native error messages and device IDs are excluded. | Not alerted; firmware reliability funnel. |
| `Subscription Plan Changed` | Flutter mobile | After a reactivation or checkout returns success: [`PlansSheet`](../../app/lib/pages/settings/widgets/plans_sheet.dart) | Closed previous/new plan identifiers, billing interval, and `mobile_checkout` source. | Not alerted; subscription transition analysis. |

Mobile search-completion events (`Search Query Entered`, `Conversation Detail Search Query Entered`, `Fact Searched`, and `Apps Searched`) share the content-free fields `query_length`, `query_word_count`, `results_count`, and closed `search_surface`. Raw query text is never emitted.

`Conversation Created` is not an Omi PostHog event: both current conversation
emitters retain the historical name `Memory Created`.
