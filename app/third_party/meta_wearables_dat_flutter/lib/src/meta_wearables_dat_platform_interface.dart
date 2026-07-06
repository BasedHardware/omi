import 'package:meta_wearables_dat_flutter/src/meta_wearables_dat_method_channel.dart';
import 'package:meta_wearables_dat_flutter/src/models/background_notification.dart';
import 'package:meta_wearables_dat_flutter/src/models/camera_facing.dart';
import 'package:meta_wearables_dat_flutter/src/models/device_compatibility.dart';
import 'package:meta_wearables_dat_flutter/src/models/device_info.dart';
import 'package:meta_wearables_dat_flutter/src/models/device_session_state.dart';
import 'package:meta_wearables_dat_flutter/src/models/display/display_components.dart';
import 'package:meta_wearables_dat_flutter/src/models/display/display_state.dart';
import 'package:meta_wearables_dat_flutter/src/models/frame_data.dart';
import 'package:meta_wearables_dat_flutter/src/models/photo_result.dart';
import 'package:meta_wearables_dat_flutter/src/models/registration_state.dart';
import 'package:meta_wearables_dat_flutter/src/models/stream_quality.dart';
import 'package:meta_wearables_dat_flutter/src/models/stream_session_state.dart';
import 'package:meta_wearables_dat_flutter/src/models/video_frame.dart';
import 'package:meta_wearables_dat_flutter/src/models/video_stream_size.dart';
import 'package:plugin_platform_interface/plugin_platform_interface.dart';

/// Platform interface for `meta_wearables_dat_flutter`.
///
/// Concrete implementations subclass [MetaWearablesDatPlatform] and override
/// the methods they implement. The shipped default,
/// [MethodChannelMetaWearablesDat], forwards every call across a single
/// `MethodChannel` and the topic-specific `EventChannel`s described in
/// `AGENTS.md`.
///
/// Tests can substitute their own subclass with `MockPlatformInterfaceMixin`.
abstract class MetaWearablesDatPlatform extends PlatformInterface {
  /// Constructs a [MetaWearablesDatPlatform].
  MetaWearablesDatPlatform() : super(token: _token);

  static final Object _token = Object();

  static MetaWearablesDatPlatform _instance = MethodChannelMetaWearablesDat();

  /// The current default platform implementation.
  static MetaWearablesDatPlatform get instance => _instance;

  /// Sets the platform implementation (used by tests).
  static set instance(MetaWearablesDatPlatform instance) {
    PlatformInterface.verifyToken(instance, _token);
    _instance = instance;
  }

  // --- Diagnostics ----------------------------------------------------------

  /// Returns a short string identifying the host platform.
  Future<String?> getPlatformVersion() {
    throw UnimplementedError('getPlatformVersion() has not been implemented.');
  }

  /// Implements `MetaWearablesDat.dumpDiagnostics`.
  Future<Map<String, Object?>> dumpDiagnostics() {
    throw UnimplementedError('dumpDiagnostics() has not been implemented.');
  }

  // --- Permissions ----------------------------------------------------------

  /// Implements `MetaWearablesDat.requestAndroidPermissions`.
  Future<bool> requestAndroidPermissions() {
    throw UnimplementedError(
      'requestAndroidPermissions() has not been implemented.',
    );
  }

  /// Implements `MetaWearablesDat.requestCameraPermission`.
  Future<bool> requestCameraPermission() {
    throw UnimplementedError(
      'requestCameraPermission() has not been implemented.',
    );
  }

  /// Implements `MetaWearablesDat.getCameraPermissionStatus`.
  Future<bool> getCameraPermissionStatus() {
    throw UnimplementedError(
      'getCameraPermissionStatus() has not been implemented.',
    );
  }

  // --- Registration ---------------------------------------------------------

  /// Implements `MetaWearablesDat.startRegistration`.
  Future<void> startRegistration({String? appId, String? urlScheme}) {
    throw UnimplementedError('startRegistration() has not been implemented.');
  }

  /// Implements `MetaWearablesDat.handleUrl`.
  Future<bool> handleUrl(String url) {
    throw UnimplementedError('handleUrl() has not been implemented.');
  }

  /// Implements `MetaWearablesDat.startUnregistration`.
  Future<void> startUnregistration() {
    throw UnimplementedError(
      'startUnregistration() has not been implemented.',
    );
  }

  /// Implements `MetaWearablesDat.getRegistrationState`.
  Future<RegistrationState> getRegistrationState() {
    throw UnimplementedError(
      'getRegistrationState() has not been implemented.',
    );
  }

  /// Implements `MetaWearablesDat.registrationStateStream`.
  Stream<RegistrationState> registrationStateStream() {
    throw UnimplementedError(
      'registrationStateStream() has not been implemented.',
    );
  }

  /// Implements `MetaWearablesDat.activeDeviceStream`.
  Stream<DeviceInfo?> activeDeviceStream() {
    throw UnimplementedError('activeDeviceStream() has not been implemented.');
  }

  /// Implements `MetaWearablesDat.devicesStream`.
  Stream<List<DeviceInfo>> devicesStream() {
    throw UnimplementedError('devicesStream() has not been implemented.');
  }

  /// Implements `MetaWearablesDat.getDevices`.
  Future<List<DeviceInfo>> getDevices() {
    throw UnimplementedError('getDevices() has not been implemented.');
  }

  /// Implements `MetaWearablesDat.compatibilityStream`.
  Stream<DeviceCompatibilityEvent> compatibilityStream() {
    throw UnimplementedError('compatibilityStream() has not been implemented.');
  }

  /// Implements `MetaWearablesDat.openFirmwareUpdate`.
  Future<void> openFirmwareUpdate() {
    throw UnimplementedError('openFirmwareUpdate() has not been implemented.');
  }

  /// Implements `MetaWearablesDat.openDATGlassesAppUpdate`.
  Future<void> openDATGlassesAppUpdate() {
    throw UnimplementedError(
      'openDATGlassesAppUpdate() has not been implemented.',
    );
  }

  // --- Streaming ------------------------------------------------------------

  /// Implements `MetaWearablesDat.startStreamSession`.
  Future<int> startStreamSession({
    String? deviceUUID,
    int fps = 30,
    StreamQuality quality = StreamQuality.medium,
    Set<DeviceKind>? deviceKinds,
    VideoCodec videoCodec = VideoCodec.raw,
  }) {
    throw UnimplementedError('startStreamSession() has not been implemented.');
  }

  /// Implements `MetaWearablesDat.stopStreamSession`.
  Future<void> stopStreamSession({String? deviceUUID}) {
    throw UnimplementedError('stopStreamSession() has not been implemented.');
  }

  /// Implements `MetaWearablesDat.pauseStreamSession`.
  Future<void> pauseStreamSession({String? deviceUUID}) {
    throw UnimplementedError('pauseStreamSession() has not been implemented.');
  }

  /// Implements `MetaWearablesDat.resumeStreamSession`.
  Future<void> resumeStreamSession({String? deviceUUID}) {
    throw UnimplementedError(
      'resumeStreamSession() has not been implemented.',
    );
  }

  /// Implements `MetaWearablesDat.streamSessionStateStream`.
  Stream<StreamSessionState> streamSessionStateStream() {
    throw UnimplementedError(
      'streamSessionStateStream() has not been implemented.',
    );
  }

  /// Implements `MetaWearablesDat.streamSessionErrorStream`.
  Stream<Object> streamSessionErrorStream() {
    throw UnimplementedError(
      'streamSessionErrorStream() has not been implemented.',
    );
  }

  /// Implements `MetaWearablesDat.deviceSessionStateStream`.
  Stream<DeviceSessionState> deviceSessionStateStream() {
    throw UnimplementedError(
      'deviceSessionStateStream() has not been implemented.',
    );
  }

  /// Implements `MetaWearablesDat.deviceSessionErrorStream`.
  Stream<Object> deviceSessionErrorStream() {
    throw UnimplementedError(
      'deviceSessionErrorStream() has not been implemented.',
    );
  }

  /// Implements `MetaWearablesDat.videoStreamSizeStream`.
  Stream<VideoStreamSize> videoStreamSizeStream() {
    throw UnimplementedError(
      'videoStreamSizeStream() has not been implemented.',
    );
  }

  /// Implements `MetaWearablesDat.videoFramesStream`.
  Stream<VideoFrame> videoFramesStream() {
    throw UnimplementedError('videoFramesStream() has not been implemented.');
  }

  /// Implements `MetaWearablesDat.enableBackgroundStreaming`.
  Future<void> enableBackgroundStreaming({
    BackgroundNotification? androidNotification,
  }) {
    throw UnimplementedError(
      'enableBackgroundStreaming() has not been implemented.',
    );
  }

  /// Implements `MetaWearablesDat.disableBackgroundStreaming`.
  Future<void> disableBackgroundStreaming() {
    throw UnimplementedError(
      'disableBackgroundStreaming() has not been implemented.',
    );
  }

  // --- Display --------------------------------------------------------------

  /// Implements `MetaWearablesDat.startDisplaySession`.
  Future<void> startDisplaySession({String? deviceUUID}) {
    throw UnimplementedError('startDisplaySession() has not been implemented.');
  }

  /// Implements `MetaWearablesDat.sendDisplayView`.
  Future<void> sendDisplayView(DisplayView view) {
    throw UnimplementedError('sendDisplayView() has not been implemented.');
  }

  /// Implements `MetaWearablesDat.stopDisplaySession`.
  Future<void> stopDisplaySession() {
    throw UnimplementedError('stopDisplaySession() has not been implemented.');
  }

  /// Implements `MetaWearablesDat.displayStateStream`.
  Stream<DisplayState> displayStateStream() {
    throw UnimplementedError('displayStateStream() has not been implemented.');
  }

  // --- Capture --------------------------------------------------------------

  /// Implements `MetaWearablesDat.captureStreamFrame`.
  Future<FrameData?> captureStreamFrame(
    int textureId, {
    FrameFormat format = FrameFormat.rawRgba,
  }) {
    throw UnimplementedError(
      'captureStreamFrame() has not been implemented.',
    );
  }

  /// Implements `MetaWearablesDat.captureLatestFrame`.
  Future<FrameData?> captureLatestFrame({double quality = 0.8}) {
    throw UnimplementedError(
      'captureLatestFrame() has not been implemented.',
    );
  }

  /// Implements `MetaWearablesDat.capturePhoto`.
  Future<PhotoResult> capturePhoto({
    String? deviceUUID,
    PhotoFormat format = PhotoFormat.jpeg,
  }) {
    throw UnimplementedError('capturePhoto() has not been implemented.');
  }

  // --- Mock Device ----------------------------------------------------------

  /// Implements `MetaWearablesDat.enableMockDevice`.
  Future<void> enableMockDevice({
    bool initiallyRegistered = true,
    bool initialPermissionsGranted = true,
  }) {
    throw UnimplementedError('enableMockDevice() has not been implemented.');
  }

  /// Implements `MetaWearablesDat.disableMockDevice`.
  Future<void> disableMockDevice() {
    throw UnimplementedError('disableMockDevice() has not been implemented.');
  }

  /// Implements `MetaWearablesDat.isMockDeviceEnabled`.
  Future<bool> isMockDeviceEnabled() {
    throw UnimplementedError(
      'isMockDeviceEnabled() has not been implemented.',
    );
  }

  /// Implements `MetaWearablesDat.pairMockRayBanMeta`.
  Future<String> pairMockRayBanMeta() {
    throw UnimplementedError('pairMockRayBanMeta() has not been implemented.');
  }

  /// Implements `MetaWearablesDat.pairedMockDevices`.
  Future<List<DeviceInfo>> pairedMockDevices() {
    throw UnimplementedError(
      'pairedMockDevices() has not been implemented.',
    );
  }

  /// Implements `MetaWearablesDat.unpairMockDevice`.
  Future<void> unpairMockDevice(String uuid) {
    throw UnimplementedError('unpairMockDevice() has not been implemented.');
  }

  /// Implements `MetaWearablesDat.mockPowerOn`.
  Future<void> mockPowerOn(String uuid) {
    throw UnimplementedError('mockPowerOn() has not been implemented.');
  }

  /// Implements `MetaWearablesDat.mockPowerOff`.
  Future<void> mockPowerOff(String uuid) {
    throw UnimplementedError('mockPowerOff() has not been implemented.');
  }

  /// Implements `MetaWearablesDat.mockDon`.
  Future<void> mockDon(String uuid) {
    throw UnimplementedError('mockDon() has not been implemented.');
  }

  /// Implements `MetaWearablesDat.mockDoff`.
  Future<void> mockDoff(String uuid) {
    throw UnimplementedError('mockDoff() has not been implemented.');
  }

  /// Implements `MetaWearablesDat.mockFold`.
  Future<void> mockFold(String uuid) {
    throw UnimplementedError('mockFold() has not been implemented.');
  }

  /// Implements `MetaWearablesDat.mockUnfold`.
  Future<void> mockUnfold(String uuid) {
    throw UnimplementedError('mockUnfold() has not been implemented.');
  }

  /// Implements `MetaWearablesDat.setMockCameraFacing`.
  Future<void> setMockCameraFacing(String uuid, CameraFacing facing) {
    throw UnimplementedError(
      'setMockCameraFacing() has not been implemented.',
    );
  }

  /// Implements `MetaWearablesDat.setMockCameraFeed`. [filePath] may be
  /// `null` to clear the previously-set feed.
  Future<void> setMockCameraFeed(String uuid, String? filePath) {
    throw UnimplementedError('setMockCameraFeed() has not been implemented.');
  }

  /// Implements `MetaWearablesDat.setMockCapturedImage`. [filePath] may be
  /// `null` to clear the previously-set image.
  Future<void> setMockCapturedImage(String uuid, String? filePath) {
    throw UnimplementedError(
      'setMockCapturedImage() has not been implemented.',
    );
  }

  /// Implements `MetaWearablesDat.setMockPermission`.
  Future<void> setMockPermission(String permission, String status) {
    throw UnimplementedError(
      'setMockPermission() has not been implemented.',
    );
  }

  /// Implements `MetaWearablesDat.setMockPermissionRequestResult`.
  Future<void> setMockPermissionRequestResult(
    String permission,
    String status,
  ) {
    throw UnimplementedError(
      'setMockPermissionRequestResult() has not been implemented.',
    );
  }

  /// Implements `MetaWearablesDat.mockDevicesStream`.
  Stream<List<DeviceInfo>> mockDevicesStream() {
    throw UnimplementedError('mockDevicesStream() has not been implemented.');
  }
}
