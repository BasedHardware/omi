import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

import 'package:crypto/crypto.dart' as crypto;
import 'package:meta_wearables_dat_flutter/meta_wearables_dat_flutter.dart';

import 'package:path_provider/path_provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/capture/capture_controller.dart';
import 'package:omi/services/devices/meta_wearables_service.dart';
import 'package:omi/services/meta_wearables/meta_capture_diagnostics.dart';
import 'package:omi/services/meta_wearables/meta_capture_queue.dart';
import 'package:omi/services/meta_wearables/meta_capture_watchdog.dart';
import 'package:omi/utils/enums.dart';
import 'package:omi/utils/logger.dart';

/// How connected Meta glasses feed the capture pipeline.
///
/// The DAT SDK exposes camera streaming only in this integration; Meta capture
/// history is cached from glasses frames and does not start the phone mic.
enum MetaGlassesCaptureMode {
  /// Periodic camera frames cached into conversation history.
  cameraAndMic,

  /// Legacy setting. DAT mic capture is not available here, so this starts no
  /// phone audio.
  micOnly;

  static MetaGlassesCaptureMode fromName(String? name) {
    return MetaGlassesCaptureMode.values.firstWhere((m) => m.name == name, orElse: () => cameraAndMic);
  }
}

/// User-selectable interval between automatic camera captures in Camera+Mic
/// mode.
enum MetaGlassesCaptureInterval {
  s10(Duration(seconds: 10)),
  s30(Duration(seconds: 30)),
  m1(Duration(minutes: 1)),
  m5(Duration(minutes: 5));

  const MetaGlassesCaptureInterval(this.duration);
  final Duration duration;

  static MetaGlassesCaptureInterval fromName(String? name) {
    return MetaGlassesCaptureInterval.values.firstWhere((m) => m.name == name, orElse: () => s30);
  }
}

enum MetaGlassesHealth {
  ok,
  overheating,
  foldedClosed;

  static MetaGlassesHealth? fromSessionError(Object error) {
    if (error is SessionError) {
      if (error.isThermalCritical) return MetaGlassesHealth.overheating;
      if (error.isHingesClosed) return MetaGlassesHealth.foldedClosed;
    }
    if (error is DatError) {
      if (error.code == DatErrorCodes.thermalCritical) return MetaGlassesHealth.overheating;
      if (error.code == DatErrorCodes.hingesClosed) return MetaGlassesHealth.foldedClosed;
    }
    return null;
  }
}

/// App-level state for Meta glasses connected through the Wearables Device
/// Access Toolkit. Runs alongside [DeviceProvider] so a BLE wearable and one
/// or more Meta glasses can be connected at the same time (multi-device).
///
/// Multi-device model: the DAT SDK reports every glasses paired to this phone
/// via `devicesStream()`. The user may pick which pair is "active" for
/// streaming/photo sessions; per-device sessions are addressed by
/// `DeviceInfo.uuid`.
class MetaWearablesProvider extends ChangeNotifier {
  static const String _selectedDeviceUuidPrefKey = 'metaWearablesSelectedDeviceUuid';

  /// Native audio-session bridge (AppDelegate `com.omi.ios/audioSession`):
  /// Meta capture uses `configureForMediaSafeCapture`; other recorder flows
  /// may still opt into the coupled Bluetooth HFP route.
  static const MethodChannel _audioSessionChannel = MethodChannel('com.omi.ios/audioSession');

  /// Native gesture bridge (AppDelegate `com.omi/meta_gestures`). Glasses
  /// stalk taps arrive as Bluetooth media-remote commands; only delivered
  /// while capture holds the audio session and Now Playing. Tap = toggle
  /// capture — the one honest gesture the transport can carry.
  static const MethodChannel _gesturesChannel = MethodChannel('com.omi/meta_gestures');
  static const Duration _gestureDebounce = Duration(milliseconds: 1500);

  /// Claiming the Bluetooth route fires a phantom AVRCP `pause` at the new
  /// Now Playing app ~400ms after listening starts (observed on-device
  /// 2026-07-05: listening-started 15:34:36.566 → pause .972 → capture
  /// toggled itself off). Discard anything inside this window.
  static const Duration _gestureActivationGrace = Duration(seconds: 3);
  static const String _captureModePrefKey = 'metaGlassesCaptureMode';
  static const String _autoCapturePrefKey = 'metaGlassesAutoCapture';
  static const String _captureIntervalPrefKey = 'metaGlassesCaptureInterval';
  static const Duration _displayUpdateThrottle = Duration(seconds: 2);
  static const bool _advancedDisplayUiEnabled = false;

  // Background capture streams video frames from the glasses (native-pushed,
  // works while backgrounded). Run at the lowest DAT frame rate (2 fps) to keep
  // the per-frame copy cheap; medium quality so stored frames are viewable
  // (low/360p looked bad).
  static const int _photoSessionFps = 2;
  static const StreamQuality _photoSessionQuality = StreamQuality.medium;

  // Bound the on-disk photo backlog (oldest dropped first).
  static const int _maxQueuedPhotos = 200;
  static const int _runtimeProofLogMaxBytes = 64 * 1024;
  static const Duration _watchdogFrameGrace = Duration(seconds: 10);
  static const Duration _watchdogStreamFrameStaleThreshold = Duration(seconds: 20);
  static const Duration _firstQueuedFrameStartTimeout = Duration(seconds: 12);

  final MetaWearablesService _service;

  MetaWearablesProvider({MetaWearablesService service = const MetaWearablesService()}) : _service = service;

  RegistrationState registrationState = RegistrationState.unavailable;
  List<DeviceInfo> devices = [];
  DeviceInfo? _sdkActiveDevice;
  String? _selectedDeviceUuid;
  MetaGlassesCameraPermissionState cameraPermissionState = MetaGlassesCameraPermissionState.unavailable;
  StreamSessionState streamSessionState = StreamSessionState.stopped;
  DeviceSessionState deviceSessionState = DeviceSessionState.idle;
  bool isRegistering = false;
  String? lastError;
  MetaGlassesHealth health = MetaGlassesHealth.ok;

  MetaGlassesCaptureMode captureMode = MetaGlassesCaptureMode.cameraAndMic;
  MetaGlassesCaptureInterval captureInterval = MetaGlassesCaptureInterval.s30;
  bool isCapturing = false;
  CaptureController? _captureController;
  Timer? _thermalRetryTimer;

  // Background capture: one continuous never-paused stream session. The DAT
  // videoFramesStream (native-pushed) is the capture trigger — it keeps firing
  // while backgrounded, unlike a Dart timer. Each frame event keeps the SDK's
  // latestPixelBuffer fresh; we encode one viewable JPEG from it natively at
  // most once per [captureInterval] via captureLatestFrame.
  StreamSubscription<VideoFrame>? _frameSub;
  DateTime? _lastFrameForwardedAt;
  DateTime? _lastStreamFrameEventAt;
  DateTime? _lastPhotoLoopStartedAt;
  DateTime? _lastQueuedPhotoAt;
  Completer<bool>? _firstQueuedFrameCompleter;
  int _streamGeneration = 0;
  bool _frameForwardInFlight = false;
  int? _frameForwardInFlightGeneration;
  final MetaCaptureWatchdog _captureWatchdog = MetaCaptureWatchdog();
  Timer? _captureWatchdogTimer;
  bool _captureWatchdogTimerIsRestart = false;
  bool _captureWatchdogRestartInFlight = false;
  @visibleForTesting
  void Function(MetaCaptureHealth health, Duration delay)? debugOnCaptureWatchdogRestartScheduled;

  // videoStreamingError recovery (bounded).
  int streamFailureCount = 0;
  bool micOnlyFallback = false;
  Timer? _streamRetryTimer;
  Timer? _autoStartRetryTimer;
  static const Duration _notReadyRefreshInterval = Duration(seconds: 2);
  Timer? _notReadyRefreshTimer;
  bool _notReadyRefreshInFlight = false;

  Duration get _photoInterval => captureInterval.duration;
  Duration get _watchdogStaleFrameThreshold => _photoInterval + _watchdogFrameGrace;

  /// Camera wearable capture must be explicit opt-in.
  bool autoCaptureEnabled = false;
  bool _autoStartInFlight = false;

  /// A user-initiated stop must stay stopped: auto-capture may not undo it
  /// until the glasses go away and come back (a fresh session intent), the
  /// user starts capture again, or re-enables auto-capture.
  bool _manualStopRequested = false;
  bool _thermalPaused = false;
  bool _livePreviewVisible = false;
  bool _photoLoopStarting = false;

  /// Serializes start/stop so button taps can't interleave two transitions.
  bool _captureTransitionInFlight = false;

  /// Last gesture received from the native media-remote bridge (diagnostics).
  String? lastGesture;
  DateTime? _lastGestureAt;
  DateTime? _gestureListeningStartedAt;
  bool _gestureHandlerInstalled = false;

  /// Store-and-forward photo queue: every still lands on disk first and is
  /// only deleted after the backend confirms transmission over the socket.
  Directory? _photoQueueDir;
  MetaCaptureQueue? _metaCaptureQueue;
  File? _runtimeProofLogFile;
  int pendingPhotoCount = 0;
  MetaCaptureDiagnostics diagnostics = const MetaCaptureDiagnostics();
  DateTime? _lastDiagnosticsLogAt;
  bool _flushingQueue = false;
  final Set<String> _photosShownInUi = {};

  /// Live camera preview texture while a camera session runs, for `Texture`.
  int? previewTextureId;
  double previewAspectRatio = 4 / 3;

  /// Latest per-device compatibility verdicts (firmware/SDK update needed).
  final Map<String, DeviceCompatibility> compatibilityByUuid = {};

  bool _displaySessionActive = false;
  String _displayStatusText = 'Listening';
  CaptureController? _displayCaptureController;
  Timer? _displayUpdateTimer;
  DateTime? _lastDisplayUpdateAt;

  StreamSubscription<RegistrationState>? _registrationSub;
  StreamSubscription<List<DeviceInfo>>? _devicesSub;
  StreamSubscription<DeviceInfo?>? _activeDeviceSub;
  StreamSubscription<DeviceCompatibilityEvent>? _compatibilitySub;
  StreamSubscription<VideoStreamSize>? _videoSizeSub;
  StreamSubscription<StreamSessionState>? _streamStateSub;
  StreamSubscription<DeviceSessionState>? _deviceStateSub;
  StreamSubscription<Object>? _streamErrorSub;
  StreamSubscription<Object>? _deviceErrorSub;
  StreamSubscription<DisplayState>? _displayStateSub;
  bool _initialized = false;
  bool _initialRefreshComplete = false;

  bool get isRegistered => registrationState == RegistrationState.registered;
  bool get isAvailable => registrationState != RegistrationState.unavailable;
  bool get hasDevices => devices.isNotEmpty;
  bool get cameraPermissionGranted => cameraPermissionState == MetaGlassesCameraPermissionState.granted;
  bool get isRequestingCameraPermission => cameraPermissionState == MetaGlassesCameraPermissionState.requesting;
  bool get isStreamPaused => streamSessionState == StreamSessionState.paused;
  bool get isDeviceSessionPaused => deviceSessionState == DeviceSessionState.paused;
  bool get advancedDisplayUiEnabled => _advancedDisplayUiEnabled;
  bool get canShowDisplayStatus => selectedDevice?.kind == DeviceKind.rayBanDisplay;
  bool get _cameraStreamNeeded => captureMode == MetaGlassesCaptureMode.cameraAndMic;
  bool get _cameraCaptureStreamReady =>
      previewTextureId != null && _frameSub != null && _lastQueuedPhotoAt != null && !micOnlyFallback;

  static DisplayView buildDisplayCaptureView({
    required String captureStateLine,
    List<TranscriptSegment> segments = const <TranscriptSegment>[],
  }) {
    final snippet = _latestDisplaySnippet(segments);
    return FlexBox(
      padding: 16,
      spacing: 8,
      children: [
        DisplayText(captureStateLine, style: DisplayTextStyle.heading),
        if (snippet != null) DisplayText(snippet, style: DisplayTextStyle.body, color: DisplayTextColor.secondary),
      ],
    );
  }

  static String? _latestDisplaySnippet(List<TranscriptSegment> segments) {
    for (final segment in segments.reversed) {
      final text = segment.text.trim();
      if (text.isNotEmpty) return _truncateDisplayText(text);
    }
    return null;
  }

  static String _truncateDisplayText(String text) {
    const maxChars = 80;
    if (text.length <= maxChars) return text;
    return '${text.substring(0, maxChars - 3).trimRight()}...';
  }

  /// Devices whose Bluetooth link is live (or reported by an older native
  /// layer that predates link states). Sessions only work against these.
  List<DeviceInfo> get linkedDevices =>
      devices.where((d) => d.linkState == DeviceLinkState.connected || d.linkState == DeviceLinkState.unknown).toList();

  bool get hasLinkedDevices => linkedDevices.isNotEmpty;

  bool get _activeDeviceIsSessionCandidate {
    final linkState = _sdkActiveDevice?.linkState;
    return linkState == DeviceLinkState.connected || linkState == DeviceLinkState.unknown;
  }

  bool get _hasSessionCandidateDevice => hasLinkedDevices || _activeDeviceIsSessionCandidate;

  /// The glasses sessions target: the user's explicit pick when it is still
  /// paired, otherwise whatever the SDK reports as active, otherwise the
  /// first paired pair.
  DeviceInfo? get selectedDevice {
    if (_selectedDeviceUuid != null) {
      for (final device in devices) {
        if (device.uuid == _selectedDeviceUuid) return device;
      }
    }
    // Prefer the sanitized-list instance for the SDK-active device; a shadow
    // record that got filtered out must not resurface here.
    final activeUuid = _sdkActiveDevice?.uuid;
    if (activeUuid != null) {
      for (final device in devices) {
        if (device.uuid == activeUuid) return device;
      }
    }
    if (devices.isNotEmpty) return devices.first;
    return _sdkActiveDevice;
  }

  /// Device uuid to pass to session APIs. Prefer a user-selected or DAT-active
  /// pair that the SDK currently reports; the iOS auto selector can return
  /// `noEligibleDevice` while link-state streams are still catching up.
  String? get _sessionTargetUuid {
    final linked = linkedDevices;
    final selectedUuid = _selectedDeviceUuid;
    if (selectedUuid != null && linked.any((d) => d.uuid == selectedUuid)) return selectedUuid;
    final activeUuid = _sdkActiveDevice?.uuid;
    if (activeUuid != null &&
        _activeDeviceIsSessionCandidate &&
        (devices.isEmpty || devices.any((d) => d.uuid == activeUuid))) {
      return activeUuid;
    }
    if (linked.length == 1) return linked.first.uuid;
    return null;
  }

  bool isSelected(DeviceInfo device) => selectedDevice?.uuid == device.uuid;

  bool isActive(DeviceInfo device) => _sdkActiveDevice?.uuid == device.uuid;

  Future<void> init() async {
    if (_initialized) return;
    _initialized = true;

    final storedUuid = SharedPreferencesUtil().getString(_selectedDeviceUuidPrefKey);
    _selectedDeviceUuid = storedUuid.isEmpty ? null : storedUuid;
    captureMode = MetaGlassesCaptureMode.fromName(SharedPreferencesUtil().getString(_captureModePrefKey));
    captureInterval = MetaGlassesCaptureInterval.fromName(SharedPreferencesUtil().getString(_captureIntervalPrefKey));
    autoCaptureEnabled = SharedPreferencesUtil().getBool(_autoCapturePrefKey);
    try {
      final docs = await getApplicationDocumentsDirectory();
      final dir = Directory('${docs.path}/meta_glasses_photo_queue');
      if (!dir.existsSync()) dir.createSync(recursive: true);
      _photoQueueDir = dir;
      _metaCaptureQueue = MetaCaptureQueue(rootDirectory: dir);
      _runtimeProofLogFile = File('${docs.path}/meta_glasses_runtime_proof.log');
      _appendRuntimeProof('MetaGlassRuntimeProof provider-init');
      await _refreshPendingPhotoCount();
    } catch (e) {
      Logger.debug('MetaWearablesProvider: photo queue dir unavailable: $e');
    }

    _registrationSub = _service.registrationStateStream().listen((state) {
      registrationState = state;
      if (state != RegistrationState.registering) isRegistering = false;
      _appendRuntimeProof('MetaGlassRuntimeProof registration-state state=$state');
      notifyListeners();
      _maybeAutoStartCapture();
    }, onError: (Object e) => Logger.debug('MetaWearablesProvider registration stream error: $e'));

    _devicesSub = _service.devicesStream().listen((rawList) {
      final deviceList = sanitizeDevices(rawList);
      final hadDevices = devices.isNotEmpty;
      devices = deviceList;
      final deviceStates = deviceList.map((d) => '${d.uuid}:${d.linkState.name}').join(',');
      _appendRuntimeProof(
          'MetaGlassRuntimeProof devices count=${deviceList.length} selected=$_selectedDeviceUuid linked=$hasLinkedDevices candidate=$_hasSessionCandidateDevice states=$deviceStates');
      // A persisted selection pointing at a device the SDK no longer reports
      // (stale shadow record) would make every session start fail — drop it.
      if (_selectedDeviceUuid != null &&
          deviceList.isNotEmpty &&
          !deviceList.any((d) => d.uuid == _selectedDeviceUuid)) {
        _selectedDeviceUuid = null;
        SharedPreferencesUtil().saveString(_selectedDeviceUuidPrefKey, '');
      }
      notifyListeners();
      if (deviceList.isEmpty && hadDevices) {
        // Glasses gone (powered off / out of range) — wind the session down;
        // auto-capture brings it back when they reappear. A prior manual stop
        // no longer applies to the next appearance.
        _manualStopRequested = false;
        if (isCapturing) stopCapture(manual: false);
      } else {
        _maybeAutoStartCapture();
      }
    }, onError: (Object e) => Logger.debug('MetaWearablesProvider devices stream error: $e'));

    _activeDeviceSub = _service.activeDeviceStream().listen((device) {
      _sdkActiveDevice = device;
      _appendRuntimeProof('MetaGlassRuntimeProof active-device uuid=${device?.uuid ?? 'none'}');
      notifyListeners();
      _maybeAutoStartCapture();
    }, onError: (Object e) => Logger.debug('MetaWearablesProvider active device stream error: $e'));

    _compatibilitySub = MetaWearablesDat.compatibilityStream().listen((event) {
      compatibilityByUuid[event.deviceUuid] = event.compatibility;
      notifyListeners();
    }, onError: (Object e) => Logger.debug('MetaWearablesProvider compatibility stream error: $e'));

    _videoSizeSub = MetaWearablesDat.videoStreamSizeStream().listen((size) {
      if (size.width > 0 && size.height > 0) {
        previewAspectRatio = size.width / size.height;
        notifyListeners();
      }
    }, onError: (Object e) => Logger.debug('MetaWearablesProvider video size stream error: $e'));

    _streamStateSub = MetaWearablesDat.streamSessionStateStream().listen(
      _handleStreamSessionState,
      onError: (Object e) => Logger.debug('MetaWearablesProvider stream state sub failed: $e'),
    );

    _deviceStateSub = MetaWearablesDat.deviceSessionStateStream().listen(
      _handleDeviceSessionState,
      onError: (Object e) => Logger.debug('MetaWearablesProvider device state sub failed: $e'),
    );

    _streamErrorSub = MetaWearablesDat.streamSessionErrorStream().listen(
      (error) => unawaited(_handleSessionError(error)),
      onError: (Object e) => Logger.debug('MetaWearablesProvider stream error sub failed: $e'),
    );

    _deviceErrorSub = MetaWearablesDat.deviceSessionErrorStream().listen(
      (error) => unawaited(_handleSessionError(error)),
      onError: (Object e) => Logger.debug('MetaWearablesProvider device error sub failed: $e'),
    );

    await refresh();
    _initialRefreshComplete = true;
    _maybeAutoStartCapture();
  }

  /// Compatibility verdict for [device], if the SDK has reported one.
  DeviceCompatibility compatibilityFor(DeviceInfo device) {
    return compatibilityByUuid[device.uuid] ?? DeviceCompatibility.unknown;
  }

  bool hasCompatibilityUpdateAction(DeviceInfo device) {
    final compatibility = compatibilityFor(device);
    return compatibility == DeviceCompatibility.deviceUpdateRequired ||
        compatibility == DeviceCompatibility.sdkUpdateRequired;
  }

  Future<void> openCompatibilityUpdate(DeviceInfo device) async {
    try {
      switch (compatibilityFor(device)) {
        case DeviceCompatibility.deviceUpdateRequired:
          await _service.openFirmwareUpdate();
          break;
        case DeviceCompatibility.sdkUpdateRequired:
          await _service.openDATGlassesAppUpdate();
          break;
        case DeviceCompatibility.compatible:
        case DeviceCompatibility.unknown:
          return;
      }
    } catch (e) {
      Logger.debug('MetaWearablesProvider open compatibility update failed: $e');
      lastError = e.toString();
      notifyListeners();
    }
  }

  /// The DAT SDK can report the same physical glasses twice: once with the
  /// user-visible name (e.g. "000R") and once as a shadow record whose "name"
  /// is a long identifier. Collapse uuid duplicates and drop identifier-named
  /// shadows whenever a properly named device exists — but never filter down
  /// to nothing.
  @visibleForTesting
  static List<DeviceInfo> sanitizeDevices(List<DeviceInfo> raw) {
    final byUuid = <String, DeviceInfo>{};
    for (final device in raw) {
      final existing = byUuid[device.uuid];
      if (existing == null || (!_hasHumanName(existing) && _hasHumanName(device))) {
        byUuid[device.uuid] = device;
      }
    }
    final deduped = byUuid.values.toList();
    final named = deduped.where(_hasHumanName).toList();
    return named.isNotEmpty ? named : deduped;
  }

  static final RegExp _identifierLikeName = RegExp(r'^[0-9A-Fa-f:-]{16,}$');

  static bool _hasHumanName(DeviceInfo device) {
    final name = device.name.trim();
    if (name.isEmpty) return false;
    if (name == device.uuid) return false;
    if (_identifierLikeName.hasMatch(name)) return false;
    // Long unbroken blobs (base64-ish session ids) are artifacts, not names.
    if (name.length >= 24 && !name.contains(' ')) return false;
    return true;
  }

  Future<void> refresh() async {
    try {
      final snapshot = await _service.snapshot();
      registrationState = snapshot.registrationState;
      devices = sanitizeDevices(snapshot.devices);
      _sdkActiveDevice = snapshot.activeDevice;
      cameraPermissionState = snapshot.cameraPermissionState;
      lastError = null;
    } catch (e) {
      Logger.debug('MetaWearablesProvider refresh failed: $e');
      lastError = e.toString();
    }
    notifyListeners();
  }

  /// Deep-links into the Meta AI app to register this app with the user's
  /// glasses. Registration completes when the omimeta:// callback comes back.
  Future<bool> startRegistration() async {
    if (isRegistering) return false;
    isRegistering = true;
    lastError = null;
    notifyListeners();
    try {
      await _service.startPairing();
      await refresh();
      return isRegistered;
    } catch (e) {
      Logger.debug('MetaWearablesProvider startRegistration failed: $e');
      lastError = e.toString();
      return false;
    } finally {
      isRegistering = false;
      notifyListeners();
    }
  }

  Future<void> unregister() async {
    try {
      await _service.forgetLocalRegistration();
    } catch (e) {
      Logger.debug('MetaWearablesProvider unregister failed: $e');
      lastError = e.toString();
    }
    _selectedDeviceUuid = null;
    await SharedPreferencesUtil().saveString(_selectedDeviceUuidPrefKey, '');
    await refresh();
  }

  /// Picks which paired glasses future sessions target. Persisted so the
  /// choice survives app restarts.
  Future<void> selectDevice(String uuid) async {
    _selectedDeviceUuid = uuid;
    await SharedPreferencesUtil().saveString(_selectedDeviceUuidPrefKey, uuid);
    notifyListeners();
  }

  Future<bool> requestCameraPermission() async {
    cameraPermissionState = MetaGlassesCameraPermissionState.requesting;
    notifyListeners();
    try {
      final granted = await _service.requestCameraPermission();
      cameraPermissionState =
          granted ? MetaGlassesCameraPermissionState.granted : MetaGlassesCameraPermissionState.needsRequest;
    } catch (e) {
      Logger.debug('MetaWearablesProvider camera permission failed: $e');
      lastError = e.toString();
      cameraPermissionState = MetaGlassesCameraPermissionState.unavailable;
    }
    await refresh();
    return cameraPermissionGranted;
  }

  /// Starts a preview stream on the selected glasses; returns the Flutter
  /// texture id, or null on failure.
  Future<int?> startPreview() async {
    final device = selectedDevice;
    try {
      final textureId = await _service.startPreviewStream(deviceUUID: device?.uuid);
      previewTextureId = textureId;
      notifyListeners();
      return textureId;
    } catch (e) {
      Logger.debug('MetaWearablesProvider startPreview failed: $e');
      lastError = e.toString();
      notifyListeners();
      return null;
    }
  }

  Future<void> stopPreview() async {
    final device = selectedDevice;
    try {
      await _service.stopPreviewStream(deviceUUID: device?.uuid);
    } catch (e) {
      Logger.debug('MetaWearablesProvider stopPreview failed: $e');
    }
  }

  BtDevice? get selectedBtDevice {
    final device = selectedDevice;
    if (device == null) return null;
    return _service.toBtDevice(device);
  }

  // --- Capture (Camera+Mic / Mic only) --------------------------------------

  /// Wires the app-level capture pipeline in (from a ProxyProvider in
  /// main.dart), enabling gesture- and auto-started capture without any page
  /// visit — the glasses behave like a built-in app.
  void attachCaptureController(CaptureController controller) {
    _captureController = controller;
    _maybeAutoStartCapture();
  }

  Future<void> setAutoCaptureEnabled(bool enabled) async {
    autoCaptureEnabled = enabled;
    if (enabled) _manualStopRequested = false;
    await SharedPreferencesUtil().saveBool(_autoCapturePrefKey, enabled);
    notifyListeners();
    _maybeAutoStartCapture();
  }

  /// Starts capture hands-free when registered glasses are present, the
  /// pipeline is attached, and nothing else is recording.
  Future<void> _maybeAutoStartCapture() async {
    if (!autoCaptureEnabled) {
      _cancelNotReadyRefresh();
      _appendRuntimeProof('MetaGlassRuntimeProof auto-start-skip reason=disabled');
      return;
    }
    if (isCapturing) {
      _cancelNotReadyRefresh();
      _appendRuntimeProof('MetaGlassRuntimeProof auto-start-skip reason=already-capturing');
      return;
    }
    if (_autoStartInFlight) {
      _appendRuntimeProof('MetaGlassRuntimeProof auto-start-skip reason=in-flight');
      return;
    }
    if (_captureTransitionInFlight) {
      _appendRuntimeProof('MetaGlassRuntimeProof auto-start-skip reason=transitioning');
      return;
    }
    if (_manualStopRequested) {
      _cancelNotReadyRefresh();
      _appendRuntimeProof('MetaGlassRuntimeProof auto-start-skip reason=manual-stop');
      return;
    }
    if (!_initialRefreshComplete) {
      _appendRuntimeProof('MetaGlassRuntimeProof auto-start-skip reason=initial-refresh');
      return;
    }
    if (!isRegistered || !_hasSessionCandidateDevice) {
      _appendRuntimeProof(
          'MetaGlassRuntimeProof auto-start-skip reason=not-ready registered=$isRegistered linked=$hasLinkedDevices devices=${devices.length} active=${_sdkActiveDevice?.uuid ?? 'none'}');
      _scheduleNotReadyRefresh();
      return;
    }
    _cancelNotReadyRefresh();
    final controller = _captureController;
    if (controller == null) {
      _cancelNotReadyRefresh();
      _appendRuntimeProof('MetaGlassRuntimeProof auto-start-skip reason=no-capture-controller');
      return;
    }
    // Don't fight another active recording source (BLE wearable, phone mic).
    if (controller.recordingState != RecordingState.stop) {
      _cancelNotReadyRefresh();
      _appendRuntimeProof(
          'MetaGlassRuntimeProof auto-start-skip reason=recording-state state=${controller.recordingState}');
      return;
    }
    _autoStartInFlight = true;
    try {
      Logger.debug('MetaWearablesProvider: auto-starting glasses capture');
      _appendRuntimeProof(
          'MetaGlassRuntimeProof auto-starting target=${_sessionTargetUuid ?? 'auto'} linked=$hasLinkedDevices devices=${devices.length}');
      final started = await startCapture(controller);
      if (!started) {
        _appendRuntimeProof('MetaGlassRuntimeProof auto-start-failed');
        _scheduleAutoStartRetry();
      }
    } finally {
      _autoStartInFlight = false;
    }
  }

  bool get _shouldPollNotReady =>
      _initialized &&
      _initialRefreshComplete &&
      autoCaptureEnabled &&
      !isCapturing &&
      !_autoStartInFlight &&
      !_captureTransitionInFlight &&
      !_manualStopRequested &&
      isRegistered &&
      devices.isNotEmpty &&
      !_hasSessionCandidateDevice &&
      _captureController != null &&
      _captureController?.recordingState == RecordingState.stop;

  void _scheduleNotReadyRefresh() {
    if (_notReadyRefreshTimer != null || !_shouldPollNotReady) return;
    _appendRuntimeProof(
        'MetaGlassRuntimeProof not-ready-refresh-scheduled interval=${_notReadyRefreshInterval.inSeconds}s');
    _notReadyRefreshTimer = Timer.periodic(_notReadyRefreshInterval, (_) {
      unawaited(_refreshNotReadyDevices());
    });
  }

  void _scheduleAutoStartRetry() {
    if (_autoStartRetryTimer?.isActive == true) return;
    _appendRuntimeProof('MetaGlassRuntimeProof auto-start-retry-scheduled');
    _autoStartRetryTimer = Timer(_notReadyRefreshInterval, () {
      _autoStartRetryTimer = null;
      unawaited(_maybeAutoStartCapture());
    });
  }

  void _cancelNotReadyRefresh() {
    final timer = _notReadyRefreshTimer;
    if (timer == null) return;
    timer.cancel();
    _notReadyRefreshTimer = null;
    _appendRuntimeProof('MetaGlassRuntimeProof not-ready-refresh-cancelled');
  }

  void _cancelAutoStartRetry() {
    _autoStartRetryTimer?.cancel();
    _autoStartRetryTimer = null;
  }

  Future<void> _refreshNotReadyDevices() async {
    if (!_shouldPollNotReady) {
      _cancelNotReadyRefresh();
      return;
    }
    if (_notReadyRefreshInFlight) return;

    _notReadyRefreshInFlight = true;
    try {
      _appendRuntimeProof('MetaGlassRuntimeProof not-ready-refresh');
      await refresh();
      if (_hasSessionCandidateDevice) {
        _cancelNotReadyRefresh();
      }
      await _maybeAutoStartCapture();
    } catch (error, stackTrace) {
      Logger.error('Meta glasses not-ready refresh failed: $error\n$stackTrace');
      _appendRuntimeProof('MetaGlassRuntimeProof not-ready-refresh-error error=$error');
    } finally {
      _notReadyRefreshInFlight = false;
    }
  }

  Future<void> setCaptureMode(MetaGlassesCaptureMode mode) async {
    if (captureMode == mode) return;
    captureMode = mode;
    await SharedPreferencesUtil().saveString(_captureModePrefKey, mode.name);
    // Apply live when a capture session is running.
    if (isCapturing) {
      if (_cameraStreamNeeded) {
        await _startPhotoLoop();
      } else {
        _thermalPaused = false;
        _thermalRetryTimer?.cancel();
        _thermalRetryTimer = null;
        await _stopPhotoLoop();
      }
    }
    notifyListeners();
  }

  /// How often Camera+Mic mode forwards a frame from the continuous stream to
  /// the conversation. Applies live: the frame throttle reads [captureInterval]
  /// directly, so the next forwarded frame uses the new cadence.
  Future<void> setCaptureInterval(MetaGlassesCaptureInterval interval) async {
    if (captureInterval == interval) return;
    captureInterval = interval;
    await SharedPreferencesUtil().saveString(_captureIntervalPrefKey, interval.name);
    _cancelCaptureWatchdogTimer();
    _evaluateCaptureWatchdog();
    notifyListeners();
  }

  void setLivePreviewVisible(bool visible) {
    if (_livePreviewVisible == visible) return;
    _livePreviewVisible = visible;
    notifyListeners();
  }

  /// Starts glasses capture: DAT camera frames and media-safe phone-mic audio
  /// share the transcription socket without taking over Bluetooth playback.
  ///
  /// [displayStatusText] is rendered on Ray-Ban Display glasses while
  /// capturing; pass a localized string from the UI.
  Future<bool> startCapture(CaptureController captureController, {String? displayStatusText}) async {
    if (isCapturing || _captureTransitionInFlight) return isCapturing;
    if (!isRegistered) return false;
    _captureTransitionInFlight = true;
    _manualStopRequested = false;
    _captureController = captureController;
    if (displayStatusText != null && displayStatusText.isNotEmpty) _displayStatusText = displayStatusText;
    lastError = null;
    // Fresh capture intent — reset the stream-error recovery budget and the
    // watchdog restart backoff (a previous session's failures must not
    // penalize this one with a 32s first-restart delay).
    streamFailureCount = 0;
    micOnlyFallback = false;
    _captureWatchdog.reset();

    try {
      try {
        await MetaWearablesDat.enableBackgroundStreaming();
      } catch (e) {
        Logger.debug('MetaGlassStreamDiag: enableBackgroundStreaming failed: $e');
      }

      _appendRuntimeProof(
          'MetaGlassRuntimeProof start-capture captureMode=${captureMode.name} cameraNeeded=$_cameraStreamNeeded cameraPermission=$cameraPermissionState gestures=media-remote');

      if (_cameraStreamNeeded) {
        await _startPhotoLoop();
        final firstFrameQueued = await _waitForFirstQueuedFrame();
        if (!_cameraCaptureStreamReady || !firstFrameQueued) {
          _appendRuntimeProof('MetaGlassRuntimeProof start-capture-failed reason=camera-stream-not-ready');
          await _stopPhotoLoop();
          try {
            await MetaWearablesDat.disableBackgroundStreaming();
          } catch (e) {
            Logger.debug('MetaWearablesProvider: disableBackgroundStreaming failed after start failure: $e');
          }
          notifyListeners();
          return false;
        }
      } else {
        _appendRuntimeProof('MetaGlassStreamDiag start-photo-loop skipped captureMode=${captureMode.name}');
      }

      // HFP couples the glasses mic and speaker routes. Record from the iPhone
      // built-in mic instead, keep the glasses on A2DP, then open the shared
      // transcription socket for STT audio and image_chunk photo uploads.
      Map<String, String>? route;
      try {
        route = await _audioSessionChannel.invokeMapMethod<String, String>('configureForMediaSafeCapture');
      } catch (e) {
        Logger.debug('MetaGlassStreamDiag: configureForMediaSafeCapture failed: $e');
      }
      await captureController.streamRecording();
      final input = route?['input'] ?? 'unknown';
      final output = route?['output'] ?? 'unknown';
      _appendRuntimeProof('MetaGlassRuntimeProof audio-stream-started input=$input output=$output');

      await _startGestureListening();

      await _startDisplayStatus();

      _cancelAutoStartRetry();
      isCapturing = true;
      _evaluateCaptureWatchdog();
      notifyListeners();
      // Push any photos buffered while offline into the fresh session.
      unawaited(flushPhotoQueue());
      return true;
    } finally {
      _captureTransitionInFlight = false;
    }
  }

  /// [manual] marks a user-initiated stop (button), which
  /// suppresses auto-capture from immediately restarting the session.
  /// Internal teardown (glasses disappearing) passes false so capture
  /// resumes when they come back.
  Future<void> stopCapture({bool manual = true}) async {
    if (!isCapturing || _captureTransitionInFlight) return;
    _captureTransitionInFlight = true;
    if (manual) _manualStopRequested = true;
    try {
      _cancelAutoStartRetry();
      _thermalPaused = false;
      _thermalRetryTimer?.cancel();
      _thermalRetryTimer = null;
      health = MetaGlassesHealth.ok;
      await _stopGestureListening();
      await _stopPhotoLoop();
      try {
        await _captureController?.stopStreamRecording();
      } catch (e) {
        Logger.debug('MetaGlassStreamDiag: stopStreamRecording failed: $e');
      }
      await _stopDisplayStatus();
      try {
        await MetaWearablesDat.disableBackgroundStreaming();
      } catch (e) {
        Logger.debug('MetaWearablesProvider: disableBackgroundStreaming failed: $e');
      }
      isCapturing = false;
      notifyListeners();
    } finally {
      _captureTransitionInFlight = false;
    }
  }

  /// Installs the Dart side of the media-remote gesture bridge and tells the
  /// native side to claim Now Playing + remote commands. Only meaningful
  /// while capture holds the audio session.
  Future<void> _startGestureListening() async {
    if (!Platform.isIOS) return;
    if (!_gestureHandlerInstalled) {
      _gesturesChannel.setMethodCallHandler((call) async {
        if (call.method == 'onGesture') {
          final args = (call.arguments as Map?)?.cast<String, dynamic>() ?? const {};
          _handleGesture(args['type'] as String? ?? 'tap', args['command'] as String? ?? '');
        }
        return null;
      });
      _gestureHandlerInstalled = true;
    }
    try {
      await _gesturesChannel.invokeMethod('startListening');
      _gestureListeningStartedAt = DateTime.now();
      _appendRuntimeProof('MetaGlassGestureDiag listening-started');
    } catch (e) {
      Logger.debug('MetaGlassGestureDiag: startListening failed: $e');
    }
  }

  Future<void> _stopGestureListening() async {
    if (!Platform.isIOS) return;
    try {
      await _gesturesChannel.invokeMethod('stopListening');
      _appendRuntimeProof('MetaGlassGestureDiag listening-stopped');
    } catch (e) {
      Logger.debug('MetaGlassGestureDiag: stopListening failed: $e');
    }
  }

  /// Tap = toggle capture. Media-remote events often double-fire (play +
  /// togglePlayPause for one physical tap), so collapse anything inside the
  /// debounce window into one action.
  void _handleGesture(String type, String command) {
    final now = DateTime.now();
    final last = _lastGestureAt;
    _appendRuntimeProof('MetaGlassGestureDiag received type=$type command=$command');
    final listeningSince = _gestureListeningStartedAt;
    if (listeningSince != null && now.difference(listeningSince) < _gestureActivationGrace) {
      _appendRuntimeProof('MetaGlassGestureDiag discarded-phantom command=$command '
          'ageMs=${now.difference(listeningSince).inMilliseconds}');
      return;
    }
    if (last != null && now.difference(last) < _gestureDebounce) {
      Logger.debug('MetaGlassGestureDiag: debounced $command');
      return;
    }
    _lastGestureAt = now;
    lastGesture = command.isEmpty ? type : command;
    notifyListeners();
    final controller = _captureController;
    if (isCapturing) {
      unawaited(stopCapture());
    } else if (controller != null) {
      unawaited(startCapture(controller));
    }
  }

  /// Renders a small status view on Ray-Ban Display glasses while capturing.
  Future<void> _startDisplayStatus() async {
    if (!canShowDisplayStatus) return;
    try {
      _displayStateSub ??= MetaWearablesDat.displayStateStream().listen(
        _handleDisplayState,
        onError: (Object e) => Logger.debug('MetaWearablesProvider display state sub failed: $e'),
      );
      _attachDisplayCaptureListener();
      await MetaWearablesDat.startDisplaySession(deviceUUID: selectedDevice?.uuid);
    } catch (e) {
      Logger.debug('MetaWearablesProvider: display session unavailable: $e');
    }
  }

  Future<void> _stopDisplayStatus() async {
    final hadDisplaySession = _displaySessionActive ||
        _displayStateSub != null ||
        _displayCaptureController != null ||
        _displayUpdateTimer != null;
    if (!hadDisplaySession) return;
    _displaySessionActive = false;
    _displayUpdateTimer?.cancel();
    _displayUpdateTimer = null;
    _lastDisplayUpdateAt = null;
    _detachDisplayCaptureListener();
    await _displayStateSub?.cancel();
    _displayStateSub = null;
    try {
      await MetaWearablesDat.stopDisplaySession();
    } catch (e) {
      Logger.debug('MetaWearablesProvider: stopDisplaySession failed: $e');
    }
  }

  void _handleDisplayState(DisplayState state) {
    switch (state) {
      case DisplayState.started:
        _displaySessionActive = true;
        updateDisplayFromCapture();
        break;
      case DisplayState.stopped:
        _displaySessionActive = false;
        _displayUpdateTimer?.cancel();
        _displayUpdateTimer = null;
        break;
      case DisplayState.starting:
      case DisplayState.stopping:
        break;
    }
  }

  void _attachDisplayCaptureListener() {
    final controller = _captureController;
    if (_displayCaptureController == controller) return;
    _detachDisplayCaptureListener();
    _displayCaptureController = controller;
    _captureController?.addListener(_handleCaptureDisplayChanged);
  }

  void _detachDisplayCaptureListener() {
    _displayCaptureController?.removeListener(_handleCaptureDisplayChanged);
    _displayCaptureController = null;
  }

  void _handleCaptureDisplayChanged() {
    if (!_displaySessionActive) return;
    final now = DateTime.now();
    final last = _lastDisplayUpdateAt;
    if (last == null || now.difference(last) >= _displayUpdateThrottle) {
      _displayUpdateTimer?.cancel();
      _displayUpdateTimer = null;
      updateDisplayFromCapture();
      return;
    }
    _displayUpdateTimer ??= Timer(_displayUpdateThrottle - now.difference(last), () {
      _displayUpdateTimer = null;
      if (_displaySessionActive) updateDisplayFromCapture();
    });
  }

  void updateDisplayFromCapture() {
    if (!_displaySessionActive) return;
    _lastDisplayUpdateAt = DateTime.now();
    unawaited(_sendDisplayCaptureView());
  }

  Future<void> _sendDisplayCaptureView() async {
    try {
      await MetaWearablesDat.sendDisplayView(
        buildDisplayCaptureView(
          captureStateLine: _displayStatusText,
          segments: _captureController?.segments ?? const <TranscriptSegment>[],
        ),
      );
    } catch (e) {
      Logger.debug('MetaWearablesProvider: send display view failed: $e');
    }
  }

  Future<bool> _waitForFirstQueuedFrame() async {
    final completer = _firstQueuedFrameCompleter;
    if (completer == null) return _lastQueuedPhotoAt != null;
    try {
      return await completer.future.timeout(_firstQueuedFrameStartTimeout, onTimeout: () => false);
    } catch (_) {
      return false;
    }
  }

  /// Starts (once) a continuous, never-paused camera stream and subscribes to
  /// the DAT videoFramesStream as a background-capable capture trigger.
  ///
  /// No shutter/snapshot cadence: the stream runs continuously and frame events
  /// are native-pushed (they keep firing while backgrounded via
  /// enableBackgroundStreaming, unlike a Dart timer which suspends). Each event
  /// keeps the SDK's latestPixelBuffer fresh; at most once per [captureInterval]
  /// we encode one viewable JPEG from that buffer natively (on the CPU) via
  /// [MetaWearablesDat.captureLatestFrame]. The native CPU encode works
  /// backgrounded, unlike the Flutter-texture rasterizer.
  Future<void> _startPhotoLoop() async {
    _appendRuntimeProof(
        'MetaGlassStreamDiag start-photo-loop cameraPermission=$cameraPermissionState granted=$cameraPermissionGranted texture=$previewTextureId frameSub=${_frameSub != null}');
    if (_photoLoopStarting) {
      _appendRuntimeProof('MetaGlassStreamDiag start-photo-loop skipped already-starting');
      return;
    }
    if (_frameSub != null && previewTextureId != null) {
      _appendRuntimeProof('MetaGlassStreamDiag start-photo-loop skipped already-streaming');
      return;
    }
    if (!cameraPermissionGranted) {
      if (cameraPermissionState == MetaGlassesCameraPermissionState.needsRequest) {
        _appendRuntimeProof('MetaGlassStreamDiag start-photo-loop requesting-camera-permission');
        await requestCameraPermission();
      } else if (cameraPermissionState == MetaGlassesCameraPermissionState.unavailable && _hasSessionCandidateDevice) {
        _appendRuntimeProof(
            'MetaGlassStreamDiag start-photo-loop permission-unavailable-continuing devices=${devices.length} active=${_sdkActiveDevice?.uuid ?? 'none'}');
      }
      if (!cameraPermissionGranted &&
          !(cameraPermissionState == MetaGlassesCameraPermissionState.unavailable && _hasSessionCandidateDevice)) {
        Logger.debug('MetaWearablesProvider: camera permission missing, glasses camera capture unavailable');
        _appendRuntimeProof(
            'MetaGlassStreamDiag start-photo-loop camera-unavailable cameraPermission=$cameraPermissionState');
        micOnlyFallback = true;
        notifyListeners();
        return;
      }
    }
    _photoLoopStarting = true;
    try {
      final textureId = await _service.startPreviewStream(
        deviceUUID: _sessionTargetUuid,
        fps: _photoSessionFps,
        quality: _photoSessionQuality,
      );
      previewTextureId = textureId;
      micOnlyFallback = false;
      _lastFrameForwardedAt = null;
      _lastPhotoLoopStartedAt = DateTime.now();
      _lastQueuedPhotoAt = null;
      _firstQueuedFrameCompleter = Completer<bool>();
      Logger.debug('MetaGlassStreamDiag: stream session started (interval=${_photoInterval.inSeconds}s)');
      _appendRuntimeProof(
          'MetaGlassStreamDiag stream-started interval=${_photoInterval.inSeconds}s texture=$textureId');
      await _frameSub?.cancel();
      // videoFramesStream = native-pushed trigger (works backgrounded). We don't
      // encode the raw frame here; we use the event to pull an SDK-encoded frame.
      final listenerGeneration = _streamGeneration;
      _frameSub = _service.videoFrames().listen(
        (frame) => _onVideoFrame(frame, listenerGeneration),
        onError: (Object e) {
          if (listenerGeneration != _streamGeneration) {
            _appendRuntimeProof('MetaGlassStreamDiag frame-error-stale $e');
            return;
          }
          Logger.debug('MetaGlassStreamDiag: frame stream error $e');
          _appendRuntimeProof('MetaGlassStreamDiag frame-error $e');
          unawaited(recoverFromVideoStreamingError(e));
        },
      );
      notifyListeners();
    } catch (e) {
      Logger.debug('MetaGlassStreamDiag: stream session start failed $e');
      _appendRuntimeProof('MetaGlassStreamDiag stream-start-failed $e');
      if (_firstQueuedFrameCompleter?.isCompleted == false) _firstQueuedFrameCompleter?.complete(false);
      await recoverFromVideoStreamingError(e);
    } finally {
      _photoLoopStarting = false;
    }
  }

  void _onVideoFrame(VideoFrame frame, int listenerGeneration) {
    if (listenerGeneration != _streamGeneration) {
      _appendRuntimeProof('MetaGlassStreamDiag frame-event-stale $frame');
      return;
    }
    final now = DateTime.now();
    _lastStreamFrameEventAt = now;
    _evaluateCaptureWatchdog(now: now);
    _appendRuntimeProof('MetaGlassStreamDiag frame-event $frame');
    final last = _lastFrameForwardedAt;
    if (last != null && now.difference(last) < _photoInterval) return;
    if (_frameForwardInFlight) return;
    _lastFrameForwardedAt = now;
    unawaited(_captureFrame());
  }

  /// Encodes one viewable JPEG from the SDK's latest decoded pixel buffer
  /// (natively, on the CPU) and queues it.
  ///
  /// Uses [MetaWearablesDat.captureLatestFrame], NOT the Flutter-texture
  /// rasterizer (`captureStreamFrame` → `ui.Scene.toImage`). The texture path
  /// depends on the GPU raster pipeline, which iOS suspends when the app is
  /// backgrounded — that produced blank/garbled captures and "nothing captured"
  /// while locked. The native encode reads the SDK's cached frame and runs on
  /// the CPU, so it keeps working backgrounded.
  Future<void> _captureFrame() async {
    if (previewTextureId == null || _frameForwardInFlight) return;
    final generation = _streamGeneration;
    _frameForwardInFlight = true;
    _frameForwardInFlightGeneration = generation;
    try {
      final frame = await MetaWearablesDat.captureLatestFrame(quality: 0.8);
      if (generation != _streamGeneration) {
        _appendRuntimeProof('MetaGlassStreamDiag frame-drop-generation');
        return;
      }
      if (frame == null || frame.bytes.isEmpty) {
        Logger.debug('MetaGlassStreamDiag: captureLatestFrame returned no frame');
        _appendRuntimeProof('MetaGlassStreamDiag frame-empty');
        if (_firstQueuedFrameCompleter?.isCompleted == false) _firstQueuedFrameCompleter?.complete(false);
        await recoverFromVideoStreamingError('captureLatestFrameEmpty');
        return;
      }
      Logger.debug('MetaGlassStreamDiag: captured frame ${frame.bytes.length}B');
      _appendRuntimeProof('MetaGlassStreamDiag frame-captured bytes=${frame.bytes.length}');
      if (generation != _streamGeneration || previewTextureId == null || _frameSub == null) {
        _appendRuntimeProof('MetaGlassStreamDiag frame-drop-stopped');
        if (_firstQueuedFrameCompleter?.isCompleted == false) _firstQueuedFrameCompleter?.complete(false);
        return;
      }
      final queued = await _enqueuePhoto(frame.bytes);
      if (!queued) {
        _updateCaptureDiagnostics(
          lastUploadAt: DateTime.now(),
          lastUploadStatus: 'enqueue_failed',
          failedUploadCount: diagnostics.failedUploadCount + 1,
        );
        if (_firstQueuedFrameCompleter?.isCompleted == false) _firstQueuedFrameCompleter?.complete(false);
        await recoverFromVideoStreamingError('photoEnqueueFailed');
        return;
      }
      _lastQueuedPhotoAt = DateTime.now();
      if (_firstQueuedFrameCompleter?.isCompleted == false) _firstQueuedFrameCompleter?.complete(true);
      _updateCaptureDiagnostics(
        lastFrameAt: _lastQueuedPhotoAt,
        lastUploadStatus: 'frame_enqueued',
        pendingQueueCount: pendingPhotoCount,
      );
      if (!isCapturing ||
          !_cameraStreamNeeded ||
          _captureWatchdogPaused ||
          micOnlyFallback ||
          previewTextureId == null) {
        return;
      }
      _cancelCaptureWatchdogTimer();
      _markHealthRecovered();
      _captureWatchdog.recordHealthyFrame();
      streamFailureCount = 0;
      unawaited(flushPhotoQueue());
    } catch (e) {
      Logger.debug('MetaGlassStreamDiag: captureLatestFrame failed $e');
      _appendRuntimeProof('MetaGlassStreamDiag frame-capture-failed $e');
      if (_firstQueuedFrameCompleter?.isCompleted == false) _firstQueuedFrameCompleter?.complete(false);
      await recoverFromVideoStreamingError(e);
    } finally {
      if (_frameForwardInFlightGeneration == generation) {
        _frameForwardInFlight = false;
        _frameForwardInFlightGeneration = null;
      }
    }
  }

  Future<void> _stopPhotoLoop() async {
    _livePreviewVisible = false;
    _cancelCaptureWatchdogTimer();
    await _frameSub?.cancel();
    _frameSub = null;
    _streamRetryTimer?.cancel();
    _streamRetryTimer = null;
    _releaseStreamResources();
    notifyListeners();
    await stopPreview();
  }

  void _handleStreamSessionState(StreamSessionState state) {
    streamSessionState = state;
    _updateCaptureDiagnostics(streamState: state.name);
    switch (state) {
      case StreamSessionState.paused:
      case StreamSessionState.stopped:
        break;
      case StreamSessionState.waitingForDevice:
      case StreamSessionState.starting:
      case StreamSessionState.streaming:
      case StreamSessionState.stopping:
        break;
    }
    _evaluateCaptureWatchdog();
    notifyListeners();
  }

  void _handleDeviceSessionState(DeviceSessionState state) {
    deviceSessionState = state;
    _updateCaptureDiagnostics(sessionState: state.name);
    switch (state) {
      case DeviceSessionState.paused:
      case DeviceSessionState.stopping:
        break;
      case DeviceSessionState.stopped:
        _releaseStreamResources();
        break;
      case DeviceSessionState.idle:
      case DeviceSessionState.starting:
      case DeviceSessionState.started:
        final restartStream = _thermalPaused && isCapturing && _cameraStreamNeeded;
        _markHealthRecovered();
        if (restartStream) unawaited(_startPhotoLoop());
        break;
    }
    _evaluateCaptureWatchdog();
    notifyListeners();
  }

  bool get _captureWatchdogPaused => isStreamPaused || isDeviceSessionPaused || _thermalPaused;

  MetaCaptureHealth _deriveCaptureHealth({DateTime? now}) {
    final checkedAt = now ?? DateTime.now();
    if (_captureWatchdogPaused) return MetaCaptureHealth.paused;
    if (!isCapturing || !_cameraStreamNeeded) return MetaCaptureHealth.streaming;
    if (previewTextureId == null || _frameSub == null) return MetaCaptureHealth.stopped;
    if (streamSessionState == StreamSessionState.stopped || deviceSessionState == DeviceSessionState.stopped) {
      return MetaCaptureHealth.stopped;
    }

    final lastStreamFrameEventAt = _lastStreamFrameEventAt;
    if (lastStreamFrameEventAt != null &&
        checkedAt.difference(lastStreamFrameEventAt) >= _watchdogStreamFrameStaleThreshold) {
      return MetaCaptureHealth.stale;
    }

    final startedAt = _lastPhotoLoopStartedAt;
    if (lastStreamFrameEventAt == null &&
        startedAt != null &&
        checkedAt.difference(startedAt) >= _watchdogStreamFrameStaleThreshold) {
      return MetaCaptureHealth.stale;
    }

    final lastQueuedAt = _lastQueuedPhotoAt;
    if (lastQueuedAt != null) {
      return checkedAt.difference(lastQueuedAt) >= _watchdogStaleFrameThreshold
          ? MetaCaptureHealth.stale
          : MetaCaptureHealth.streaming;
    }

    if (startedAt != null && checkedAt.difference(startedAt) >= _watchdogStaleFrameThreshold) {
      return MetaCaptureHealth.stale;
    }
    return MetaCaptureHealth.streaming;
  }

  Duration _timeUntilStale(DateTime? since, Duration threshold, DateTime now) {
    if (since == null) return threshold;
    final remaining = threshold - now.difference(since);
    return remaining <= Duration.zero ? const Duration(milliseconds: 1) : remaining;
  }

  Duration _nextCaptureWatchdogCheckDelay(DateTime now) {
    final streamSince = _lastStreamFrameEventAt ?? _lastPhotoLoopStartedAt;
    final captureSince = _lastQueuedPhotoAt ?? _lastPhotoLoopStartedAt;
    final streamDelay = _timeUntilStale(streamSince, _watchdogStreamFrameStaleThreshold, now);
    final captureDelay = _timeUntilStale(captureSince, _watchdogStaleFrameThreshold, now);
    return streamDelay < captureDelay ? streamDelay : captureDelay;
  }

  /// Re-arms the watchdog while it cannot act (retry pending, paused,
  /// mic-only). Suspended timers fire on foreground resume, so a session that
  /// died while the app was backgrounded recovers on the next foreground
  /// instead of staying dead until relaunch.
  void _scheduleWatchdogRecheck({required String reason}) {
    _cancelCaptureWatchdogTimer();
    _appendRuntimeProof('MetaGlassWatchdog wait reason=$reason recheck=10s');
    _captureWatchdogTimerIsRestart = false;
    _captureWatchdogTimer = Timer(const Duration(seconds: 10), () {
      _captureWatchdogTimer = null;
      _evaluateCaptureWatchdog();
    });
  }

  void _evaluateCaptureWatchdog({DateTime? now}) {
    if (!isCapturing || !_cameraStreamNeeded || !_hasSessionCandidateDevice) {
      _cancelCaptureWatchdogTimer();
      return;
    }
    if (micOnlyFallback || _streamRetryTimer?.isActive == true) {
      // Never go dormant: a suspension mid-retry froze the retry timer while
      // the watchdog had cancelled itself, leaving capture dead until app
      // relaunch (observed on-device 2026-07-05). Re-check instead.
      _scheduleWatchdogRecheck(reason: micOnlyFallback ? 'micOnlyFallback' : 'streamRetry');
      return;
    }

    final checkedAt = now ?? DateTime.now();
    final health = _deriveCaptureHealth(now: checkedAt);
    if (health == MetaCaptureHealth.paused) {
      _scheduleWatchdogRecheck(reason: 'paused');
      return;
    }

    if (_captureWatchdog.nextAction(health) == MetaCaptureWatchdogAction.restart) {
      if (_captureWatchdogRestartInFlight ||
          (_captureWatchdogTimer?.isActive == true && _captureWatchdogTimerIsRestart)) {
        return;
      }
      _cancelCaptureWatchdogTimer();
      final delay = _captureWatchdog.nextDelay(health);
      _captureWatchdogTimerIsRestart = true;
      _appendRuntimeProof('MetaGlassWatchdog schedule-restart health=${health.name} delay=${delay.inSeconds}s');
      debugOnCaptureWatchdogRestartScheduled?.call(health, delay);
      _captureWatchdogTimer = Timer(delay, () {
        _captureWatchdogTimer = null;
        _captureWatchdogTimerIsRestart = false;
        unawaited(_restartDatCameraSession(health));
      });
      return;
    }

    if (_captureWatchdogTimer?.isActive == true && !_captureWatchdogTimerIsRestart) return;
    _cancelCaptureWatchdogTimer();
    _captureWatchdogTimerIsRestart = false;
    _captureWatchdogTimer = Timer(_nextCaptureWatchdogCheckDelay(checkedAt), () {
      _captureWatchdogTimer = null;
      _evaluateCaptureWatchdog();
    });
  }

  @visibleForTesting
  void debugSetCaptureWatchdogStateForTest({
    required bool isCapturing,
    required StreamSessionState streamSessionState,
    required DeviceSessionState deviceSessionState,
    required bool hasPreviewTexture,
    required bool hasFrameSubscription,
    MetaGlassesCaptureMode captureMode = MetaGlassesCaptureMode.cameraAndMic,
    MetaGlassesCaptureInterval captureInterval = MetaGlassesCaptureInterval.s30,
    DateTime? lastPhotoLoopStartedAt,
    DateTime? lastQueuedPhotoAt,
    DateTime? lastStreamFrameEventAt,
    bool hasSessionCandidateDevice = true,
    bool thermalPaused = false,
    bool micOnlyFallback = false,
    bool streamRetryScheduled = false,
  }) {
    _cancelCaptureWatchdogTimer();
    _streamRetryTimer?.cancel();
    _streamRetryTimer = null;
    this.isCapturing = isCapturing;
    this.captureMode = captureMode;
    this.captureInterval = captureInterval;
    this.streamSessionState = streamSessionState;
    this.deviceSessionState = deviceSessionState;
    _thermalPaused = thermalPaused;
    this.micOnlyFallback = micOnlyFallback;
    if (streamRetryScheduled) {
      _streamRetryTimer = Timer(const Duration(minutes: 1), () {});
    }
    previewTextureId = hasPreviewTexture ? 1 : null;
    _lastPhotoLoopStartedAt = lastPhotoLoopStartedAt;
    _lastQueuedPhotoAt = lastQueuedPhotoAt;
    _lastStreamFrameEventAt = lastStreamFrameEventAt;
    devices = hasSessionCandidateDevice
        ? const [
            DeviceInfo(
              uuid: 'watchdog-test-device',
              name: 'Watchdog Test Device',
              kind: DeviceKind.rayBanMeta,
              linkState: DeviceLinkState.connected,
            ),
          ]
        : const [];
    unawaited(_frameSub?.cancel());
    _frameSub = hasFrameSubscription ? const Stream<VideoFrame>.empty().listen((_) {}) : null;
  }

  @visibleForTesting
  void debugEvaluateCaptureWatchdogForTest({
    DateTime? now,
    void Function(MetaCaptureHealth health, Duration delay)? onRestartScheduled,
  }) {
    debugOnCaptureWatchdogRestartScheduled = onRestartScheduled;
    _evaluateCaptureWatchdog(now: now);
  }

  @visibleForTesting
  void debugHandleStreamSessionStateForTest(StreamSessionState state) {
    _handleStreamSessionState(state);
  }

  @visibleForTesting
  bool get debugHasCaptureWatchdogTimerForTest => _captureWatchdogTimer?.isActive == true;

  Future<void> _restartDatCameraSession(MetaCaptureHealth health) async {
    if (_captureWatchdogRestartInFlight || !isCapturing || !_cameraStreamNeeded || _captureWatchdogPaused) return;
    _captureWatchdogRestartInFlight = true;
    _captureWatchdog.recordRestartAttempt();
    _appendRuntimeProof('MetaGlassWatchdog restart health=${health.name}');
    _updateCaptureDiagnostics(lastUploadStatus: 'watchdog_restart_${health.name}');
    try {
      _releaseStreamResources();
      await stopPreview();
      if (!isCapturing || !_cameraStreamNeeded || _captureWatchdogPaused || micOnlyFallback) return;
      await _startPhotoLoop();
    } finally {
      _captureWatchdogRestartInFlight = false;
      _evaluateCaptureWatchdog();
    }
  }

  void _cancelCaptureWatchdogTimer() {
    _captureWatchdogTimer?.cancel();
    _captureWatchdogTimer = null;
    _captureWatchdogTimerIsRestart = false;
  }

  void _updateCaptureDiagnostics({
    DateTime? lastFrameAt,
    DateTime? lastUploadAt,
    String? lastUploadStatus,
    String? streamState,
    String? sessionState,
    int? pendingQueueCount,
    int? uploadedCount,
    int? failedUploadCount,
  }) {
    diagnostics = diagnostics.copyWith(
      lastFrameAt: lastFrameAt,
      lastUploadAt: lastUploadAt,
      lastUploadStatus: lastUploadStatus,
      streamState: streamState,
      sessionState: sessionState,
      pendingQueueCount: pendingQueueCount,
      uploadedCount: uploadedCount,
      failedUploadCount: failedUploadCount,
    );
    final now = DateTime.now();
    final lastLogAt = _lastDiagnosticsLogAt;
    if (lastLogAt != null && now.difference(lastLogAt) < const Duration(seconds: 5)) return;
    _lastDiagnosticsLogAt = now;
    Logger.debug('Meta capture diagnostics: ${diagnostics.toJson()}');
  }

  Future<void> _handleSessionError(Object error) async {
    Logger.debug('MetaGlassStreamDiag: session error $error');
    final nextHealth = MetaGlassesHealth.fromSessionError(error);
    if (nextHealth == null) {
      // Generic/transient stream error (incl. videoStreamingError). Recover the
      // camera stream without a raw user-facing error.
      await recoverFromVideoStreamingError(error);
      return;
    }

    lastError = error.toString();
    health = nextHealth;
    if (nextHealth == MetaGlassesHealth.overheating) {
      _thermalPaused = true;
      _releaseStreamResources();
      _scheduleThermalRetry();
    } else {
      _releaseStreamResources();
    }
    notifyListeners();
  }

  /// Bounded recovery for `SessionError(videoStreamingError)` and other
  /// transient stream failures. Tears down the camera stream, retries once, then
  /// stops this glasses-only capture and schedules auto-start recovery.
  Future<void> recoverFromVideoStreamingError(Object error) async {
    final isStreamError =
        error is SessionError ? error.isVideoStreamingError : error.toString().contains('videoStreamingError');
    streamFailureCount++;
    Logger.debug('MetaGlassStreamDiag: recoverFromVideoStreamingError count=$streamFailureCount stream=$isStreamError');
    _appendRuntimeProof('MetaGlassStreamDiag recover count=$streamFailureCount stream=$isStreamError error=$error');

    // Tear down the camera stream. This glasses-only path does not use phone mic.
    _releaseStreamResources();
    await stopPreview();
    _appendRuntimeProof('MetaGlassStreamDiag stop-before-retry');

    final captureActiveOrStarting = isCapturing || _captureTransitionInFlight;
    if (!captureActiveOrStarting || !_cameraStreamNeeded || _thermalPaused) {
      notifyListeners();
      return;
    }

    if (streamFailureCount <= 1) {
      // One bounded retry after a short wait.
      _streamRetryTimer?.cancel();
      _streamRetryTimer = Timer(const Duration(seconds: 8), () {
        if ((isCapturing || _captureTransitionInFlight) &&
            _cameraStreamNeeded &&
            !_captureWatchdogPaused &&
            !micOnlyFallback &&
            !_thermalPaused &&
            previewTextureId == null) {
          unawaited(_startPhotoLoop());
        }
      });
    } else {
      // Retry exhausted. There is no phone-mic fallback in this glasses-only path.
      micOnlyFallback = true;
      isCapturing = false;
      try {
        await MetaWearablesDat.disableBackgroundStreaming();
      } catch (e) {
        Logger.debug('MetaWearablesProvider: disableBackgroundStreaming failed after retry exhaustion: $e');
      }
      _scheduleNotReadyRefresh();
      _appendRuntimeProof('MetaGlassStreamDiag recover-exhausted-autostart-retry');
      _scheduleAutoStartRetry();
      Logger.debug('MetaGlassStreamDiag cameraUnavailable: camera stream unavailable, stopping glasses capture');
      _appendRuntimeProof('MetaGlassStreamDiag camera-unavailable count=$streamFailureCount');
    }
    notifyListeners();
  }

  void _appendRuntimeProof(String message) {
    final file = _runtimeProofLogFile;
    if (file == null) return;
    try {
      final parent = file.parent;
      if (!parent.existsSync()) parent.createSync(recursive: true);
      if (file.existsSync() && file.lengthSync() > _runtimeProofLogMaxBytes) {
        final current = file.readAsStringSync();
        const keepLength = _runtimeProofLogMaxBytes ~/ 2;
        final keep = current.length > keepLength ? current.substring(current.length - keepLength) : current;
        file.writeAsStringSync(keep, mode: FileMode.write);
      }
      file.writeAsStringSync('${DateTime.now().toIso8601String()} $message\n', mode: FileMode.append);
    } catch (e) {
      Logger.debug('MetaGlassRuntimeProof: write failed $e');
    }
  }

  void _scheduleThermalRetry() {
    if (_thermalRetryTimer != null) return;
    _thermalRetryTimer = Timer.periodic(const Duration(seconds: 20), (_) {
      if (!_thermalPaused || !isCapturing || captureMode != MetaGlassesCaptureMode.cameraAndMic) {
        _thermalRetryTimer?.cancel();
        _thermalRetryTimer = null;
        return;
      }
      _appendRuntimeProof('MetaGlassWatchdog wait reason=thermalPaused');
    });
  }

  void _markHealthRecovered() {
    if (health == MetaGlassesHealth.ok && !_thermalPaused && _thermalRetryTimer == null) return;
    health = MetaGlassesHealth.ok;
    _thermalPaused = false;
    _thermalRetryTimer?.cancel();
    _thermalRetryTimer = null;
  }

  void _releaseStreamResources() {
    _cancelCaptureWatchdogTimer();
    _streamGeneration += 1;
    if (_firstQueuedFrameCompleter?.isCompleted == false) _firstQueuedFrameCompleter?.complete(false);
    _firstQueuedFrameCompleter = null;
    unawaited(_frameSub?.cancel());
    _frameSub = null;
    previewTextureId = null;
    _frameForwardInFlight = false;
    _frameForwardInFlightGeneration = null;
    _lastStreamFrameEventAt = null;
    _lastPhotoLoopStartedAt = null;
    _lastQueuedPhotoAt = null;
  }

  /// Explicit user photo capture ("take photo" gesture / manual): samples the
  /// running stream immediately (shutter-free).
  Future<void> captureGlassesPhotoNow() => _captureFrame();

  List<File> _listQueuedPhotos() {
    final dir = _photoQueueDir;
    if (dir == null || !dir.existsSync()) return [];
    final files = dir
        .listSync()
        .whereType<File>()
        .where((f) => f.path.endsWith('.jpg') || f.path.endsWith('.png'))
        .toList()
      ..sort((a, b) => a.path.compareTo(b.path));
    return files;
  }

  /// Queue files are named `<captureEpochMs>.<ext>`; recover the capture time
  /// so late-flushed photos land at the right point in the timeline.
  @visibleForTesting
  static DateTime? capturedAtFromQueueFile(String path) {
    final base = path.split(Platform.pathSeparator).last;
    final epochMs = int.tryParse(base.replaceFirst(RegExp(r'\.(jpg|png)$'), ''));
    if (epochMs == null || epochMs <= 0) return null;
    return DateTime.fromMillisecondsSinceEpoch(epochMs);
  }

  Future<Directory?> _ensurePhotoQueueDirectory() async {
    final existing = _photoQueueDir;
    if (existing != null) {
      if (!existing.existsSync()) existing.createSync(recursive: true);
      return existing;
    }

    try {
      final docs = await getApplicationDocumentsDirectory();
      final dir = Directory('${docs.path}/meta_glasses_photo_queue');
      if (!dir.existsSync()) dir.createSync(recursive: true);
      _photoQueueDir = dir;
      return dir;
    } catch (e) {
      Logger.debug('MetaWearablesProvider: documents photo queue unavailable: $e');
    }

    try {
      final temp = await getTemporaryDirectory();
      final dir = Directory('${temp.path}/meta_glasses_photo_queue');
      if (!dir.existsSync()) dir.createSync(recursive: true);
      _photoQueueDir = dir;
      return dir;
    } catch (e) {
      Logger.debug('MetaWearablesProvider: fallback photo queue unavailable: $e');
      return null;
    }
  }

  Future<MetaCaptureQueue?> _ensureMetaCaptureQueue() async {
    final existing = _metaCaptureQueue;
    if (existing != null) return existing;

    final dir = await _ensurePhotoQueueDirectory();
    if (dir == null) return null;

    final queue = MetaCaptureQueue(rootDirectory: dir);
    _metaCaptureQueue = queue;
    return queue;
  }

  Future<bool> _enqueuePhotoFileFallback(
    Uint8List bytes, {
    required DateTime capturedAt,
    required String deviceUuid,
    required String? deviceName,
  }) async {
    final dir = await _ensurePhotoQueueDirectory();
    if (dir == null) {
      Logger.debug('MetaWearablesProvider: dropping frame because no local photo queue is writable');
      return false;
    }

    Future<void> writeTo(Directory targetDir) async {
      if (!targetDir.existsSync()) targetDir.createSync(recursive: true);
      final frameSha256 = crypto.sha256.convert(bytes).toString();
      final file = File('${targetDir.path}/${capturedAt.millisecondsSinceEpoch}.png');
      await file.writeAsBytes(bytes, flush: true);
      await File('${file.path}.json').writeAsString(
        jsonEncode({
          'captured_at': capturedAt.toUtc().toIso8601String(),
          'device_uuid': deviceUuid,
          if (deviceName != null) 'device_name': deviceName,
          'frame_sha256': frameSha256,
        }),
        flush: true,
      );
    }

    try {
      await writeTo(dir);
      return true;
    } catch (e) {
      Logger.debug('MetaWearablesProvider: photo fallback enqueue failed: $e');
    }

    try {
      final temp = await getTemporaryDirectory();
      final fallbackDir = Directory('${temp.path}/meta_glasses_photo_queue');
      await writeTo(fallbackDir);
      _photoQueueDir = fallbackDir;
      _metaCaptureQueue = null;
      return true;
    } catch (e) {
      Logger.debug('MetaWearablesProvider: temp photo fallback enqueue failed: $e');
    }
    return false;
  }

  Map<String, String?> _readPhotoFileMetadata(File file) {
    final metadataFile = File('${file.path}.json');
    if (!metadataFile.existsSync()) return const {};

    try {
      final json = jsonDecode(metadataFile.readAsStringSync());
      if (json is! Map<String, dynamic>) return const {};
      return {
        'captured_at': json['captured_at']?.toString(),
        'device_uuid': json['device_uuid']?.toString(),
        'device_name': json['device_name']?.toString(),
        'frame_sha256': json['frame_sha256']?.toString(),
      };
    } catch (_) {
      return const {};
    }
  }

  Future<void> _refreshPendingPhotoCount() async {
    var count = _listQueuedPhotos().length;
    final queue = _metaCaptureQueue;
    if (queue != null) {
      count += (await queue.pending(limit: _maxQueuedPhotos)).length;
    }
    pendingPhotoCount = count;
    _updateCaptureDiagnostics(pendingQueueCount: pendingPhotoCount);
  }

  Future<bool> _enqueuePhoto(Uint8List bytes) async {
    final capturedAt = DateTime.now();
    final device = selectedDevice ?? _sdkActiveDevice;
    final deviceUuid = device?.uuid ?? _sessionTargetUuid ?? 'unknown';
    final deviceName = device?.name;
    final queue = await _ensureMetaCaptureQueue();
    if (queue == null) {
      final queued = await _enqueuePhotoFileFallback(
        bytes,
        capturedAt: capturedAt,
        deviceUuid: deviceUuid,
        deviceName: deviceName,
      );
      await _refreshPendingPhotoCount();
      notifyListeners();
      return queued;
    }
    try {
      await queue.enqueue(bytes: bytes, capturedAt: capturedAt, deviceUuid: deviceUuid, deviceName: deviceName);
      await _refreshPendingPhotoCount();
      notifyListeners();
      return true;
    } catch (e) {
      Logger.debug('MetaWearablesProvider: photo enqueue failed: $e');
      final queued = await _enqueuePhotoFileFallback(
        bytes,
        capturedAt: capturedAt,
        deviceUuid: deviceUuid,
        deviceName: deviceName,
      );
      await _refreshPendingPhotoCount();
      notifyListeners();
      return queued;
    }
  }

  Future<bool> _cachePhotoBytes(
    Uint8List bytes, {
    required DateTime? capturedAt,
    bool addToUi = true,
    String? deviceUuid,
    String? deviceName,
    String? frameSha256,
  }) async {
    final controller = _captureController;
    if (controller == null) return false;
    // Photos go out as image_chunk messages on the transcription socket — the
    // only ingestion path deployed on api.omi.me. The REST cache endpoint
    // (v1/meta-wearables/photos/cache) exists only in the local repo backend
    // and 404s on prod, which stranded frames in the sync queue.
    return controller.ingestCapturedImage(
      bytes,
      addToUi: addToUi,
      capturedAt: capturedAt,
    );
  }

  /// Sends every buffered photo the backend hasn't confirmed yet, oldest
  /// first. Stops at the first failure — the server/cache path is down, later
  /// photos won't fare better.
  Future<void> flushPhotoQueue() async {
    if (_flushingQueue) return;
    if (_captureController == null) return;
    _flushingQueue = true;
    try {
      var stoppedOnFailure = false;
      final queue = _metaCaptureQueue;
      if (queue != null) {
        for (final item in await queue.pending(limit: _maxQueuedPhotos)) {
          Uint8List bytes;
          try {
            bytes = await File(item.path).readAsBytes();
          } catch (_) {
            continue;
          }
          final showInUi = !_photosShownInUi.contains(item.path);
          final sent = await _cachePhotoBytes(
            bytes,
            addToUi: showInUi,
            capturedAt: item.capturedAt,
            deviceUuid: item.deviceUuid,
            deviceName: item.deviceName,
            frameSha256: item.sha256,
          );
          if (showInUi) _photosShownInUi.add(item.path);
          if (!sent) {
            stoppedOnFailure = true;
            _updateCaptureDiagnostics(
              lastUploadAt: DateTime.now(),
              lastUploadStatus: 'upload_failed',
              failedUploadCount: diagnostics.failedUploadCount + 1,
            );
            break;
          }
          await queue.markUploaded(item.id);
          _updateCaptureDiagnostics(
            lastUploadAt: DateTime.now(),
            lastUploadStatus: 'upload_ok',
            uploadedCount: diagnostics.uploadedCount + 1,
          );
          try {
            await File(item.path).delete();
          } catch (_) {}
          _photosShownInUi.remove(item.path);
        }
      }

      if (!stoppedOnFailure) {
        for (final file in _listQueuedPhotos()) {
          Uint8List bytes;
          try {
            bytes = file.readAsBytesSync();
          } catch (_) {
            continue;
          }
          final metadata = _readPhotoFileMetadata(file);
          final metadataCapturedAt = DateTime.tryParse(metadata['captured_at'] ?? '');
          final showInUi = !_photosShownInUi.contains(file.path);
          final sent = await _cachePhotoBytes(
            bytes,
            addToUi: showInUi,
            capturedAt: metadataCapturedAt ?? capturedAtFromQueueFile(file.path),
            deviceUuid: metadata['device_uuid'],
            deviceName: metadata['device_name'],
            frameSha256: metadata['frame_sha256'] ?? crypto.sha256.convert(bytes).toString(),
          );
          if (showInUi) _photosShownInUi.add(file.path);
          if (!sent) {
            _updateCaptureDiagnostics(
              lastUploadAt: DateTime.now(),
              lastUploadStatus: 'upload_failed',
              failedUploadCount: diagnostics.failedUploadCount + 1,
            );
            break;
          }
          _updateCaptureDiagnostics(
            lastUploadAt: DateTime.now(),
            lastUploadStatus: 'upload_ok',
            uploadedCount: diagnostics.uploadedCount + 1,
          );
          try {
            file.deleteSync();
          } catch (_) {}
          try {
            File('${file.path}.json').deleteSync();
          } catch (_) {}
          _photosShownInUi.remove(file.path);
        }
      }
    } finally {
      await _refreshPendingPhotoCount();
      _flushingQueue = false;
      notifyListeners();
    }
  }

  @override
  void dispose() {
    _cancelCaptureWatchdogTimer();
    _cancelAutoStartRetry();
    _frameSub?.cancel();
    _streamRetryTimer?.cancel();
    _cancelNotReadyRefresh();
    _thermalRetryTimer?.cancel();
    _registrationSub?.cancel();
    _devicesSub?.cancel();
    _activeDeviceSub?.cancel();
    _compatibilitySub?.cancel();
    _videoSizeSub?.cancel();
    _streamStateSub?.cancel();
    _deviceStateSub?.cancel();
    _streamErrorSub?.cancel();
    _deviceErrorSub?.cancel();
    _displayStateSub?.cancel();
    _displayUpdateTimer?.cancel();
    _detachDisplayCaptureListener();
    super.dispose();
  }
}
