/// `meta_wearables_dat_flutter` is an unofficial Flutter plugin bridging
/// Meta's official iOS and Android Wearables Device Access Toolkit (DAT)
/// SDKs. It is not affiliated with Meta Platforms, Inc.
///
/// Public entry point: [MetaWearablesDat]. All methods on the facade are
/// static; lifecycle is managed by the plugin internally and shared across
/// the entire Flutter engine.
library;

import 'package:meta_wearables_dat_flutter/src/meta_wearables_dat_platform_interface.dart';
import 'package:meta_wearables_dat_flutter/src/models/background_notification.dart';
import 'package:meta_wearables_dat_flutter/src/models/camera_facing.dart';
import 'package:meta_wearables_dat_flutter/src/models/device_compatibility.dart';
import 'package:meta_wearables_dat_flutter/src/models/device_info.dart';
import 'package:meta_wearables_dat_flutter/src/models/device_session_state.dart';
import 'package:meta_wearables_dat_flutter/src/models/display/display_components.dart';
import 'package:meta_wearables_dat_flutter/src/models/display/display_state.dart';
import 'package:meta_wearables_dat_flutter/src/models/frame_data.dart';
import 'package:meta_wearables_dat_flutter/src/models/mock_permission.dart';
import 'package:meta_wearables_dat_flutter/src/models/photo_result.dart';
import 'package:meta_wearables_dat_flutter/src/models/registration_state.dart';
import 'package:meta_wearables_dat_flutter/src/models/stream_quality.dart';
import 'package:meta_wearables_dat_flutter/src/models/stream_session_state.dart';
import 'package:meta_wearables_dat_flutter/src/models/video_frame.dart';
import 'package:meta_wearables_dat_flutter/src/models/video_stream_size.dart';

export 'package:meta_wearables_dat_flutter/src/models/background_notification.dart';
export 'package:meta_wearables_dat_flutter/src/models/camera_facing.dart';
export 'package:meta_wearables_dat_flutter/src/models/dat_error.dart';
export 'package:meta_wearables_dat_flutter/src/models/device_compatibility.dart';
export 'package:meta_wearables_dat_flutter/src/models/device_info.dart';
export 'package:meta_wearables_dat_flutter/src/models/device_session_state.dart';
export 'package:meta_wearables_dat_flutter/src/models/display/display_components.dart';
export 'package:meta_wearables_dat_flutter/src/models/display/display_playback_event.dart';
export 'package:meta_wearables_dat_flutter/src/models/display/display_state.dart';
export 'package:meta_wearables_dat_flutter/src/models/frame_data.dart';
export 'package:meta_wearables_dat_flutter/src/models/mock_permission.dart';
export 'package:meta_wearables_dat_flutter/src/models/photo_result.dart';
export 'package:meta_wearables_dat_flutter/src/models/registration_state.dart';
// ignore: deprecated_member_use_from_same_package
export 'package:meta_wearables_dat_flutter/src/models/session_state.dart';
export 'package:meta_wearables_dat_flutter/src/models/stream_quality.dart';
export 'package:meta_wearables_dat_flutter/src/models/stream_session_state.dart';
export 'package:meta_wearables_dat_flutter/src/models/video_frame.dart';
export 'package:meta_wearables_dat_flutter/src/models/video_stream_size.dart';

/// Static facade for the entire plugin.
///
/// **Lifecycle order** (see `doc/getting_started.md`):
///
/// 1. [requestAndroidPermissions] (Android only; safe no-op on iOS).
/// 2. [startRegistration] + [handleUrl] (host app forwards inbound deep
///    links to [handleUrl]).
/// 3. [requestCameraPermission] (Meta AI bottom sheet).
/// 4. [startStreamSession] returns a Flutter texture id; render with
///    `Texture(textureId: id)`.
/// 5. [stopStreamSession] when done.
abstract final class MetaWearablesDat {
  // --- Diagnostics ----------------------------------------------------------

  /// Returns a short string identifying the host platform.
  static Future<String?> getPlatformVersion() {
    return MetaWearablesDatPlatform.instance.getPlatformVersion();
  }

  /// Returns a structured snapshot of everything Meta's SDK validates at
  /// `startRegistration` time on the host platform.
  static Future<Map<String, Object?>> dumpDiagnostics() {
    return MetaWearablesDatPlatform.instance.dumpDiagnostics();
  }

  // --- Permissions ----------------------------------------------------------

  /// Requests the Android runtime permissions Meta's SDK requires
  /// (`BLUETOOTH_CONNECT` and `INTERNET`).
  ///
  /// Returns `true` if every required permission ends up granted, `false`
  /// otherwise. On iOS this method is a documented no-op and always
  /// resolves to `true` immediately.
  static Future<bool> requestAndroidPermissions() {
    return MetaWearablesDatPlatform.instance.requestAndroidPermissions();
  }

  /// Requests the wearable-side camera permission by deep-linking into
  /// the Meta AI app and showing its standard permission bottom sheet.
  ///
  /// Throws [PermissionError] when the request cannot be initiated.
  static Future<bool> requestCameraPermission() {
    return MetaWearablesDatPlatform.instance.requestCameraPermission();
  }

  /// Returns the current wearable-side camera permission status without
  /// triggering the Meta AI bottom sheet.
  static Future<bool> getCameraPermissionStatus() {
    return MetaWearablesDatPlatform.instance.getCameraPermissionStatus();
  }

  // --- Registration ---------------------------------------------------------

  /// Starts the device registration flow.
  ///
  /// Both [appId] and [urlScheme] are vestigial: every value the SDK
  /// needs is read from the host app's `Info.plist` (`MWDAT` dict) on
  /// iOS and `AndroidManifest.xml` `<meta-data>` on Android. Passing
  /// them here has **no effect** on either platform and they will be
  /// removed in v0.2.0.
  ///
  /// Throws [RegistrationError] if registration cannot be initiated.
  static Future<void> startRegistration({
    @Deprecated(
      'Vestigial parameter. The iOS SDK reads MetaAppID from '
      'Info.plist.MWDAT and the Android SDK reads APPLICATION_ID from '
      '<meta-data>. Will be removed in v0.2.0.',
    )
    String? appId,
    @Deprecated(
      'Vestigial parameter. The iOS SDK reads AppLinkURLScheme from '
      'Info.plist.MWDAT (and that value must end with "://", because '
      'Meta AI literally concatenates it with the callback query '
      'string). Android reads the scheme from the activity '
      '<intent-filter>. Will be removed in v0.2.0.',
    )
    String? urlScheme,
  }) {
    return MetaWearablesDatPlatform.instance.startRegistration(
      appId: appId,
      urlScheme: urlScheme,
    );
  }

  /// Forwards an inbound deep-link URL to the SDK.
  ///
  /// Throws [HandleUrlError] if the URL was not a registration callback.
  static Future<bool> handleUrl(String url) {
    return MetaWearablesDatPlatform.instance.handleUrl(url);
  }

  /// Starts an unregistration flow for the currently registered device.
  ///
  /// Throws [UnregistrationError] if it cannot be initiated.
  static Future<void> startUnregistration() {
    return MetaWearablesDatPlatform.instance.startUnregistration();
  }

  /// Returns the current [RegistrationState].
  static Future<RegistrationState> getRegistrationState() {
    return MetaWearablesDatPlatform.instance.getRegistrationState();
  }

  /// Broadcast stream of [RegistrationState] changes.
  static Stream<RegistrationState> registrationStateStream() {
    return MetaWearablesDatPlatform.instance.registrationStateStream();
  }

  /// Broadcast stream of the currently active device, or `null` when no
  /// device is paired or the registered device disconnects.
  static Stream<DeviceInfo?> activeDeviceStream() {
    return MetaWearablesDatPlatform.instance.activeDeviceStream();
  }

  /// Broadcast stream of every paired device (active or not). Mirrors
  /// `Wearables.shared.devicesStream()` on iOS and the equivalent
  /// `Wearables.devices` flow on Android.
  static Stream<List<DeviceInfo>> devicesStream() {
    return MetaWearablesDatPlatform.instance.devicesStream();
  }

  /// One-shot snapshot of every paired device known to the SDK.
  static Future<List<DeviceInfo>> getDevices() {
    return MetaWearablesDatPlatform.instance.getDevices();
  }

  /// Broadcast stream of per-device compatibility verdicts (e.g. "your
  /// glasses firmware needs an update"). Mirrors iOS
  /// `Device.addCompatibilityListener` / Android
  /// `Wearables.devicesMetadata[id].compatibility`.
  static Stream<DeviceCompatibilityEvent> compatibilityStream() {
    return MetaWearablesDatPlatform.instance.compatibilityStream();
  }

  /// Opens the Meta AI firmware update flow for glasses that report
  /// [DeviceCompatibility.deviceUpdateRequired].
  static Future<void> openFirmwareUpdate() {
    return MetaWearablesDatPlatform.instance.openFirmwareUpdate();
  }

  /// Opens the Meta AI DAT glasses-app update flow for glasses that report
  /// [DeviceCompatibility.sdkUpdateRequired].
  static Future<void> openDATGlassesAppUpdate() {
    return MetaWearablesDatPlatform.instance.openDATGlassesAppUpdate();
  }

  // --- Streaming ------------------------------------------------------------

  /// Starts a video stream from the active wearable and returns a Flutter
  /// `textureId` you can render with `Texture(textureId: id)`.
  ///
  /// When [deviceKinds] is set, only devices whose `kind` is in the set
  /// are considered by the underlying `AutoDeviceSelector` filter (or
  /// equivalent enumeration on iOS). Pass `null` to accept any kind.
  ///
  /// [videoCodec] picks the codec used for [videoFramesStream] payloads
  /// (see [VideoCodec]). The texture preview path always sees raw frames
  /// regardless of this setting on iOS; on Android the texture preview is
  /// disabled when [VideoCodec.hvc1] is selected (see `doc/streaming.md`).
  ///
  /// Throws [SessionError] (or [DeviceSessionError]) if the session
  /// cannot be started.
  static Future<int> startStreamSession({
    String? deviceUUID,
    int fps = 30,
    StreamQuality quality = StreamQuality.medium,
    Set<DeviceKind>? deviceKinds,
    VideoCodec videoCodec = VideoCodec.raw,
  }) {
    return MetaWearablesDatPlatform.instance.startStreamSession(
      deviceUUID: deviceUUID,
      fps: fps,
      quality: quality,
      deviceKinds: deviceKinds,
      videoCodec: videoCodec,
    );
  }

  /// Stops the active stream session and unregisters the texture.
  static Future<void> stopStreamSession({String? deviceUUID}) {
    return MetaWearablesDatPlatform.instance.stopStreamSession(
      deviceUUID: deviceUUID,
    );
  }

  /// Pauses the active stream session.
  static Future<void> pauseStreamSession({String? deviceUUID}) {
    return MetaWearablesDatPlatform.instance.pauseStreamSession(
      deviceUUID: deviceUUID,
    );
  }

  /// Resumes a paused stream session.
  static Future<void> resumeStreamSession({String? deviceUUID}) {
    return MetaWearablesDatPlatform.instance.resumeStreamSession(
      deviceUUID: deviceUUID,
    );
  }

  /// Broadcast stream of [StreamSessionState] changes.
  static Stream<StreamSessionState> streamSessionStateStream() {
    return MetaWearablesDatPlatform.instance.streamSessionStateStream();
  }

  /// Broadcast stream of stream-level session errors. Events are typed
  /// [SessionError] subclasses with `is*` getters such as
  /// `isThermalCritical` and `isHingesClosed`.
  static Stream<Object> streamSessionErrorStream() {
    return MetaWearablesDatPlatform.instance.streamSessionErrorStream();
  }

  /// Broadcast stream of [DeviceSessionState] changes — the underlying
  /// long-lived connection to a paired wearable.
  static Stream<DeviceSessionState> deviceSessionStateStream() {
    return MetaWearablesDatPlatform.instance.deviceSessionStateStream();
  }

  /// Broadcast stream of [DeviceSessionError] events from the underlying
  /// device session (separate from the stream-level errors emitted by
  /// [streamSessionErrorStream]).
  static Stream<Object> deviceSessionErrorStream() {
    return MetaWearablesDatPlatform.instance.deviceSessionErrorStream();
  }

  /// **Deprecated** — alias for [streamSessionStateStream]. Will be removed
  /// in v0.2.0.
  @Deprecated('Use streamSessionStateStream() instead.')
  static Stream<StreamSessionState> sessionStateStream() {
    return MetaWearablesDatPlatform.instance.streamSessionStateStream();
  }

  /// **Deprecated** — alias for [streamSessionErrorStream]. Will be removed
  /// in v0.2.0.
  @Deprecated('Use streamSessionErrorStream() instead.')
  static Stream<Object> sessionErrorStream() {
    return MetaWearablesDatPlatform.instance.streamSessionErrorStream();
  }

  /// Broadcast stream of [VideoStreamSize] updates emitted once per
  /// resolution change. Use the latest value to drive an `AspectRatio`
  /// around the texture widget.
  static Stream<VideoStreamSize> videoStreamSizeStream() {
    return MetaWearablesDatPlatform.instance.videoStreamSizeStream();
  }

  /// Broadcast stream of every video frame produced by the active stream
  /// session, suitable for recording / OCR / ML pipelines.
  ///
  /// Payloads are large (≈3.7 MB per 720p raw BGRA frame); the native side
  /// only does the per-frame copy when at least one Dart subscriber is
  /// attached. See `doc/frame_processing.md` for budget guidance.
  static Stream<VideoFrame> videoFramesStream() {
    return MetaWearablesDatPlatform.instance.videoFramesStream();
  }

  /// Keeps frames flowing through device sleep / screen lock / app
  /// backgrounding.
  ///
  /// On iOS this activates `AVAudioSession` with `.playAndRecord` /
  /// `.videoRecording`, registers interruption + route-change observers
  /// (so AVAudioSession is re-activated on recovery), and flips the
  /// VTDecompression pipeline into software-only mode so frames keep
  /// decoding while the app is backgrounded. The host app must declare
  /// the matching `UIBackgroundModes` keys (`audio`, `bluetooth-central`,
  /// `bluetooth-peripheral`, `external-accessory`) in its `Info.plist`.
  ///
  /// On Android this starts a foreground service of type
  /// `FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE` showing
  /// [androidNotification]'s details, acquires a partial wake lock, and
  /// runtime-requests `POST_NOTIFICATIONS` on API 33+. Throws
  /// [DatError] when [androidNotification] is null on Android.
  static Future<void> enableBackgroundStreaming({
    BackgroundNotification? androidNotification,
  }) {
    return MetaWearablesDatPlatform.instance.enableBackgroundStreaming(
      androidNotification: androidNotification,
    );
  }

  /// Reverses [enableBackgroundStreaming]: deactivates the iOS
  /// `AVAudioSession`, stops the Android foreground service, and
  /// releases the wake lock.
  static Future<void> disableBackgroundStreaming() {
    return MetaWearablesDatPlatform.instance.disableBackgroundStreaming();
  }

  // --- Capture --------------------------------------------------------------

  /// Captures a single frame from a live texture in pure Dart, without
  /// touching the platform channel for the pixel data.
  static Future<FrameData?> captureStreamFrame(
    int textureId, {
    FrameFormat format = FrameFormat.rawRgba,
  }) {
    return MetaWearablesDatPlatform.instance.captureStreamFrame(
      textureId,
      format: format,
    );
  }

  /// Captures the most recent streamed frame as JPEG bytes, encoded natively
  /// on the CPU from the SDK's latest decoded pixel buffer.
  ///
  /// Unlike [captureStreamFrame] (which rasterizes the Flutter texture via
  /// `ui.Scene.toImage` and therefore only works while the app is foregrounded
  /// and the GPU raster pipeline is live), this keeps producing viewable frames
  /// while the app is backgrounded — the SDK's native frame callback keeps the
  /// source buffer fresh and the encode runs on the CPU. Prefer this for
  /// background/continuous capture. [quality] is the JPEG quality (0.0–1.0).
  static Future<FrameData?> captureLatestFrame({double quality = 0.8}) {
    return MetaWearablesDatPlatform.instance.captureLatestFrame(
      quality: quality,
    );
  }

  /// Captures a high-resolution still mid-stream.
  ///
  /// Throws [CaptureError] if the device is disconnected, no session is
  /// active, a capture is already in progress, or the SDK reports a
  /// hardware-side capture failure.
  static Future<PhotoResult> capturePhoto({
    String? deviceUUID,
    PhotoFormat format = PhotoFormat.jpeg,
  }) {
    return MetaWearablesDatPlatform.instance.capturePhoto(
      deviceUUID: deviceUUID,
      format: format,
    );
  }

  // --- Display --------------------------------------------------------------

  /// Attaches the display capability to a Ray-Ban Display device and starts
  /// it, so [sendDisplayView] can render content on the glasses.
  ///
  /// Pass [deviceUUID] to target a specific paired device; otherwise the SDK
  /// auto-selects the best display-capable device. Observe progress via
  /// [displayStateStream] (the display is ready once it reaches
  /// [DisplayState.started]).
  ///
  /// Throws [DeviceSessionError] if the session cannot be started (e.g.
  /// `isDatAppUpdateRequired` when the on-glasses DAT app is too old).
  static Future<void> startDisplaySession({String? deviceUUID}) {
    return MetaWearablesDatPlatform.instance.startDisplaySession(
      deviceUUID: deviceUUID,
    );
  }

  /// Renders [view] on the glasses display, replacing whatever was shown
  /// before.
  ///
  /// Build [view] declaratively with [FlexBox], [DisplayText], [DisplayImage],
  /// [DisplayButton], [DisplayIcon] and [VideoPlayer]. Tap / click / playback
  /// handlers attached to the tree are invoked when the user interacts with
  /// the rendered content.
  ///
  /// If no display session is active yet this will attach one on demand on
  /// platforms that support it; otherwise call [startDisplaySession] first.
  static Future<void> sendDisplayView(DisplayView view) {
    return MetaWearablesDatPlatform.instance.sendDisplayView(view);
  }

  /// Detaches the display capability and tears down its device session.
  static Future<void> stopDisplaySession() {
    return MetaWearablesDatPlatform.instance.stopDisplaySession();
  }

  /// Broadcast stream of [DisplayState] changes for the display capability.
  static Stream<DisplayState> displayStateStream() {
    return MetaWearablesDatPlatform.instance.displayStateStream();
  }

  // --- Mock Device Kit ------------------------------------------------------

  /// Enables Meta's Mock Device Kit so [pairMockRayBanMeta] and friends can
  /// be used to develop without real glasses.
  ///
  /// [initiallyRegistered] / [initialPermissionsGranted] map to
  /// `MockDeviceKit.shared.enable(config:)` on iOS (and the equivalent
  /// Android API).
  static Future<void> enableMockDevice({
    bool initiallyRegistered = true,
    bool initialPermissionsGranted = true,
  }) {
    return MetaWearablesDatPlatform.instance.enableMockDevice(
      initiallyRegistered: initiallyRegistered,
      initialPermissionsGranted: initialPermissionsGranted,
    );
  }

  /// Disables the Mock Device Kit and unpairs all simulated devices.
  static Future<void> disableMockDevice() {
    return MetaWearablesDatPlatform.instance.disableMockDevice();
  }

  /// Returns `true` if the Mock Device Kit is currently enabled.
  static Future<bool> isMockDeviceEnabled() {
    return MetaWearablesDatPlatform.instance.isMockDeviceEnabled();
  }

  /// Pairs a simulated Ray-Ban Meta device. Returns the UUID assigned to it.
  static Future<String> pairMockRayBanMeta() {
    return MetaWearablesDatPlatform.instance.pairMockRayBanMeta();
  }

  /// Returns the list of currently-paired mock devices.
  static Future<List<DeviceInfo>> pairedMockDevices() {
    return MetaWearablesDatPlatform.instance.pairedMockDevices();
  }

  /// Unpairs a previously-paired mock device.
  static Future<void> unpairMockDevice(String uuid) {
    return MetaWearablesDatPlatform.instance.unpairMockDevice(uuid);
  }

  /// Powers a mock device on.
  static Future<void> mockPowerOn(String uuid) {
    return MetaWearablesDatPlatform.instance.mockPowerOn(uuid);
  }

  /// Powers a mock device off.
  static Future<void> mockPowerOff(String uuid) {
    return MetaWearablesDatPlatform.instance.mockPowerOff(uuid);
  }

  /// Marks the mock device as worn ("donned").
  static Future<void> mockDon(String uuid) {
    return MetaWearablesDatPlatform.instance.mockDon(uuid);
  }

  /// Marks the mock device as removed ("doffed").
  static Future<void> mockDoff(String uuid) {
    return MetaWearablesDatPlatform.instance.mockDoff(uuid);
  }

  /// Folds the mock device (sleep-like state for displayless glasses).
  static Future<void> mockFold(String uuid) {
    return MetaWearablesDatPlatform.instance.mockFold(uuid);
  }

  /// Unfolds the mock device.
  static Future<void> mockUnfold(String uuid) {
    return MetaWearablesDatPlatform.instance.mockUnfold(uuid);
  }

  /// Picks which of the host phone's cameras feeds the simulated device.
  static Future<void> setMockCameraFacing(String uuid, CameraFacing facing) {
    return MetaWearablesDatPlatform.instance.setMockCameraFacing(uuid, facing);
  }

  /// Sets a video file (or content URI on Android) as the mock device's
  /// camera feed. Pass `null` for [filePath] to clear it.
  static Future<void> setMockCameraFeed(String uuid, String? filePath) {
    return MetaWearablesDatPlatform.instance.setMockCameraFeed(uuid, filePath);
  }

  /// Sets a still image file as what the mock device returns from
  /// [capturePhoto] requests. Pass `null` for [filePath] to clear it.
  static Future<void> setMockCapturedImage(String uuid, String? filePath) {
    return MetaWearablesDatPlatform.instance.setMockCapturedImage(
      uuid,
      filePath,
    );
  }

  /// Sets the current permission status reported by the Mock Device Kit
  /// for [permission].
  static Future<void> setMockPermission(
    MockPermission permission,
    MockPermissionStatus status,
  ) {
    return MetaWearablesDatPlatform.instance.setMockPermission(
      permission.value,
      status.value,
    );
  }

  /// Sets what the **next** `requestPermission` call resolves to.
  static Future<void> setMockPermissionRequestResult(
    MockPermission permission,
    MockPermissionStatus status,
  ) {
    return MetaWearablesDatPlatform.instance.setMockPermissionRequestResult(
      permission.value,
      status.value,
    );
  }

  /// Broadcast stream of currently paired mock devices.
  static Stream<List<DeviceInfo>> mockDevicesStream() {
    return MetaWearablesDatPlatform.instance.mockDevicesStream();
  }
}
