import 'dart:async';
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:meta_wearables_dat_flutter/src/meta_wearables_dat_platform_interface.dart';
import 'package:meta_wearables_dat_flutter/src/models/background_notification.dart';
import 'package:meta_wearables_dat_flutter/src/models/camera_facing.dart';
import 'package:meta_wearables_dat_flutter/src/models/dat_error.dart';
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

/// Default [MetaWearablesDatPlatform] implementation that forwards every call
/// across a single `MethodChannel` plus the topic-specific `EventChannel`s
/// described in `AGENTS.md`.
class MethodChannelMetaWearablesDat extends MetaWearablesDatPlatform {
  /// Method channel used for request/response calls.
  @visibleForTesting
  final MethodChannel methodChannel = const MethodChannel(
    'meta_wearables_dat_flutter',
  );

  /// Event channel for `registrationStateStream`.
  @visibleForTesting
  final EventChannel registrationStateChannel = const EventChannel(
    'meta_wearables_dat_flutter/registration_state',
  );

  /// Event channel for `activeDeviceStream`.
  @visibleForTesting
  final EventChannel activeDeviceChannel = const EventChannel(
    'meta_wearables_dat_flutter/active_device',
  );

  /// Event channel for `devicesStream`.
  @visibleForTesting
  final EventChannel devicesChannel = const EventChannel(
    'meta_wearables_dat_flutter/devices',
  );

  /// Event channel for `compatibilityStream`.
  @visibleForTesting
  final EventChannel compatibilityChannel = const EventChannel(
    'meta_wearables_dat_flutter/compatibility',
  );

  /// Event channel for `streamSessionStateStream`.
  @visibleForTesting
  final EventChannel streamSessionStateChannel = const EventChannel(
    'meta_wearables_dat_flutter/stream_session_state',
  );

  /// Event channel for `streamSessionErrorStream`.
  @visibleForTesting
  final EventChannel streamSessionErrorsChannel = const EventChannel(
    'meta_wearables_dat_flutter/stream_session_errors',
  );

  /// Event channel for `deviceSessionStateStream`.
  @visibleForTesting
  final EventChannel deviceSessionStateChannel = const EventChannel(
    'meta_wearables_dat_flutter/device_session_state',
  );

  /// Event channel for `deviceSessionErrorStream`.
  @visibleForTesting
  final EventChannel deviceSessionErrorsChannel = const EventChannel(
    'meta_wearables_dat_flutter/device_session_errors',
  );

  /// Event channel for `videoStreamSizeStream`.
  @visibleForTesting
  final EventChannel videoStreamSizeChannel = const EventChannel(
    'meta_wearables_dat_flutter/video_stream_size',
  );

  /// Event channel for `videoFramesStream`.
  @visibleForTesting
  final EventChannel videoFramesChannel = const EventChannel(
    'meta_wearables_dat_flutter/video_frames',
  );

  /// Event channel for `mockDevicesStream`.
  @visibleForTesting
  final EventChannel mockDevicesChannel = const EventChannel(
    'meta_wearables_dat_flutter/mock_devices',
  );

  /// Event channel for `displayStateStream`.
  @visibleForTesting
  final EventChannel displayStateChannel = const EventChannel(
    'meta_wearables_dat_flutter/display_state',
  );

  /// Event channel carrying display tap / click / playback callbacks back to
  /// Dart. Each event is `{callbackId, type, [event]}`.
  @visibleForTesting
  final EventChannel displayEventsChannel = const EventChannel(
    'meta_wearables_dat_flutter/display_events',
  );

  // Cached broadcast streams so multiple Dart-side listeners share a single
  // platform-channel subscription.
  Stream<RegistrationState>? _registrationStateStream;
  Stream<DeviceInfo?>? _activeDeviceStream;
  Stream<List<DeviceInfo>>? _devicesStream;
  Stream<DeviceCompatibilityEvent>? _compatibilityStream;
  Stream<StreamSessionState>? _streamSessionStateStream;
  Stream<Object>? _streamSessionErrorStream;
  Stream<DeviceSessionState>? _deviceSessionStateStream;
  Stream<Object>? _deviceSessionErrorStream;
  Stream<VideoStreamSize>? _videoStreamSizeStream;
  Stream<VideoFrame>? _videoFramesStream;
  Stream<List<DeviceInfo>>? _mockDevicesStream;
  Stream<DisplayState>? _displayStateStream;

  /// Callback table for the view currently shown on the glasses display.
  /// Rebuilt on every [sendDisplayView]; dispatched to from the
  /// `display_events` channel.
  DisplayCallbackTable? _displayCallbacks;

  /// Long-lived subscription to the `display_events` channel. Lives for the
  /// lifetime of the plugin singleton (like the cached broadcast streams
  /// above), so it is intentionally never cancelled.
  // ignore: cancel_subscriptions
  StreamSubscription<dynamic>? _displayEventsSubscription;

  /// Latest [VideoStreamSize] observed on the `video_stream_size` channel.
  VideoStreamSize? _lastVideoStreamSize;

  // --- Diagnostics ----------------------------------------------------------

  @override
  Future<String?> getPlatformVersion() {
    return methodChannel.invokeMethod<String>('getPlatformVersion');
  }

  @override
  Future<Map<String, Object?>> dumpDiagnostics() async {
    final raw = await methodChannel.invokeMethod<Map<Object?, Object?>>('dumpDiagnostics');
    return _deepStringKeyed(raw) ?? <String, Object?>{};
  }

  Map<String, Object?>? _deepStringKeyed(Object? value) {
    if (value is Map) {
      final result = <String, Object?>{};
      value.forEach((k, v) {
        result['$k'] = _deepConvert(v);
      });
      return result;
    }
    return null;
  }

  Object? _deepConvert(Object? value) {
    if (value is Map) {
      return _deepStringKeyed(value);
    }
    if (value is List) {
      return value.map(_deepConvert).toList(growable: false);
    }
    return value;
  }

  // --- Permissions ----------------------------------------------------------

  @override
  Future<bool> requestAndroidPermissions() async {
    final granted = await methodChannel.invokeMethod<bool>(
      'requestAndroidPermissions',
    );
    return granted ?? false;
  }

  @override
  Future<bool> requestCameraPermission() async {
    try {
      final granted = await methodChannel.invokeMethod<bool>(
        'requestCameraPermission',
      );
      return granted ?? false;
    } on PlatformException catch (e) {
      throw _mapPlatformException(e);
    }
  }

  @override
  Future<bool> getCameraPermissionStatus() async {
    try {
      final granted = await methodChannel.invokeMethod<bool>(
        'getCameraPermissionStatus',
      );
      return granted ?? false;
    } on PlatformException catch (e) {
      throw _mapPlatformException(e);
    }
  }

  // --- Registration ---------------------------------------------------------

  @override
  Future<void> startRegistration({String? appId, String? urlScheme}) async {
    try {
      await methodChannel.invokeMethod<void>(
        'startRegistration',
        <String, Object?>{
          if (appId != null) 'appId': appId,
          if (urlScheme != null) 'urlScheme': urlScheme,
        },
      );
    } on PlatformException catch (e) {
      throw _mapPlatformException(e);
    }
  }

  @override
  Future<bool> handleUrl(String url) async {
    try {
      final consumed = await methodChannel.invokeMethod<bool>(
        'handleUrl',
        <String, Object?>{'url': url},
      );
      return consumed ?? false;
    } on PlatformException catch (e) {
      throw _mapPlatformException(e);
    }
  }

  @override
  Future<void> startUnregistration() async {
    try {
      await methodChannel.invokeMethod<void>('startUnregistration');
    } on PlatformException catch (e) {
      throw _mapPlatformException(e);
    }
  }

  @override
  Future<RegistrationState> getRegistrationState() async {
    final raw = await methodChannel.invokeMethod<int>('getRegistrationState');
    return RegistrationState.fromInt(raw);
  }

  // --- Registration streams -------------------------------------------------

  @override
  Stream<RegistrationState> registrationStateStream() {
    return _registrationStateStream ??=
        registrationStateChannel.receiveBroadcastStream().map((event) => RegistrationState.fromInt(event as int?));
  }

  @override
  Stream<DeviceInfo?> activeDeviceStream() {
    return _activeDeviceStream ??= activeDeviceChannel.receiveBroadcastStream().map((event) {
      if (event == null) return null;
      return DeviceInfo.fromMap(event as Map<Object?, Object?>);
    });
  }

  @override
  Stream<List<DeviceInfo>> devicesStream() {
    return _devicesStream ??= devicesChannel.receiveBroadcastStream().map((
      event,
    ) {
      final list = (event as List<Object?>?) ?? const [];
      return list.map((e) => DeviceInfo.fromMap(e! as Map<Object?, Object?>)).toList(growable: false);
    });
  }

  @override
  Future<List<DeviceInfo>> getDevices() async {
    try {
      final raw = await methodChannel.invokeMethod<List<Object?>>('getDevices');
      if (raw == null) return const [];
      return raw.map((e) => DeviceInfo.fromMap(e! as Map<Object?, Object?>)).toList(growable: false);
    } on PlatformException catch (e) {
      throw _mapPlatformException(e);
    }
  }

  @override
  Stream<DeviceCompatibilityEvent> compatibilityStream() {
    return _compatibilityStream ??= compatibilityChannel.receiveBroadcastStream().map(
          (event) => DeviceCompatibilityEvent.fromMap(
            event as Map<Object?, Object?>,
          ),
        );
  }

  @override
  Future<void> openFirmwareUpdate() {
    return methodChannel.invokeMethod<void>('openFirmwareUpdate');
  }

  @override
  Future<void> openDATGlassesAppUpdate() {
    return methodChannel.invokeMethod<void>('openDATGlassesAppUpdate');
  }

  // --- Streaming ------------------------------------------------------------

  @override
  Future<int> startStreamSession({
    String? deviceUUID,
    int fps = 30,
    StreamQuality quality = StreamQuality.medium,
    Set<DeviceKind>? deviceKinds,
    VideoCodec videoCodec = VideoCodec.raw,
  }) async {
    try {
      final id = await methodChannel.invokeMethod<int>(
        'startStreamSession',
        <String, Object?>{
          if (deviceUUID != null) 'deviceUuid': deviceUUID,
          'fps': fps,
          'quality': quality.name,
          if (deviceKinds != null && deviceKinds.isNotEmpty) 'deviceKinds': deviceKinds.map((k) => k.wireName).toList(),
          'videoCodec': videoCodec.name,
        },
      );
      if (id == null) {
        throw const SessionError(
          code: DatErrorCodes.session,
          message: 'startStreamSession returned null',
        );
      }
      return id;
    } on PlatformException catch (e) {
      throw _mapPlatformException(e);
    }
  }

  @override
  Future<void> stopStreamSession({String? deviceUUID}) async {
    try {
      await methodChannel.invokeMethod<void>(
        'stopStreamSession',
        <String, Object?>{
          if (deviceUUID != null) 'deviceUuid': deviceUUID,
        },
      );
    } on PlatformException catch (e) {
      throw _mapPlatformException(e);
    }
  }

  @override
  Future<void> pauseStreamSession({String? deviceUUID}) async {
    try {
      await methodChannel.invokeMethod<void>(
        'pauseStreamSession',
        <String, Object?>{
          if (deviceUUID != null) 'deviceUuid': deviceUUID,
        },
      );
    } on PlatformException catch (e) {
      throw _mapPlatformException(e);
    }
  }

  @override
  Future<void> resumeStreamSession({String? deviceUUID}) async {
    try {
      await methodChannel.invokeMethod<void>(
        'resumeStreamSession',
        <String, Object?>{
          if (deviceUUID != null) 'deviceUuid': deviceUUID,
        },
      );
    } on PlatformException catch (e) {
      throw _mapPlatformException(e);
    }
  }

  // --- Streaming streams ----------------------------------------------------

  @override
  Stream<StreamSessionState> streamSessionStateStream() {
    return _streamSessionStateStream ??=
        streamSessionStateChannel.receiveBroadcastStream().map((event) => StreamSessionState.fromInt(event as int?));
  }

  @override
  Stream<Object> streamSessionErrorStream() {
    return _streamSessionErrorStream ??=
        streamSessionErrorsChannel.receiveBroadcastStream().map(_mapStreamSessionError);
  }

  @override
  Stream<DeviceSessionState> deviceSessionStateStream() {
    return _deviceSessionStateStream ??=
        deviceSessionStateChannel.receiveBroadcastStream().map((event) => DeviceSessionState.fromInt(event as int?));
  }

  @override
  Stream<Object> deviceSessionErrorStream() {
    return _deviceSessionErrorStream ??=
        deviceSessionErrorsChannel.receiveBroadcastStream().map(_mapDeviceSessionError);
  }

  @override
  Stream<VideoStreamSize> videoStreamSizeStream() {
    return _videoStreamSizeStream ??= videoStreamSizeChannel
        .receiveBroadcastStream()
        .map((event) => VideoStreamSize.fromMap(event as Map<Object?, Object?>))
        .map((size) {
      _lastVideoStreamSize = size;
      return size;
    });
  }

  @override
  Stream<VideoFrame> videoFramesStream() {
    return _videoFramesStream ??=
        videoFramesChannel.receiveBroadcastStream().map((event) => VideoFrame.fromMap(event as Map<Object?, Object?>));
  }

  @override
  Future<void> enableBackgroundStreaming({
    BackgroundNotification? androidNotification,
  }) async {
    try {
      await methodChannel.invokeMethod<void>(
        'enableBackgroundStreaming',
        <String, Object?>{
          if (androidNotification != null) 'androidNotification': androidNotification.toMap(),
        },
      );
    } on PlatformException catch (e) {
      throw _mapPlatformException(e);
    }
  }

  @override
  Future<void> disableBackgroundStreaming() async {
    try {
      await methodChannel.invokeMethod<void>('disableBackgroundStreaming');
    } on PlatformException catch (e) {
      throw _mapPlatformException(e);
    }
  }

  // --- Display --------------------------------------------------------------

  @override
  Future<void> startDisplaySession({String? deviceUUID}) async {
    _ensureDisplayEventsListening();
    try {
      await methodChannel.invokeMethod<void>(
        'startDisplaySession',
        <String, Object?>{
          if (deviceUUID != null) 'deviceUuid': deviceUUID,
        },
      );
    } on PlatformException catch (e) {
      throw _mapPlatformException(e);
    }
  }

  @override
  Future<void> sendDisplayView(DisplayView view) async {
    _ensureDisplayEventsListening();
    final table = DisplayCallbackTable();
    final json = view.toJson(table);
    // Replace the live callback table so events for the previous view stop
    // resolving once the new view is on screen.
    _displayCallbacks = table;
    try {
      await methodChannel.invokeMethod<void>(
        'sendDisplayView',
        <String, Object?>{'view': json},
      );
    } on PlatformException catch (e) {
      throw _mapPlatformException(e);
    }
  }

  @override
  Future<void> stopDisplaySession() async {
    try {
      await methodChannel.invokeMethod<void>('stopDisplaySession');
    } on PlatformException catch (e) {
      throw _mapPlatformException(e);
    }
    _displayCallbacks = null;
  }

  @override
  Stream<DisplayState> displayStateStream() {
    return _displayStateStream ??=
        displayStateChannel.receiveBroadcastStream().map((event) => DisplayState.fromInt(event as int?));
  }

  /// Lazily subscribes to the `display_events` channel and forwards every
  /// event to the live [DisplayCallbackTable]. Idempotent.
  void _ensureDisplayEventsListening() {
    _displayEventsSubscription ??= displayEventsChannel.receiveBroadcastStream().listen((event) {
      if (event is Map) {
        _displayCallbacks?.dispatch(event.cast<Object?, Object?>());
      }
    });
  }

  // --- Photo capture --------------------------------------------------------

  @override
  Future<PhotoResult> capturePhoto({
    String? deviceUUID,
    PhotoFormat format = PhotoFormat.jpeg,
  }) async {
    try {
      final result = await methodChannel.invokeMethod<Map<Object?, Object?>>('capturePhoto', <String, Object?>{
        if (deviceUUID != null) 'deviceUuid': deviceUUID,
        'format': format.name,
      });
      if (result == null) {
        throw const CaptureError(
          code: DatErrorCodes.capture,
          message: 'capturePhoto returned null',
        );
      }
      final bytes = result['bytes'];
      final formatName = result['format'] as String? ?? format.name;
      final byteList = switch (bytes) {
        final Uint8List u => u,
        final List<int> l => Uint8List.fromList(l),
        _ => Uint8List(0),
      };
      return PhotoResult(
        bytes: byteList,
        format: formatName == 'heic' ? PhotoFormat.heic : PhotoFormat.jpeg,
      );
    } on PlatformException catch (e) {
      throw _mapPlatformException(e);
    }
  }

  // --- Frame capture --------------------------------------------------------

  @override
  Future<FrameData?> captureStreamFrame(
    int textureId, {
    FrameFormat format = FrameFormat.rawRgba,
  }) async {
    final size = _lastVideoStreamSize ?? const VideoStreamSize(width: 1280, height: 720);
    final width = size.width;
    final height = size.height;
    if (width <= 0 || height <= 0) return null;

    ui.Scene? scene;
    ui.Image? image;
    try {
      final builder = ui.SceneBuilder()
        ..pushOffset(0, 0)
        ..addTexture(
          textureId,
          width: width.toDouble(),
          height: height.toDouble(),
        )
        ..pop();
      scene = builder.build();
      image = await scene.toImage(width, height);

      final byteFormat = switch (format) {
        FrameFormat.png => ui.ImageByteFormat.png,
        FrameFormat.rawStraightRgba => ui.ImageByteFormat.rawStraightRgba,
        FrameFormat.rawRgba => ui.ImageByteFormat.rawRgba,
        // JPEG is only produced by the native captureLatestFrame path; the
        // Dart texture rasterizer cannot emit JPEG, so fall back to PNG.
        FrameFormat.jpeg => ui.ImageByteFormat.png,
      };
      final byteData = await image.toByteData(format: byteFormat);
      if (byteData == null) {
        throw const CaptureError(
          code: DatErrorCodes.capture,
          message: 'ui.Image.toByteData returned null',
        );
      }
      return FrameData(
        bytes: byteData.buffer.asUint8List(
          byteData.offsetInBytes,
          byteData.lengthInBytes,
        ),
        width: width,
        height: height,
        format: format,
      );
    } catch (e) {
      if (e is DatError) rethrow;
      throw CaptureError(
        code: DatErrorCodes.capture,
        message: 'captureStreamFrame failed: $e',
      );
    } finally {
      image?.dispose();
      scene?.dispose();
    }
  }

  @override
  Future<FrameData?> captureLatestFrame({double quality = 0.8}) async {
    try {
      final bytes = await methodChannel.invokeMethod<Uint8List>(
        'captureLatestFrame',
        <String, Object?>{'quality': quality},
      );
      if (bytes == null || bytes.isEmpty) return null;
      final size = _lastVideoStreamSize;
      return FrameData(
        bytes: bytes,
        width: size?.width ?? 0,
        height: size?.height ?? 0,
        format: FrameFormat.jpeg,
      );
    } on PlatformException catch (e) {
      throw CaptureError(
        code: DatErrorCodes.capture,
        message: 'captureLatestFrame failed: ${e.message}',
      );
    }
  }

  // --- Mock device control --------------------------------------------------

  @override
  Future<void> enableMockDevice({
    bool initiallyRegistered = true,
    bool initialPermissionsGranted = true,
  }) async {
    try {
      await methodChannel.invokeMethod<void>(
        'enableMockDevice',
        <String, Object?>{
          'initiallyRegistered': initiallyRegistered,
          'initialPermissionsGranted': initialPermissionsGranted,
        },
      );
    } on PlatformException catch (e) {
      throw _mapPlatformException(e);
    }
  }

  @override
  Future<void> disableMockDevice() async {
    try {
      await methodChannel.invokeMethod<void>('disableMockDevice');
    } on PlatformException catch (e) {
      throw _mapPlatformException(e);
    }
  }

  @override
  Future<bool> isMockDeviceEnabled() async {
    try {
      final enabled = await methodChannel.invokeMethod<bool>(
        'isMockDeviceEnabled',
      );
      return enabled ?? false;
    } on PlatformException catch (e) {
      throw _mapPlatformException(e);
    }
  }

  @override
  Future<String> pairMockRayBanMeta() async {
    try {
      final uuid = await methodChannel.invokeMethod<String>('pairMockRayBanMeta');
      return uuid ?? '';
    } on PlatformException catch (e) {
      throw _mapPlatformException(e);
    }
  }

  @override
  Future<List<DeviceInfo>> pairedMockDevices() async {
    try {
      final raw = await methodChannel.invokeMethod<List<Object?>>(
        'pairedMockDevices',
      );
      if (raw == null) return const [];
      return raw.map((e) => DeviceInfo.fromMap(e! as Map<Object?, Object?>)).toList(growable: false);
    } on PlatformException catch (e) {
      throw _mapPlatformException(e);
    }
  }

  @override
  Future<void> unpairMockDevice(String uuid) async {
    try {
      await methodChannel.invokeMethod<void>(
        'unpairMockDevice',
        <String, Object?>{'uuid': uuid},
      );
    } on PlatformException catch (e) {
      throw _mapPlatformException(e);
    }
  }

  @override
  Future<void> mockPowerOn(String uuid) async {
    await _mockUuidVoid('mockPowerOn', uuid);
  }

  @override
  Future<void> mockPowerOff(String uuid) async {
    await _mockUuidVoid('mockPowerOff', uuid);
  }

  @override
  Future<void> mockDon(String uuid) async {
    await _mockUuidVoid('mockDon', uuid);
  }

  @override
  Future<void> mockDoff(String uuid) async {
    await _mockUuidVoid('mockDoff', uuid);
  }

  @override
  Future<void> mockFold(String uuid) async {
    await _mockUuidVoid('mockFold', uuid);
  }

  @override
  Future<void> mockUnfold(String uuid) async {
    await _mockUuidVoid('mockUnfold', uuid);
  }

  Future<void> _mockUuidVoid(String method, String uuid) async {
    try {
      await methodChannel.invokeMethod<void>(
        method,
        <String, Object?>{'uuid': uuid},
      );
    } on PlatformException catch (e) {
      throw _mapPlatformException(e);
    }
  }

  @override
  Future<void> setMockCameraFacing(String uuid, CameraFacing facing) async {
    try {
      await methodChannel.invokeMethod<void>(
        'setMockCameraFacing',
        <String, Object?>{'uuid': uuid, 'facing': facing.name},
      );
    } on PlatformException catch (e) {
      throw _mapPlatformException(e);
    }
  }

  @override
  Future<void> setMockCameraFeed(String uuid, String? filePath) async {
    try {
      await methodChannel.invokeMethod<void>(
        'setMockCameraFeed',
        <String, Object?>{'uuid': uuid, 'filePath': filePath},
      );
    } on PlatformException catch (e) {
      throw _mapPlatformException(e);
    }
  }

  @override
  Future<void> setMockCapturedImage(String uuid, String? filePath) async {
    try {
      await methodChannel.invokeMethod<void>(
        'setMockCapturedImage',
        <String, Object?>{'uuid': uuid, 'filePath': filePath},
      );
    } on PlatformException catch (e) {
      throw _mapPlatformException(e);
    }
  }

  @override
  Future<void> setMockPermission(String permission, String status) async {
    try {
      await methodChannel.invokeMethod<void>(
        'setMockPermission',
        <String, Object?>{'permission': permission, 'status': status},
      );
    } on PlatformException catch (e) {
      throw _mapPlatformException(e);
    }
  }

  @override
  Future<void> setMockPermissionRequestResult(
    String permission,
    String status,
  ) async {
    try {
      await methodChannel.invokeMethod<void>(
        'setMockPermissionRequestResult',
        <String, Object?>{'permission': permission, 'status': status},
      );
    } on PlatformException catch (e) {
      throw _mapPlatformException(e);
    }
  }

  // --- Mock devices stream --------------------------------------------------

  @override
  Stream<List<DeviceInfo>> mockDevicesStream() {
    return _mockDevicesStream ??= mockDevicesChannel.receiveBroadcastStream().map((event) {
      final list = (event as List<Object?>?) ?? const [];
      return list.map((e) => DeviceInfo.fromMap(e! as Map<Object?, Object?>)).toList(growable: false);
    });
  }

  // --- Helpers --------------------------------------------------------------

  /// Maps a [PlatformException] thrown from the platform channel to the
  /// most specific [DatError] subclass we have for its `code`. Anything
  /// unrecognised passes through as a base [DatError].
  static DatError _mapPlatformException(PlatformException e) {
    final code = e.code;
    final message = e.message ?? '';
    final details = e.details;
    switch (code) {
      case DatErrorCodes.registration:
        return RegistrationError(
          code: code,
          message: message,
          details: details,
        );
      case DatErrorCodes.unregistration:
        return UnregistrationError(
          code: code,
          message: message,
          details: details,
        );
      case DatErrorCodes.handleUrl:
        return HandleUrlError(code: code, message: message, details: details);
      case DatErrorCodes.permission:
      case DatErrorCodes.missingFragmentActivity:
        return PermissionError(code: code, message: message, details: details);
      case DatErrorCodes.deviceSession:
        return DeviceSessionError(
          code: code,
          message: message,
          details: details,
        );
      case DatErrorCodes.session:
        return SessionError(code: code, message: message, details: details);
      case DatErrorCodes.capture:
        return CaptureError(code: code, message: message, details: details);
      case _:
        return DatError(code: code, message: message, details: details);
    }
  }

  /// Maps a `stream_session_errors` channel event into a typed
  /// [SessionError]. The map shape is `{code, message, details?}` where
  /// `code` is the typed sub-code (e.g. `thermalCritical`).
  static DatError _mapStreamSessionError(Object? event) {
    final map = event as Map<Object?, Object?>? ?? const {};
    final code = map['code'] as String? ?? DatErrorCodes.session;
    final message = map['message'] as String? ?? '';
    final details = map['details'];
    return SessionError(code: code, message: message, details: details);
  }

  /// Maps a `device_session_errors` channel event into a typed
  /// [DeviceSessionError].
  static DatError _mapDeviceSessionError(Object? event) {
    final map = event as Map<Object?, Object?>? ?? const {};
    final code = map['code'] as String? ?? DatErrorCodes.unexpectedError;
    final message = map['message'] as String? ?? '';
    final details = map['details'];
    return DeviceSessionError(code: code, message: message, details: details);
  }
}
