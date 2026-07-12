import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:collection/collection.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:flutter_provider_utilities/flutter_provider_utilities.dart';
import 'package:geolocator/geolocator.dart';
import 'package:path_provider/path_provider.dart';
import 'package:permission_handler/permission_handler.dart';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/services/bridges/ble_bridge.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/geolocation.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/env/env.dart';
import 'package:omi/models/custom_stt_config.dart';
import 'package:omi/providers/device_onboarding_provider.dart';
import 'package:omi/services/capture/capture_external_actions.dart';
import 'package:omi/services/capture/capture_metrics_tracker.dart';
import 'package:omi/services/capture/freemium_threshold_tracker.dart';
import 'package:omi/services/connectivity_service.dart';
import 'package:omi/services/services.dart';
import 'package:omi/services/voice_playback/omi_voice_playback_service.dart';
import 'package:omi/services/sockets/transcription_service.dart';
import 'package:omi/services/audio_sources/audio_source.dart';
import 'package:omi/services/audio_sources/ble_device_source.dart';
import 'package:omi/services/devices/connectors/limitless_connection.dart';
import 'package:omi/services/devices/models.dart';
import 'package:omi/services/audio_sources/phone_mic_source.dart';
import 'package:omi/services/wals.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:omi/utils/enums.dart';
import 'package:omi/utils/image/image_utils.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/services/battery_widget_service.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/app_globals.dart';

import 'package:omi/backend/schema/message_event.dart'
    show
        MessageEvent,
        MessageServiceStatusEvent,
        ConversationProcessingStartedEvent,
        ConversationEvent,
        LastConversationEvent,
        SpeakerLabelSuggestionEvent,
        TranslationEvent,
        PhotoProcessingEvent,
        PhotoDescribedEvent,
        FreemiumThresholdReachedEvent,
        SegmentsDeletedEvent;

class CaptureController extends ChangeNotifier
    with MessageNotifierMixin
    implements ITransctiptSegmentSocketServiceListener {
  static const MethodChannel _nativeBleTranscriptChannel = MethodChannel('com.friend.ios/native_ble_transcript');
  static const int _maxInProgressConversationRefreshAttempts = 30;
  static const Duration _inProgressConversationRefreshInterval = Duration(seconds: 2);

  CaptureExternalActions externalActions;
  DeviceOnboardingProvider? deviceOnboardingProvider;

  // Cache refresh for backend-created persons
  Future<void>? _peopleRefreshFuture;

  TranscriptSegmentSocketService? _socket;
  Timer? _keepAliveTimer;
  DateTime? _keepAliveLastExecutedAt;
  Timer? _inProgressConversationRefreshTimer;
  int _inProgressConversationRefreshAttempts = 0;
  bool _isRefreshingInProgressConversation = false;

  IWalService get _wal => ServiceManager.instance().wal;

  AudioSource? _activeSource;

  bool _isWalSupported = false;

  bool get isWalSupported => _isWalSupported;

  StreamSubscription<bool>? _connectionStateListener;
  bool _isConnected = ConnectivityService().isConnected;

  get isConnected => _isConnected;

  String? microphoneName;
  double microphoneLevel = 0.0;

  bool get outOfCredits => externalActions.isOutOfCredits ?? false;

  String? get topConversationId => externalActions.topConversationId;

  final FreemiumThresholdTracker _freemiumThreshold = FreemiumThresholdTracker();

  bool get freemiumThresholdReached => _freemiumThreshold.reached;
  int get freemiumRemainingSeconds => _freemiumThreshold.remainingSeconds;

  /// Whether user needs to take action (e.g., setup on-device STT)
  bool get freemiumRequiresUserAction => _freemiumThreshold.requiresUserAction;

  List<MessageEvent> _transcriptionServiceStatuses = [];
  List<MessageEvent> get transcriptionServiceStatuses => _transcriptionServiceStatuses;

  // Phone mic WAL: buffer for splitting variable-sized PCM chunks into fixed-size frames
  bool _phoneMicWalActive = false;

  bool _isLoadingInProgressConversation = false;

  late final CaptureMetricsTracker _metrics = CaptureMetricsTracker(onNotify: notifyListeners);

  double get bleReceiveRateKbps => _metrics.bleReceiveRateKbps;
  double get wsSendRateKbps => _metrics.wsSendRateKbps;

  /// Call this in initState of a widget that needs BLE/WS metrics
  void addMetricsListener() {
    _metrics.addMetricsListener();
  }

  /// Call this in dispose of a widget that uses BLE/WS metrics
  void removeMetricsListener() {
    _metrics.removeMetricsListener();
  }

  /// Check if any segment has a personId not in local cache.
  /// Uses Set difference for O(N+M) complexity instead of O(N*M).
  bool _hasMissingPerson(List<TranscriptSegment> segments) {
    final cachedIds = SharedPreferencesUtil().cachedPeople.map((p) => p.id).toSet();
    final segmentPersonIds = segments.map((s) => s.personId).whereType<String>().toSet();
    return segmentPersonIds.difference(cachedIds).isNotEmpty;
  }

  CaptureController({CaptureExternalActions? externalActions})
      : externalActions = externalActions ?? const NoopCaptureExternalActions() {
    // Restore a persisted device mute so it survives an app kill/restart. When
    // the device reconnects, streamDeviceRecording() reads _isPaused as
    // `wasPaused` and re-applies the mute instead of silently resuming.
    _isPaused = SharedPreferencesUtil().deviceMuted;
    _connectionStateListener = ConnectivityService().onConnectionChange.listen((bool isConnected) {
      onConnectionStateChanged(isConnected);
    });
    _startAudioInterruptionListener();
    BleBridge.instance.addBatchRecordingFinalizedListener(_onOfflineRecordingFinalized);
  }

  // iOS phone-call interruption events from AudioInterruptionManager.swift.
  StreamSubscription? _audioInterruptionSubscription;
  static const EventChannel _audioInterruptionChannel = EventChannel('com.omi.ios/audioInterruption');
  static const MethodChannel _audioSessionChannel = MethodChannel('com.omi.ios/audioSession');

  void _startAudioInterruptionListener() {
    if (!Platform.isIOS) return;
    _audioInterruptionSubscription?.cancel();
    _audioInterruptionSubscription = _audioInterruptionChannel.receiveBroadcastStream().listen(
      (dynamic event) {
        if (event is! Map) return;
        final type = event['type'];
        if (type == 'began') {
          _onAudioInterruptionBegan();
        } else if (type == 'ended') {
          _onAudioInterruptionEnded();
        }
      },
      onError: (Object err) {
        Logger.error('[CaptureProvider] audioInterruption channel error: $err');
      },
    );
  }

  // True while a phone call is active; suppresses mic restarts until .ended fires.
  bool _callActive = false;

  void _onAudioInterruptionBegan() {
    if (_activeSource is! PhoneMicSource) return;
    _callActive = true;
    ServiceManager.instance().mic.stop();
    updateRecordingState(RecordingState.interrupted);
  }

  void _onAudioInterruptionEnded() {
    if (_activeSource is! PhoneMicSource) return;
    _callActive = false;
    _restartPhoneMicRecording();
  }

  bool _phoneMicRestartInFlight = false;

  Future<void> _restartPhoneMicRecording() async {
    if (_phoneMicRestartInFlight) return;
    _phoneMicRestartInFlight = true;
    try {
      ServiceManager.instance().mic.stop();
      // Re-assert interrupted so the IPC 'stopped' response doesn't overwrite it.
      updateRecordingState(RecordingState.interrupted);
      await Future.delayed(const Duration(milliseconds: 250));
      // _activeSource is cleared if the user manually stopped — bail in that case.
      if (_activeSource is! PhoneMicSource) return;
      if (Platform.isIOS) {
        try {
          await _audioSessionChannel.invokeMethod<bool>('reactivate');
        } catch (e) {
          Logger.error('[CaptureProvider] reactivate audio session failed: $e');
        }
      }
      // Use _resumeMicRecording (not streamRecording) to preserve existing socket/segments.
      await _resumeMicRecording();
    } catch (e, st) {
      Logger.error('[CaptureProvider] _restartPhoneMicRecording failed: $e\n$st');
    } finally {
      _phoneMicRestartInFlight = false;
    }
  }

  // Restarts mic only — preserves existing socket and conversation segments.
  Future<void> _resumeMicRecording() async {
    updateRecordingState(RecordingState.initialising);
    _activeSource = PhoneMicSource();
    _phoneMicWalActive = true;
    await ServiceManager.instance().mic.start(
          onByteReceived: (bytes) {
            final frames = _activeSource?.processBytes(bytes) ?? [];
            for (final frame in frames) {
              _wal.getSyncs().phone.onFrameCaptured(frame);
              if (_socket?.state == SocketServiceState.connected) {
                _socket?.send(frame.payload);
                _wal.getSyncs().phone.markFrameSynced(frame.syncKey);
              }
            }
          },
          onRecording: () {
            updateRecordingState(RecordingState.record);
          },
          onStop: () {
            if (!_callActive) {
              updateRecordingState(RecordingState.stop);
            }
          },
          onInitializing: () {
            updateRecordingState(RecordingState.initialising);
          },
          onStalled: _onMicStalled,
        );
  }

  void _onMicStalled() {
    if (_activeSource is! PhoneMicSource) return;
    if (_callActive) return; // silence during a call is expected
    if (recordingState == RecordingState.record ||
        recordingState == RecordingState.initialising ||
        recordingState == RecordingState.stop) {
      updateRecordingState(RecordingState.interrupted);
    }
    if (recordingState == RecordingState.interrupted) {
      _restartPhoneMicRecording();
    }
  }

  void updateExternalActions(CaptureExternalActions? actions) {
    externalActions = actions ?? const NoopCaptureExternalActions();

    // Run orphan recovery once after providers are wired up and WAL service is initialized.
    // Uses Future.delayed to let the WAL service finish loading wals.json from disk.
    if (!_orphanRecoveryDone) {
      _orphanRecoveryDone = true;
      Future.delayed(const Duration(seconds: 5), () => recoverOrphanedWals());
    }

    notifyListeners();
  }

  BtDevice? _recordingDevice;

  String? _getConversationSourceFromDevice() {
    if (_recordingDevice == null) {
      return null;
    }
    switch (_recordingDevice!.type) {
      case DeviceType.friendPendant:
        return 'friend_com';
      case DeviceType.omi:
        return 'omi';
      case DeviceType.openglass:
        return 'openglass';
      case DeviceType.fieldy:
        return 'fieldy';
      case DeviceType.bee:
        return 'bee';
      case DeviceType.plaud:
        return 'plaud';
      case DeviceType.appleWatch:
        return 'apple_watch';
      case DeviceType.limitless:
        return 'limitless';
      case DeviceType.raybanMeta:
        return 'rayban_meta';
    }
  }

  ServerConversation? _conversation;
  List<TranscriptSegment> segments = [];
  List<ConversationPhoto> photos = [];

  /// Unix timestamp (seconds) when the current capture session started.
  /// Used to scope WAL queries to only this session's audio.
  int _sessionStartSeconds = 0;

  @visibleForTesting
  set testSessionStartSeconds(int v) => _sessionStartSeconds = v;

  /// Unix timestamp (seconds) when the current offline/batch device-recording
  /// session started. Set only in offline mode (the websocket path that sets
  /// [_sessionStartSeconds] is skipped there); drives the "captured so far"
  /// timer on the offline capture card. 0 when not offline-recording.
  int _offlineSessionStartSeconds = 0;
  int? get offlineRecordingStartedAt => _offlineSessionStartSeconds == 0 ? null : _offlineSessionStartSeconds;

  /// Wall-clock seconds when the current recording was muted, or null when not
  /// muted — the "captured so far" timer freezes at this point.
  int? _offlineMuteStartedAt;

  bool get offlineMuted => SharedPreferencesUtil().batchMuted;

  /// Elapsed seconds of the *current* recording for the capture-card timer:
  /// frozen while muted, and reset on each cut (manual or the 15-min rotation).
  int? get offlineRecordingElapsedSeconds {
    if (_offlineSessionStartSeconds == 0) return null;
    final end = _offlineMuteStartedAt ?? (DateTime.now().millisecondsSinceEpoch ~/ 1000);
    final secs = end - _offlineSessionStartSeconds;
    return secs < 0 ? 0 : secs;
  }

  int get _nowSeconds => DateTime.now().millisecondsSinceEpoch ~/ 1000;

  /// Mute/unmute Transcribe Later capture. The native writer drops packets while
  /// muted and resumes into the same recording; the card timer freezes meanwhile.
  void toggleOfflineMute() {
    if (SharedPreferencesUtil().batchMuted) {
      if (_offlineMuteStartedAt != null) {
        _offlineSessionStartSeconds += _nowSeconds - _offlineMuteStartedAt!;
        _offlineMuteStartedAt = null;
      }
      SharedPreferencesUtil().batchMuted = false;
    } else {
      _offlineMuteStartedAt = _nowSeconds;
      SharedPreferencesUtil().batchMuted = true;
    }
    notifyListeners();
  }

  /// Manually finalize the current recording and start a fresh one. The native
  /// writer cuts on the next packet; the timer resets immediately for feedback.
  void startNewOfflineRecording() {
    SharedPreferencesUtil().batchCutRequested = true;
    if (SharedPreferencesUtil().batchMuted) SharedPreferencesUtil().batchMuted = false;
    _offlineSessionStartSeconds = _nowSeconds;
    _offlineMuteStartedAt = null;
    notifyListeners();
  }

  void _onOfflineRecordingFinalized(String _) {
    if (_offlineSessionStartSeconds == 0) return;
    _offlineSessionStartSeconds = _nowSeconds;
    _offlineMuteStartedAt = SharedPreferencesUtil().batchMuted ? _nowSeconds : null;
    notifyListeners();
  }

  bool _orphanRecoveryDone = false;

  /// Preserved session start for auto-sync after socket-driven conversation completion.
  /// Set before _resetStateVariables() clears _sessionStartSeconds, consumed on ConversationEvent.
  int _pendingAutoSyncSessionStart = 0;

  /// Fallback timer that fires if ConversationEvent doesn't arrive within 30s.
  Timer? _autoSyncFallbackTimer;

  /// The conversation ID from ConversationProcessingStartedEvent, kept for fallback sync.
  String? _pendingAutoSyncConversationId;

  /// Future tracking the in-progress _finalizeAndStampSession(), so _autoSyncSessionWals()
  /// can await it before querying disk WALs. Prevents race when backend responds fast.
  Future<void>? _pendingFinalizeAndStamp;

  /// Set in onClosed() when the socket drops during active device recording.
  /// Consumed in _initiateWebsocket() to trigger onNetworkSocketReconnected()
  /// on the device connection (e.g. Limitless re-sends enable-data-stream).
  bool _socketReconnectPending = false;

  /// Returns unsynced WALs belonging to the current capture session.
  /// Empty when all frames have been streamed successfully (clean UI).
  List<Wal> get unsyncedSessionWals {
    if (_sessionStartSeconds == 0) return [];
    return _wal.getSyncs().phone.getSessionUnsyncedWals(_sessionStartSeconds);
  }

  /// Seconds of audio still in memory buffer (not yet chunked/flushed to disk).
  int get inFlightAudioSeconds => _wal.getSyncs().phone.getInFlightSeconds();

  // Version counter for segments/photos content changes. Incremented on in-place mutations
  // (e.g., translation updates, photo description changes) to signal UI rebuilds when
  // list length and last-text remain unchanged.
  int _segmentsPhotosVersion = 0;
  int get segmentsPhotosVersion => _segmentsPhotosVersion;
  Map<String, SpeakerLabelSuggestionEvent> suggestionsBySegmentId = {};
  List<String> taggingSegmentIds = [];

  bool hasTranscripts = false;

  StreamSubscription? _bleBytesStream;
  StreamSubscription? _blePhotoStream;

  get bleBytesStream => _bleBytesStream;

  StreamSubscription? _bleButtonStream;
  DateTime? _voiceCommandSession;
  List<List<int>> _commandBytes = [];
  bool _isProcessingButtonEvent = false; // Guard to prevent overlapping button operations
  Timer? _voiceCommandTimeoutTimer; // 30s auto-end timer for voice questions
  bool _voiceSessionStartedByLegacyLongPress =
      false; // Track if session was started by legacy long press (3) vs new toggle (1), TODO: remove this flag later

  StreamSubscription? _storageStream;

  get storageStream => _storageStream;

  RecordingState recordingState = RecordingState.stop;

  bool _isPaused = false;
  bool get isPaused => _isPaused;
  bool get isCallActive => _callActive;

  // Flag to star the conversation when it ends
  bool _starOngoingConversation = false;
  bool get isConversationMarkedForStarring => _starOngoingConversation;

  void markConversationForStarring() {
    _starOngoingConversation = true;
    notifyListeners();
  }

  void unmarkConversationForStarring() {
    _starOngoingConversation = false;
    notifyListeners();
  }

  bool _transcriptServiceReady = false;

  bool get transcriptServiceReady => _transcriptServiceReady && _isConnected;

  // having a connected device or using the phone's mic for recording.
  // Includes `interrupted` so the keep-alive/reconnect path keeps running
  // while the phone mic is in a transiently-broken state (e.g., iOS audio
  // session interruption after an incoming call).
  bool get recordingDeviceServiceReady =>
      _recordingDevice != null ||
      recordingState == RecordingState.record ||
      recordingState == RecordingState.interrupted ||
      recordingState == RecordingState.systemAudioRecord;

  bool get havingRecordingDevice => _recordingDevice != null;

  BtDevice? get recordingDevice => _recordingDevice;

  void setHasTranscripts(bool value) {
    hasTranscripts = value;
    notifyListeners();
  }

  void setConversationCreating(bool value) {
    Logger.debug('set Conversation creating $value');
    // ConversationCreating = value;
    notifyListeners();
  }

  void _updateRecordingDevice(BtDevice? device) {
    Logger.debug('connected device changed from ${_recordingDevice?.id} to ${device?.id}');
    _recordingDevice = device;
    if (device == null) _endOfflineSession();
    notifyListeners();
  }

  void updateRecordingDevice(BtDevice? device) {
    _updateRecordingDevice(device);
  }

  Future _resetStateVariables() async {
    _stopInProgressConversationRefresh();
    segments = [];
    photos = [];
    hasTranscripts = false;
    suggestionsBySegmentId = {};
    _conversation = null;
    taggingSegmentIds = [];
    _sessionStartSeconds = 0;
    _endOfflineSession();
    notifyListeners();
  }

  void _endOfflineSession() {
    _offlineSessionStartSeconds = 0;
    _offlineMuteStartedAt = null;
    if (SharedPreferencesUtil().batchMuted) SharedPreferencesUtil().batchMuted = false;
    if (SharedPreferencesUtil().batchCutRequested) SharedPreferencesUtil().batchCutRequested = false;
  }

  Future<void> onRecordProfileSettingChanged() async {
    await _resetState();
  }

  static bool supportsTranscribeLater(DeviceType? type) {
    return type == DeviceType.omi ||
        type == DeviceType.openglass ||
        type == DeviceType.friendPendant ||
        type == DeviceType.limitless;
  }

  bool get deviceSupportsTranscribeLater => supportsTranscribeLater(_recordingDevice?.type);

  Future<bool> setBatchMode(bool enabled) async {
    if (SharedPreferencesUtil().batchModeEnabled == enabled) return true;
    // With batch on the realtime socket is suppressed for every device type, so a
    // device without a batch capture path would record nothing at all.
    if (enabled && _recordingDevice != null && !deviceSupportsTranscribeLater) {
      Logger.debug('[setBatchMode] refused: ${_recordingDevice?.type} has no Transcribe Later support');
      return false;
    }
    SharedPreferencesUtil().batchModeEnabled = enabled;
    PlatformManager.instance.analytics.transcribeLaterToggled(enabled: enabled);
    final docs = await getApplicationDocumentsDirectory();
    await SharedPreferencesUtil().saveString('batchAudioDir', docs.path);
    // Only re-enable native streaming when turning batch OFF, a device with a
    // native BLE route is connected, and background mode is opted in.
    final enableNativeStreaming =
        !enabled && hasNativeBackgroundStreamRoute && SharedPreferencesUtil().backgroundModeEnabled;
    await SharedPreferencesUtil().saveBool('nativeBleStreamingEnabled', enableNativeStreaming);
    await _applyLimitlessRealtimeSuppression(enabled);
    notifyListeners();
    try {
      await onRecordProfileSettingChanged();
    } catch (_) {}
    return true;
  }

  Future<void> _applyLimitlessRealtimeSuppression(bool suppressed) async {
    final device = _recordingDevice;
    if (device == null || device.type != DeviceType.limitless) return;
    try {
      final connection = await ServiceManager.instance().device.ensureConnection(device.id);
      if (connection is LimitlessDeviceConnection) {
        await connection.setRealtimeAudioSuppressed(suppressed);
      }
    } catch (e) {
      Logger.debug('[batch] limitless realtime suppression toggle failed: $e');
    }
  }

  // Interactive device onboarding needs the realtime transcript + voice paths, which Transcribe
  // Later (batch mode) disables. Flipping batchModeEnabled off also re-opens the native->Dart audio
  // forward — the native BatchAudioWriter gate reads this same pref — so BLE audio reaches Dart again.
  // Skips the transcribeLaterToggled analytic on purpose; the persisted flag drives a crash-safe restore.
  Future<void> suspendBatchModeForOnboarding() async {
    if (SharedPreferencesUtil().batchModeSuspendedForOnboarding) return;
    if (!SharedPreferencesUtil().batchModeEnabled) return;
    SharedPreferencesUtil().batchModeSuspendedForOnboarding = true;
    SharedPreferencesUtil().batchModeEnabled = false;
    await _applyLimitlessRealtimeSuppression(false);
    notifyListeners();
    try {
      await onRecordProfileSettingChanged();
    } catch (_) {}
  }

  Future<void> restoreBatchModeAfterOnboarding() async {
    if (!SharedPreferencesUtil().batchModeSuspendedForOnboarding) return;
    SharedPreferencesUtil().batchModeSuspendedForOnboarding = false;
    SharedPreferencesUtil().batchModeEnabled = true;
    await _applyLimitlessRealtimeSuppression(true);
    notifyListeners();
    try {
      await onRecordProfileSettingChanged();
    } catch (_) {}
  }

  /// Called when transcription settings are changed (e.g., custom STT provider)
  /// This resets the socket connection to use the new configuration
  Future<void> onTranscriptionSettingsChanged() async {
    Logger.debug("Transcription settings changed, refreshing socket connection...");

    // Handle device recording
    if (_recordingDevice != null) {
      await _socket?.stop(reason: 'transcription settings changed');
      BleAudioCodec codec = await _getAudioCodec(_recordingDevice!.id);
      await _initiateWebsocket(audioCodec: codec, force: true, source: _getConversationSourceFromDevice());
      return;
    }

    // Handle phone mic recording
    if (recordingState == RecordingState.record) {
      await _socket?.stop(reason: 'transcription settings changed');
      await _initiateWebsocket(
        audioCodec: BleAudioCodec.pcm16,
        sampleRate: 16000,
        force: true,
        source: ConversationSource.phone.name,
      );
      return;
    }
  }

  Future<void> changeAudioRecordProfile({
    required BleAudioCodec audioCodec,
    int? sampleRate,
    int? channels,
    bool? isPcm,
    String? source,
  }) async {
    await _resetState();
    await _initiateWebsocket(
      audioCodec: audioCodec,
      sampleRate: sampleRate,
      channels: channels,
      isPcm: isPcm,
      source: source,
    );
  }

  Future<void> _initiateWebsocket({
    required BleAudioCodec audioCodec,
    int? sampleRate,
    int? channels,
    bool? isPcm,
    bool force = false,
    String? source,
  }) async {
    Logger.debug('initiateWebsocket in capture_provider');

    // Batch (offline) mode: never open the realtime transcription socket. The
    // native layer stores incoming BLE audio to local .bin files instead, and
    // the user uploads recordings later. See _saveNativeBleStreamConfig.
    if (SharedPreferencesUtil().batchModeEnabled) {
      Logger.debug('Batch mode enabled — skipping transcription websocket');
      return;
    }

    BleAudioCodec codec = audioCodec;
    sampleRate ??= mapCodecToSampleRate(codec);
    channels ??= (codec == BleAudioCodec.pcm16 || codec == BleAudioCodec.pcm8) ? 1 : 2;

    Logger.debug('is ws null: ${_socket == null}');
    Logger.debug('Initiating WebSocket with: codec=$codec, sampleRate=$sampleRate, channels=$channels, isPcm=$isPcm');

    // Get language and custom STT config
    String language =
        SharedPreferencesUtil().hasSetPrimaryLanguage ? SharedPreferencesUtil().userPrimaryLanguage : "multi";
    final customSttConfig = SharedPreferencesUtil().customSttConfig;

    Logger.debug('Custom STT enabled: ${customSttConfig.isEnabled}, provider: ${customSttConfig.provider}');

    // Check codec compatibility for custom STT - fallback to default if incompatible
    CustomSttConfig? effectiveConfig = customSttConfig.isEnabled ? customSttConfig : null;
    if (effectiveConfig != null && !TranscriptSocketServiceFactory.isCodecSupportedForCustomStt(codec)) {
      Logger.debug('[CustomSTT] Codec $codec not supported, falling back to Omi');
      effectiveConfig = null;
    }

    // Connect to the transcript socket
    _socket = await ServiceManager.instance().socket.conversation(
          codec: codec,
          sampleRate: sampleRate,
          language: language,
          force: force,
          source: source,
          customSttConfig: effectiveConfig,
        );
    if (_socket == null) {
      _startKeepAliveServices();
      Logger.debug("Can not create new conversation socket");
      return;
    }
    _socket?.subscribe(this, this);
    _transcriptServiceReady = true;
    if (_sessionStartSeconds == 0) {
      _sessionStartSeconds = DateTime.now().millisecondsSinceEpoch ~/ 1000;
    }

    // Notify the device connection that the socket reconnected after a network
    // outage so it can re-enable streaming if needed (e.g. Limitless pendant).
    // Guard on deviceRecord: skip if the user has paused — no point waking the
    // device when _bleBytesStream is cancelled and audio would just be dropped.
    if (_socketReconnectPending && _recordingDevice != null && recordingState == RecordingState.deviceRecord) {
      _socketReconnectPending = false;
      final conn = await ServiceManager.instance().device.ensureConnection(_recordingDevice!.id);
      await conn?.onNetworkSocketReconnected();
    }

    await _loadInProgressConversation();
    await _drainNativeBleTranscriptMessages();
    _startInProgressConversationRefresh();

    notifyListeners();
  }

  void _processVoiceCommandBytes(String deviceId, List<List<int>> data) async {
    if (data.isEmpty) {
      Logger.debug("voice frames is empty");
      return;
    }

    if (_recordingDevice == null) {
      Logger.debug("Recording device is null, cannot process voice command");
      return;
    }

    BleAudioCodec codec = await _getAudioCodec(_recordingDevice!.id);
    await externalActions.sendVoiceMessageStreamToServer(
      data,
      onFirstChunkRecived: () {
        _playSpeakerHaptic(deviceId, 2);
      },
      codec: codec,
      // Device-button voice → speak the reply aloud (BG/lock-screen safe).
      // Gated by SharedPreferencesUtil().voiceResponseEnabled inside the service.
      playResponseAudio: true,
    );
  }

  // Start a 15s timeout timer for voice commands - auto-ends if user forgets to tap again
  void _startVoiceCommandTimeout(String deviceId) {
    _voiceCommandTimeoutTimer?.cancel();
    _voiceCommandTimeoutTimer = Timer(const Duration(seconds: 15), () {
      debugPrint("Voice command timeout - auto-ending session after 15s");
      if (_voiceCommandSession != null) {
        _endVoiceCommandSession(deviceId);
      }
    });
  }

  // End voice command session and process the collected audio
  void _endVoiceCommandSession(String deviceId) {
    _voiceCommandTimeoutTimer?.cancel();
    _voiceCommandTimeoutTimer = null;
    _voiceCommandSession = null;
    _voiceSessionStartedByLegacyLongPress = false; // Reset flag
    var data = List<List<int>>.from(_commandBytes);
    _commandBytes = [];
    _processVoiceCommandBytes(deviceId, data);
  }

  Future streamButton(String deviceId) async {
    Logger.debug('streamButton in capture_provider');
    _bleButtonStream?.cancel();
    _bleButtonStream = await _getBleButtonListener(
      deviceId,
      onButtonReceived: (List<int> value) {
        final snapshot = List<int>.from(value);
        if (snapshot.isEmpty || snapshot.length < 4) return;
        var buttonState = ByteData.view(
          Uint8List.fromList(snapshot.sublist(0, 4).reversed.toList()).buffer,
        ).getUint32(0);
        Logger.debug("device button $buttonState");

        // Intercept for interactive device onboarding
        if (deviceOnboardingProvider?.isOnboardingActive == true) {
          deviceOnboardingProvider!.onButtonEvent(buttonState);
          // For step 1 (ask question), let single-tap fall through to normal voice command handling
          if (deviceOnboardingProvider!.currentStep == 1 && buttonState == 1) {
            // Fall through to normal single-tap handling below
          } else {
            return;
          }
        }

        // double tap
        if (buttonState == 2) {
          Logger.debug("Double tap detected");

          // Guard: ignore if already processing a button event
          if (_isProcessingButtonEvent) {
            Logger.debug("Double tap: already processing, ignoring");
            return;
          }

          int doubleTapAction = SharedPreferencesUtil().doubleTapAction;

          if (doubleTapAction == 1) {
            // Pause/resume recording
            Logger.debug("Double tap: toggling pause/mute");
            _isProcessingButtonEvent = true;
            if (_isPaused) {
              PlatformManager.instance.analytics.omiDoubleTap(feature: 'unmute');
              resumeDeviceRecording().then((_) {
                _isProcessingButtonEvent = false;
              }).catchError((e) {
                Logger.debug("Error resuming device recording: $e");
                _isProcessingButtonEvent = false;
              });
            } else {
              PlatformManager.instance.analytics.omiDoubleTap(feature: 'mute');
              pauseDeviceRecording().then((_) {
                _isProcessingButtonEvent = false;
              }).catchError((e) {
                Logger.debug("Error pausing device recording: $e");
                _isProcessingButtonEvent = false;
              });
            }
          } else if (doubleTapAction == 2) {
            // Star ongoing conversation (doesn't end it)
            Logger.debug("Double tap: marking conversation for starring");
            if (!_starOngoingConversation) {
              markConversationForStarring();
              PlatformManager.instance.analytics.omiDoubleTap(feature: 'star_conversation');
              // Haptic feedback to confirm
              HapticFeedback.mediumImpact();
            } else {
              // Toggle off if already marked
              unmarkConversationForStarring();
              PlatformManager.instance.analytics.omiDoubleTap(feature: 'unstar_conversation');
              HapticFeedback.lightImpact();
            }
          } else {
            // End conversation and process (default)
            Logger.debug("Double tap: processing conversation");
            PlatformManager.instance.analytics.omiDoubleTap(feature: 'process_conversation');
            forceProcessingCurrentConversation();
          }
          return;
        }

        // Single tap (buttonState == 1) - toggle voice question mode
        // Tap once to start, tap again to end
        if (buttonState == 1) {
          debugPrint("Single tap detected");
          if (_voiceCommandSession == null) {
            // Start voice question session (new toggle mode)
            debugPrint("Starting voice question session (toggle mode)");
            // Cut off any in-flight voice playback from a prior reply so the
            // new recording starts clean.
            if (OmiVoicePlaybackService.instance.isSpeaking) {
              OmiVoicePlaybackService.instance.interrupt();
            }
            _voiceCommandSession = DateTime.now();
            _commandBytes = [];
            _voiceSessionStartedByLegacyLongPress = false; // New toggle mode
            _startVoiceCommandTimeout(deviceId);
            _playSpeakerHaptic(deviceId, 1);
          } else if (!_voiceSessionStartedByLegacyLongPress) {
            // Only end on second tap if session was started by toggle mode (not legacy)
            debugPrint("Ending voice question session (toggle mode)");
            _endVoiceCommandSession(deviceId);
          }
          return;
        }

        // Legacy support: start long press (for voice commands) - older firmware
        if (buttonState == 3 && _voiceCommandSession == null) {
          debugPrint("Legacy: Long press start detected");
          _voiceCommandSession = DateTime.now();
          _commandBytes = [];
          _voiceSessionStartedByLegacyLongPress = true; // Legacy hold-to-talk mode
          _startVoiceCommandTimeout(deviceId);
          _playSpeakerHaptic(deviceId, 1);
        }

        // Legacy support: release (end voice command) - older firmware
        // Only end on release if session was started by legacy long press (buttonState 3)
        if (buttonState == 5 && _voiceCommandSession != null && _voiceSessionStartedByLegacyLongPress) {
          debugPrint("Legacy: Release detected - ending voice command");
          _endVoiceCommandSession(deviceId);
        }
      },
    );
  }

  Future<bool> streamAudioToWs(String deviceId, BleAudioCodec codec) async {
    Logger.debug('streamAudioToWs in capture_provider');
    _bleBytesStream?.cancel();
    _startMetricsTracking();
    final subscription = await _getBleAudioBytesListener(
      deviceId,
      onAudioBytesReceived: (List<int> value) {
        final snapshot = List<int>.from(value);
        if (snapshot.isEmpty || snapshot.length < 3) return;

        // Track bytes received from BLE
        _metrics.addBleBytes(snapshot.length);

        // Command button triggered
        bool voiceCommandSupported = _recordingDevice != null
            ? (_recordingDevice?.type == DeviceType.omi || _recordingDevice?.type == DeviceType.openglass)
            : false;
        if (_voiceCommandSession != null && voiceCommandSupported) {
          final payload = _activeSource?.getSocketPayload(snapshot) ?? snapshot.sublist(3);
          _commandBytes.add(payload);
        }

        // Local storage syncs. In batch mode the native layer owns writing the
        // .bin files, so the Dart WAL writer must stay off to avoid double-writes.
        var checkWalSupported = !SharedPreferencesUtil().batchModeEnabled &&
            (_recordingDevice?.type == DeviceType.omi || _recordingDevice?.type == DeviceType.openglass) &&
            codec.isOpusSupported() &&
            (_socket?.state != SocketServiceState.connected || SharedPreferencesUtil().unlimitedLocalStorageEnabled);
        if (checkWalSupported != _isWalSupported) {
          setIsWalSupported(checkWalSupported);
        }

        // Process bytes through audio source and feed to WAL
        final frames = _activeSource?.processBytes(snapshot) ?? [];
        if (_isWalSupported) {
          for (final frame in frames) {
            _wal.getSyncs().phone.onFrameCaptured(frame);
          }
        }

        // Send WS
        if (_socket?.state == SocketServiceState.connected) {
          final socketPayload = _activeSource?.getSocketPayload(snapshot) ?? snapshot;
          _socket?.send(socketPayload);

          // Track bytes sent to websocket
          _metrics.addSocketBytes(socketPayload.length);

          // Mark frames as synced
          if (_isWalSupported) {
            for (final frame in frames) {
              _wal.getSyncs().phone.markFrameSynced(frame.syncKey);
            }
          }
        }
      },
    );
    _bleBytesStream = subscription;
    notifyListeners();
    return subscription != null;
  }

  Future<void> _resetState() async {
    Logger.debug('resetState');
    await _cleanupCurrentState();

    // Always try to stream audio if a device is present
    await _ensureDeviceSocketConnection();
    await _initiateDeviceAudioStreaming();

    // Additionally, stream photos if the device supports it
    if (_recordingDevice != null) {
      var connection = await ServiceManager.instance().device.ensureConnection(_recordingDevice!.id);
      if (connection != null && await connection.hasPhotoStreamingCharacteristic()) {
        await _initiateDevicePhotoStreaming();
      }
    }

    notifyListeners();
  }

  Future _cleanupCurrentState({bool disableNativeBackground = false}) async {
    _socketReconnectPending = false;
    _stopInProgressConversationRefresh();
    await _closeBleStream(disableNativeBackground: disableNativeBackground);
    _activeSource = null;
    notifyListeners();
  }

  Future<BleAudioCodec> _getAudioCodec(String deviceId) async {
    var connection = await ServiceManager.instance().device.ensureConnection(deviceId);
    if (connection == null) {
      return BleAudioCodec.pcm8;
    }
    return connection.getAudioCodec();
  }

  Future<bool> _playSpeakerHaptic(String deviceId, int level) async {
    var connection = await ServiceManager.instance().device.ensureConnection(deviceId);
    if (connection == null) {
      return false;
    }
    return connection.performPlayToSpeakerHaptic(level);
  }

  Future<StreamSubscription?> _getBleAudioBytesListener(
    String deviceId, {
    required void Function(List<int>) onAudioBytesReceived,
  }) async {
    var connection = await ServiceManager.instance().device.ensureConnection(deviceId);
    if (connection == null) {
      return Future.value(null);
    }
    return connection.getBleAudioBytesListener(onAudioBytesReceived: onAudioBytesReceived);
  }

  Future<StreamSubscription?> _getBleButtonListener(
    String deviceId, {
    required void Function(List<int>) onButtonReceived,
  }) async {
    var connection = await ServiceManager.instance().device.ensureConnection(deviceId);
    if (connection == null) {
      return Future.value(null);
    }
    return connection.getBleButtonListener(onButtonReceived: onButtonReceived);
  }

  Future<void> _ensureDeviceSocketConnection() async {
    if (_recordingDevice == null) {
      return;
    }
    BleAudioCodec codec = await _getAudioCodec(_recordingDevice!.id);
    var language =
        SharedPreferencesUtil().hasSetPrimaryLanguage ? SharedPreferencesUtil().userPrimaryLanguage : "multi";
    final customSttConfig = SharedPreferencesUtil().customSttConfig;
    final sttConfigId = customSttConfig.sttConfigId;

    if (language != _socket?.language ||
        codec != _socket?.codec ||
        _socket?.state != SocketServiceState.connected ||
        _socket?.sttConfigId != sttConfigId) {
      await _initiateWebsocket(audioCodec: codec, force: true, source: _getConversationSourceFromDevice());
    }
  }

  Future<void> _initiateDeviceAudioStreaming() async {
    final device = _recordingDevice;
    if (device == null) {
      return;
    }
    final deviceId = device.id;
    if (deviceId.isEmpty) {
      return;
    }
    final connection = await ServiceManager.instance().device.ensureConnection(deviceId);
    if (connection == null) return;
    final codec = await _getAudioCodec(deviceId);
    await _wal.getSyncs().phone.onAudioCodecChanged(codec);
    await _saveNativeBleStreamConfig(device, codec);

    // Create audio source for BLE device
    final pd = await device.getDeviceInfo(connection);
    final deviceModel = pd.modelNumber.isNotEmpty ? pd.modelNumber : "Omi";
    if (device.type == DeviceType.omi || device.type == DeviceType.openglass) {
      _activeSource = BleDeviceSource(codec: codec, deviceId: deviceId, deviceModel: deviceModel);
    }
    _wal.getSyncs().phone.setDeviceInfo(deviceId, deviceModel);

    await streamButton(deviceId);
    final foregroundAudioReady = await streamAudioToWs(deviceId, codec);
    if (foregroundAudioReady) {
      await SharedPreferencesUtil().saveBool('nativeBleForegroundReady', true);
    }

    // Update state (limitless is excluded: the pendant records on-device, so the
    // capture card is driven by its stored-page count, not a live phone timer)
    if (SharedPreferencesUtil().batchModeEnabled &&
        _recordingDevice?.type != DeviceType.limitless &&
        _offlineSessionStartSeconds == 0) {
      _offlineSessionStartSeconds = DateTime.now().millisecondsSinceEpoch ~/ 1000;
      _offlineMuteStartedAt = null;
      if (SharedPreferencesUtil().batchMuted) SharedPreferencesUtil().batchMuted = false;
    }
    updateRecordingState(RecordingState.deviceRecord);
    notifyListeners();
  }

  Future<void> _saveNativeBleStreamConfig(BtDevice device, BleAudioCodec codec) async {
    final audioTarget = _nativeBleAudioTarget(device);
    if (audioTarget == null) {
      // No native route — clear all background/streaming state and stale config.
      Logger.debug(
        '[saveNativeBleStreamConfig] no native BLE route for device ${device.id} type=${device.type} — clearing state',
      );
      await SharedPreferencesUtil().saveBool('nativeBleForegroundReady', false);
      await SharedPreferencesUtil().saveBool('nativeBleStreamingEnabled', false);
      SharedPreferencesUtil().backgroundModeEnabled = false;
      await SharedPreferencesUtil().remove('nativeBleStreamConfig');
      return;
    }

    await SharedPreferencesUtil().saveString(
      'nativeBleStreamConfig',
      jsonEncode({
        'deviceId': device.id,
        'codec': codec.toString(),
        'sampleRate': mapCodecToSampleRate(codec),
        'source': _getConversationSourceFromDevice(),
        'apiBaseUrl': Env.apiBaseUrl ?? 'https://api.omiapi.com/',
        'serviceUuid': audioTarget.key,
        'characteristicUuid': audioTarget.value,
        'deviceType': device.type.name,
      }),
    );
    // Batch (offline) capture: tell the native writer where to store .bin files
    // and ensure the native realtime socket is disabled while batch mode is on
    // (batch mode takes precedence over background streaming).
    final batchMode = SharedPreferencesUtil().batchModeEnabled;
    final docsDir = await getApplicationDocumentsDirectory();
    await SharedPreferencesUtil().saveString('batchAudioDir', docsDir.path);

    await SharedPreferencesUtil().saveBool('nativeBleForegroundReady', false);
    await SharedPreferencesUtil().saveBool(
      'nativeBleStreamingEnabled',
      !batchMode && SharedPreferencesUtil().backgroundModeEnabled && device.type != DeviceType.limitless,
    );
    Logger.debug(
      '[batch] config saved: batchMode=$batchMode dir=${docsDir.path} '
      'deviceId=${device.id} svc=${audioTarget.key} char=${audioTarget.value} type=${device.type.name}',
    );
  }

  MapEntry<String, String>? _nativeBleAudioTarget(BtDevice device) {
    switch (device.type) {
      case DeviceType.omi:
      case DeviceType.openglass:
        return const MapEntry(omiServiceUuid, audioDataStreamCharacteristicUuid);
      case DeviceType.friendPendant:
        return const MapEntry(friendPendantServiceUuid, friendPendantAudioCharacteristicUuid);
      case DeviceType.limitless:
        return const MapEntry(limitlessServiceUuid, limitlessRxCharUuid);
      case DeviceType.appleWatch:
      case DeviceType.bee:
      case DeviceType.fieldy:
      case DeviceType.plaud:
      // Ray-Ban Meta audio is bridged from the platform HFP route, so there is
      // no native BLE GATT target; capture runs on the foreground Dart path.
      case DeviceType.raybanMeta:
        return null;
    }
  }

  /// Whether the currently-connected recording device has a concrete native BLE
  /// audio route that the Background Mode / native streaming layer can use.
  /// Returns false for device types with no native route (Apple Watch, Bee,
  /// Fieldy, Limitless, Plaud) and for empty-device-id sentinel entries
  /// that may linger in preferences from stale state.
  @visibleForTesting
  bool get hasNativeBleAudioRoute {
    final device = _recordingDevice;
    if (device == null) return false;
    if (device.id.isEmpty) return false;
    return _nativeBleAudioTarget(device) != null;
  }

  /// Background Mode's native realtime streamer supports a subset of the routed
  /// devices: limitless has a route for batch capture (flash drain), but its
  /// background streaming lands with the native drain engine follow-up.
  bool get hasNativeBackgroundStreamRoute => hasNativeBleAudioRoute && _recordingDevice?.type != DeviceType.limitless;

  /// Enable or disable Background Mode through CaptureProvider so the provider
  /// can validate against the actual native BLE route before committing prefs.
  ///
  /// Returns `true` if the change was accepted, `false` if rejected (e.g. no
  /// connected device or the device lacks a native BLE audio route).
  ///
  /// When disabling: clears `backgroundModeEnabled`, `nativeBleStreamingEnabled`,
  /// and `nativeBleForegroundReady`. It keeps `nativeBleStreamConfig` only when
  /// batch mode is still enabled and the current device has a valid native route,
  /// because native batch writers use the same config for offline capture.
  ///
  /// When enabling with no concrete device or no native route: rejects the
  /// change and leaves all prefs false / removes stale config.
  ///
  /// When enabling with a valid route: sets global opt-in and enables effective
  /// native streaming only when batch mode is off.
  Future<bool> setBackgroundModeEnabled(bool requested) async {
    if (!requested) {
      // Disable realtime background streaming. Preserve nativeBleStreamConfig
      // whenever Transcribe Later remains enabled; batch capture uses the same
      // config for offline audio and may need it even while no route is
      // currently live. Reconnect/setup paths will refresh it when needed.
      final keepBatchConfig = SharedPreferencesUtil().batchModeEnabled;
      SharedPreferencesUtil().backgroundModeEnabled = false;
      await SharedPreferencesUtil().saveBool('nativeBleStreamingEnabled', false);
      await SharedPreferencesUtil().saveBool('nativeBleForegroundReady', false);
      if (!keepBatchConfig) {
        await SharedPreferencesUtil().remove('nativeBleStreamConfig');
      }
      Logger.debug('[BackgroundMode] disabled — keepBatchConfig=$keepBatchConfig');
      notifyListeners();
      return true;
    }

    // Enable: must have a concrete device the native streamer supports.
    if (!hasNativeBackgroundStreamRoute) {
      Logger.debug(
        '[BackgroundMode] enable rejected — no device with native BLE route '
        '(device=${_recordingDevice?.id}, type=${_recordingDevice?.type})',
      );
      // Defensive: ensure prefs stay false and remove any stale config.
      SharedPreferencesUtil().backgroundModeEnabled = false;
      await SharedPreferencesUtil().saveBool('nativeBleStreamingEnabled', false);
      await SharedPreferencesUtil().saveBool('nativeBleForegroundReady', false);
      await SharedPreferencesUtil().remove('nativeBleStreamConfig');
      notifyListeners();
      return false;
    }

    // Valid route — enable and recreate the native config immediately. A user
    // can toggle Background Mode off and back on without reconnecting; in that
    // case the disable/reject paths may have removed nativeBleStreamConfig and
    // the native background streamer cannot start from nativeBleStreamingEnabled
    // alone.
    SharedPreferencesUtil().backgroundModeEnabled = true;
    final device = _recordingDevice!;
    final codec = await _getAudioCodec(device.id);
    final wasForegroundReady = SharedPreferencesUtil().getBool('nativeBleForegroundReady');
    await _saveNativeBleStreamConfig(device, codec);
    if (wasForegroundReady) {
      await SharedPreferencesUtil().saveBool('nativeBleForegroundReady', true);
    }
    Logger.debug(
      '[BackgroundMode] enabled — device ${device.id} '
      'type=${device.type}, batchMode=${SharedPreferencesUtil().batchModeEnabled}',
    );
    notifyListeners();
    return true;
  }

  Future<void> _initiateDevicePhotoStreaming() async {
    if (_recordingDevice == null) return;
    final deviceId = _recordingDevice!.id;
    var connection = await ServiceManager.instance().device.ensureConnection(deviceId);
    if (connection == null) return;

    await connection.performCameraStartPhotoController();
    _blePhotoStream = await connection.performGetImageListener(
      onImageReceived: (orientedImage) async {
        final rotatedImageBytes = rotateImage(orientedImage);
        final String tempId = 'temp_img_${DateTime.now().millisecondsSinceEpoch}';
        final String base64Image = base64Encode(rotatedImageBytes);

        // Add placeholder to UI for immediate feedback
        photos.add(ConversationPhoto(id: tempId, base64: base64Image, createdAt: DateTime.now()));
        photos = List.from(photos);
        notifyListeners();

        // Chunking Logic
        const int chunkSize = 8192; // 8KB chunks
        final totalChunks = (base64Image.length / chunkSize).ceil();

        for (int i = 0; i < totalChunks; i++) {
          final start = i * chunkSize;
          final end = (start + chunkSize > base64Image.length) ? base64Image.length : start + chunkSize;
          final chunk = base64Image.substring(start, end);

          final payload = jsonEncode({
            'type': 'image_chunk',
            'id': tempId,
            'index': i,
            'total': totalChunks,
            'data': chunk,
          });

          if (_socket?.state == SocketServiceState.connected) {
            _socket?.send(payload); // Send the JSON string
          }
          await Future.delayed(const Duration(milliseconds: 20)); // Small delay to prevent flooding
        }
      },
    );
    notifyListeners();
  }

  void clearTranscripts() {
    segments = [];
    hasTranscripts = false;
    notifyListeners();
  }

  void clearUserData() {
    segments = [];
    photos = [];
    hasTranscripts = false;
    _transcriptionServiceStatuses = [];
    suggestionsBySegmentId = {};
    taggingSegmentIds = [];
    notifyListeners();
  }

  void _startMetricsTracking() {
    _metrics.start();
  }

  void _stopMetricsTracking() {
    _metrics.stop();
  }

  /// Triggers a metrics calculation for testing.
  /// This allows verifying that notifyListeners is gated by _metricsNotifyEnabled.
  @visibleForTesting
  void calculateMetricsForTesting() {
    _metrics.calculateForTesting();
  }

  Future _closeBleStream({bool disableNativeBackground = false}) async {
    await _bleBytesStream?.cancel();
    await _blePhotoStream?.cancel();
    await _bleButtonStream?.cancel();
    _stopMetricsTracking();
    if (disableNativeBackground) {
      await SharedPreferencesUtil().saveBool('nativeBleForegroundReady', false);
      await SharedPreferencesUtil().saveBool('nativeBleStreamingEnabled', false);
    } else {
      await SharedPreferencesUtil().saveBool('nativeBleForegroundReady', false);
    }
    if (_recordingDevice != null) {
      var connection = await ServiceManager.instance().device.ensureConnection(_recordingDevice!.id);
      if (connection != null && await connection.hasPhotoStreamingCharacteristic()) {
        await connection.performCameraStopPhotoController();
      }
    }
    notifyListeners();
  }

  @override
  void dispose() {
    _bleBytesStream?.cancel();
    _blePhotoStream?.cancel();
    _bleButtonStream?.cancel();
    _socket?.unsubscribe(this);
    _keepAliveTimer?.cancel();
    _inProgressConversationRefreshTimer?.cancel();
    _connectionStateListener?.cancel();
    _audioInterruptionSubscription?.cancel();
    _metrics.dispose();
    _autoSyncFallbackTimer?.cancel();
    _peopleRefreshFuture = null; // Clear in-flight tracker
    BleBridge.instance.removeBatchRecordingFinalizedListener(_onOfflineRecordingFinalized);

    super.dispose();
  }

  void updateRecordingState(RecordingState state) {
    recordingState = state;
    notifyListeners();
  }

  /// Sends current geolocation to backend if location services are enabled and permission is granted
  Future<void> _sendCurrentGeolocation() async {
    try {
      if (!await Geolocator.isLocationServiceEnabled()) {
        Logger.log('Location service is not enabled, skipping geolocation update');
        return;
      }

      final permission = await Geolocator.checkPermission();
      if (permission == LocationPermission.denied || permission == LocationPermission.deniedForever) {
        Logger.log('Location permission not granted, skipping geolocation update');
        return;
      }

      final position = await Geolocator.getCurrentPosition();
      final geolocation = Geolocation(
        latitude: position.latitude,
        longitude: position.longitude,
        altitude: position.altitude,
        accuracy: position.accuracy,
        time: position.timestamp.toUtc(),
      );

      await updateUserGeolocation(geolocation: geolocation);
    } catch (e) {
      Logger.error('Error sending geolocation: $e');
    }
  }

  streamRecording() async {
    updateRecordingState(RecordingState.initialising);
    await Permission.microphone.request();

    // Send current location when conversation starts
    _sendCurrentGeolocation();

    // prepare
    await changeAudioRecordProfile(audioCodec: BleAudioCodec.pcm16, sampleRate: 16000);

    // Initialize WAL for phone mic recording
    _activeSource = PhoneMicSource();
    _phoneMicWalActive = true;
    await _wal.getSyncs().phone.onAudioCodecChanged(BleAudioCodec.pcm16);
    _wal.getSyncs().phone.setDeviceInfo('phone-mic', 'Phone Microphone');
    setIsWalSupported(true);

    // record
    await ServiceManager.instance().mic.start(
          onByteReceived: (bytes) {
            // Process through AudioSource for frame splitting and sync key generation
            final frames = _activeSource?.processBytes(bytes) ?? [];

            for (final frame in frames) {
              _wal.getSyncs().phone.onFrameCaptured(frame);

              if (_socket?.state == SocketServiceState.connected) {
                _socket?.send(frame.payload);
                _wal.getSyncs().phone.markFrameSynced(frame.syncKey);
              }
            }
          },
          onRecording: () {
            updateRecordingState(RecordingState.record);
          },
          onStop: () {
            if (!_callActive) {
              updateRecordingState(RecordingState.stop);
            }
          },
          onInitializing: () {
            updateRecordingState(RecordingState.initialising);
          },
          onStalled: _onMicStalled,
        );
  }

  stopStreamRecording() async {
    // Flush remaining phone mic WAL buffer before stopping
    if (_phoneMicWalActive) {
      final flushed = _activeSource?.flush() ?? [];
      for (final frame in flushed) {
        _wal.getSyncs().phone.onFrameCaptured(frame);
        if (_socket?.state == SocketServiceState.connected) {
          _socket?.send(frame.payload);
          _wal.getSyncs().phone.markFrameSynced(frame.syncKey);
        }
      }
      _phoneMicWalActive = false;
    }
    await _cleanupCurrentState(disableNativeBackground: true);
    ServiceManager.instance().mic.stop();
    updateRecordingState(RecordingState.stop);
    await _socket?.stop(reason: 'stop stream recording');
  }

  Future streamDeviceRecording({BtDevice? device}) async {
    Logger.debug("streamDeviceRecording $device");
    if (deviceOnboardingProvider == null && SharedPreferencesUtil().batchModeSuspendedForOnboarding) {
      await restoreBatchModeAfterOnboarding();
    }
    if (device != null) _updateRecordingDevice(device);

    bool wasPaused = _isPaused;

    // Send current location when conversation starts
    _sendCurrentGeolocation();

    await _resetStateVariables();
    await _resetState();

    if (wasPaused) {
      await pauseDeviceRecording();
    }
  }

  Future stopStreamDeviceRecording({bool cleanDevice = false}) async {
    await _cleanupCurrentState(disableNativeBackground: true);
    if (cleanDevice) {
      _updateRecordingDevice(null);
    }
    updateRecordingState(RecordingState.stop);
    await _socket?.stop(reason: 'stop stream device recording');
  }

  @override
  void onClosed([int? closeCode]) {
    _transcriptionServiceStatuses = [];
    _transcriptServiceReady = false;

    if (closeCode == 4002) {
      externalActions.markAsOutOfCreditsAndRefresh();
    }

    // Reflect the transcription pipeline break in recordingState. Before this
    // change the UI kept reading "record" while the socket was dead, which
    // looked like active capture to the user (issue #6499). Only flip when we
    // were actively phone-mic recording — device/system-audio flows have their
    // own state lanes.
    if (recordingState == RecordingState.record) {
      updateRecordingState(RecordingState.interrupted);
      final ctx = globalNavigatorKey.currentContext;
      if (ctx != null) {
        AppSnackbar.showSnackbar(ctx.l10n.transcriptionPausedReconnecting, duration: const Duration(seconds: 3));
      }
    }

    // Mark that a device-recording session was interrupted by a network drop.
    // _initiateWebsocket() will call onNetworkSocketReconnected() on the device
    // connection so it can re-enable streaming (e.g. Limitless re-sends the
    // enable-data-stream command after its BLE audio times out).
    if (recordingState == RecordingState.deviceRecord) {
      _socketReconnectPending = true;
    }

    notifyListeners();
    _startKeepAliveServices();
  }

  void _startKeepAliveServices() {
    _keepAliveTimer?.cancel();
    _keepAliveTimer = Timer.periodic(const Duration(seconds: 15), (t) async {
      Logger.debug("[Provider] keep alive");
      // rate 1/15s
      if (_keepAliveLastExecutedAt != null &&
          DateTime.now().subtract(const Duration(seconds: 15)).isBefore(_keepAliveLastExecutedAt!)) {
        Logger.debug("[Provider] keep alive - hitting rate limits 1/15s");
        return;
      }

      _keepAliveLastExecutedAt = DateTime.now();
      if (!recordingDeviceServiceReady || _socket?.state == SocketServiceState.connected) {
        t.cancel();
        return;
      }

      if (!AuthService.instance.isSignedIn()) {
        Logger.debug("[Provider] keep alive - user not signed in, cancelling reconnect");
        t.cancel();
        return;
      }

      if (_recordingDevice != null) {
        BleAudioCodec codec = await _getAudioCodec(_recordingDevice!.id);
        await _initiateWebsocket(audioCodec: codec, source: _getConversationSourceFromDevice());
        return;
      }
      if (recordingState == RecordingState.record || recordingState == RecordingState.interrupted) {
        await _initiateWebsocket(
          audioCodec: BleAudioCodec.pcm16,
          sampleRate: 16000,
          source: ConversationSource.phone.name,
        );
        return;
      }
    });
  }

  @override
  void onError(Object err) {
    _transcriptionServiceStatuses = [];
    _transcriptServiceReady = false;

    notifyListeners();
    _startKeepAliveServices();
  }

  @override
  void onConnected() {
    _transcriptServiceReady = true;
    // Restart mic on reconnect if interrupted (skip during active call).
    if (recordingState == RecordingState.interrupted && !_callActive) {
      if (_activeSource is PhoneMicSource) {
        _restartPhoneMicRecording();
      } else {
        updateRecordingState(RecordingState.record);
      }
    }
    notifyListeners();
  }

  Future refreshInProgressConversations() async {
    _loadInProgressConversation();
  }

  bool get _canRefreshInProgressConversation =>
      recordingDeviceServiceReady ||
      recordingState == RecordingState.initialising ||
      recordingState == RecordingState.interrupted ||
      recordingState == RecordingState.pause ||
      recordingState == RecordingState.deviceRecord;

  void _startInProgressConversationRefresh() {
    if (!_canRefreshInProgressConversation || segments.isNotEmpty || photos.isNotEmpty) return;

    _stopInProgressConversationRefresh();
    _inProgressConversationRefreshAttempts = 0;
    _inProgressConversationRefreshTimer = Timer.periodic(_inProgressConversationRefreshInterval, (_) {
      _refreshInProgressConversationTick();
    });
  }

  void _stopInProgressConversationRefresh() {
    _inProgressConversationRefreshTimer?.cancel();
    _inProgressConversationRefreshTimer = null;
    _inProgressConversationRefreshAttempts = 0;
    _isRefreshingInProgressConversation = false;
  }

  Future<void> _refreshInProgressConversationTick() async {
    if (_isRefreshingInProgressConversation) return;
    if (!_canRefreshInProgressConversation ||
        segments.isNotEmpty ||
        photos.isNotEmpty ||
        _inProgressConversationRefreshAttempts >= _maxInProgressConversationRefreshAttempts) {
      _stopInProgressConversationRefresh();
      return;
    }

    _inProgressConversationRefreshAttempts++;
    _isRefreshingInProgressConversation = true;
    try {
      await _drainNativeBleTranscriptMessages();
      if (segments.isEmpty && photos.isEmpty) {
        await _loadInProgressConversation();
      }
    } finally {
      _isRefreshingInProgressConversation = false;
    }

    if (segments.isNotEmpty ||
        photos.isNotEmpty ||
        _inProgressConversationRefreshAttempts >= _maxInProgressConversationRefreshAttempts) {
      _stopInProgressConversationRefresh();
    }
  }

  Future<void> _drainNativeBleTranscriptMessages() async {
    if (!Platform.isAndroid) return;

    List<String>? messages;
    try {
      messages = await _nativeBleTranscriptChannel.invokeListMethod<String>('drain');
    } on MissingPluginException {
      return;
    } catch (e) {
      Logger.debug('Failed to drain native BLE transcript messages: $e');
      return;
    }

    if (messages == null || messages.isEmpty) return;
    Logger.debug('Draining ${messages.length} native BLE transcript messages');

    for (final message in messages) {
      await _handleNativeBleTranscriptMessage(message);
    }
  }

  Future<void> _handleNativeBleTranscriptMessage(String message) async {
    dynamic jsonEvent;
    try {
      jsonEvent = jsonDecode(message);
    } catch (e) {
      Logger.debug('Failed to decode native BLE transcript message: $e');
      return;
    }

    if (jsonEvent is List) {
      final newSegments = jsonEvent.map((e) => TranscriptSegment.fromJson(e)).toList();
      await _processNewSegmentReceived(newSegments);
      return;
    }

    if (jsonEvent is Map && jsonEvent.containsKey('type')) {
      onMessageEventReceived(MessageEvent.fromJson(Map<String, dynamic>.from(jsonEvent)));
    }
  }

  Future _loadInProgressConversation() async {
    var convos = await getConversations(statuses: [ConversationStatus.in_progress], limit: 1);
    _conversation = convos.isNotEmpty ? convos.first : null;
    if (_conversation != null) {
      segments = _conversation!.transcriptSegments;
      // Merge server photos with locally-captured temp photos to avoid losing
      // photos that haven't been processed server-side yet.
      final serverPhotos = _conversation!.photos;
      final localTempPhotos = photos.where((p) => p.id.startsWith('temp_img_')).toList();
      final serverPhotoIds = serverPhotos.map((p) => p.id).toSet();
      // Keep local temp photos that aren't already on the server
      final mergedPhotos = List<ConversationPhoto>.from(serverPhotos);
      for (final local in localTempPhotos) {
        if (!serverPhotoIds.contains(local.id)) {
          mergedPhotos.add(local);
        }
      }
      photos = mergedPhotos;
    } else {
      segments = [];
      photos = [];
    }
    _segmentsPhotosVersion++; // Bump version so Selector rebuilds
    setHasTranscripts(segments.isNotEmpty);
    notifyListeners();
  }

  @override
  void onMessageEventReceived(MessageEvent event) {
    if (event is ConversationProcessingStartedEvent) {
      externalActions.addProcessingConversation(event.memory);
      _pendingAutoSyncSessionStart = _sessionStartSeconds;
      _pendingAutoSyncConversationId = event.memory.id;

      // Force-drain tail buffer, stamp WALs with conversation ID, then clear state.
      // Store the future so _autoSyncSessionWals() can await it before querying disk WALs.
      _pendingFinalizeAndStamp = _finalizeAndStampSession(_sessionStartSeconds, event.memory.id);

      _resetStateVariables();

      // Start 30s fallback timer in case ConversationEvent never arrives (WS disconnect)
      _autoSyncFallbackTimer?.cancel();
      _autoSyncFallbackTimer = Timer(const Duration(seconds: 30), () {
        if (_pendingAutoSyncSessionStart > 0 && _pendingAutoSyncConversationId != null) {
          final sessionStart = _pendingAutoSyncSessionStart;
          final convId = _pendingAutoSyncConversationId!;
          _pendingAutoSyncSessionStart = 0;
          _pendingAutoSyncConversationId = null;
          Logger.debug('Auto-sync fallback timer fired — syncing WALs to conversation $convId');
          _autoSyncSessionWals(sessionStart, convId);
        }
      });
      return;
    }

    if (event is ConversationEvent) {
      event.memory.isNew = true;
      externalActions.removeProcessingConversation(event.memory.id);
      _processConversationCreated(event.memory, event.messages.cast<ServerMessage>());
      _autoSyncFallbackTimer?.cancel();
      if (_pendingAutoSyncSessionStart > 0) {
        final sessionStart = _pendingAutoSyncSessionStart;
        _pendingAutoSyncSessionStart = 0;
        _pendingAutoSyncConversationId = null;
        _autoSyncSessionWals(sessionStart, event.memory.id);
      }
      return;
    }

    if (event is LastConversationEvent) {
      _handleLastConvoEvent(event.memoryId);
      return;
    }

    if (event is SpeakerLabelSuggestionEvent) {
      _handleSpeakerLabelSuggestionEvent(event);
      return;
    }

    if (event is TranslationEvent) {
      _handleTranslationEvent(event.segments);
      return;
    }

    if (event is SegmentsDeletedEvent) {
      _handleSegmentsDeletedEvent(event);
      return;
    }

    if (event is MessageServiceStatusEvent) {
      // Handle freemium threshold event via status field
      if (event.status == 'freemium_threshold_reached') {
        // Parse as FreemiumThresholdReachedEvent for consistent handling
        final thresholdEvent = FreemiumThresholdReachedEvent.fromJson({'status_text': event.statusText});
        _handleFreemiumThresholdReached(thresholdEvent);
        return;
      }

      _transcriptionServiceStatuses.add(event);
      _transcriptionServiceStatuses = List.from(_transcriptionServiceStatuses);
      notifyListeners();
      return;
    }

    if (event is FreemiumThresholdReachedEvent) {
      _handleFreemiumThresholdReached(event);
      return;
    }

    if (event is PhotoProcessingEvent) {
      final tempId = event.tempId;
      final permanentId = event.photoId;
      final photoIndex = photos.indexWhere((p) => p.id == tempId);
      if (photoIndex != -1) {
        photos[photoIndex].id = permanentId;
        _segmentsPhotosVersion++;
        notifyListeners();
      }
      return;
    }

    if (event is PhotoDescribedEvent) {
      final photoId = event.photoId;
      final description = event.description;
      final discarded = event.discarded;
      final photoIndex = photos.indexWhere((p) => p.id == photoId);
      if (photoIndex != -1) {
        photos[photoIndex].description = description;
        photos[photoIndex].discarded = discarded;
        _segmentsPhotosVersion++;
        notifyListeners();
      }
      return;
    }
  }

  Future<void> forceProcessingCurrentConversation() async {
    final sessionStart = _sessionStartSeconds;

    // Force-drain tail buffer before clearing state
    final phoneSync = _wal.getSyncs().phone;
    await phoneSync.finalizeCurrentSession();

    _resetStateVariables();
    externalActions.addProcessingConversation(
      ServerConversation(
        id: '0',
        createdAt: DateTime.now(),
        structured: Structured('', ''),
        status: ConversationStatus.processing,
      ),
    );
    processInProgressConversation().then((result) async {
      if (result == null || result.conversation == null) {
        externalActions.removeProcessingConversation('0');
        return;
      }
      externalActions.removeProcessingConversation('0');
      result.conversation!.isNew = true;
      _processConversationCreated(result.conversation, result.messages);

      // Stamp WALs with conversation ID and auto-sync
      if (sessionStart > 0 && result.conversation != null) {
        await phoneSync.stampConversationId(sessionStart, result.conversation!.id);
        _autoSyncSessionWals(sessionStart, result.conversation!.id);
      }
    });

    return;
  }

  /// Force-drain tail buffer and stamp all session WALs with conversation ID.
  /// Called from synchronous onMessageEventReceived — fire-and-forget async.
  Future<void> _finalizeAndStampSession(int sessionStartSeconds, String conversationId) async {
    try {
      final phoneSync = _wal.getSyncs().phone;
      await phoneSync.finalizeCurrentSession();
      if (sessionStartSeconds > 0) {
        await phoneSync.stampConversationId(sessionStartSeconds, conversationId);
      }
    } catch (e) {
      Logger.debug('_finalizeAndStampSession error: $e');
    }
  }

  Future<void> _autoSyncSessionWals(int sessionStartSeconds, String conversationId) async {
    // Third-party STT users opt out of auto-sync: offline files can only be
    // transcribed on Omi's servers (counting toward their limit), not on their
    // own provider. They sync manually with an explicit confirmation instead.
    if (SharedPreferencesUtil().useCustomStt) {
      Logger.debug('Auto-sync skipped: custom STT provider enabled');
      return;
    }
    // Omi users can opt out of auto-sync from device settings; they back up
    // manually instead. Defaults to on.
    if (!SharedPreferencesUtil().autoSyncOfflineRecordings) {
      Logger.debug('Auto-sync skipped: disabled by user');
      return;
    }
    // Wait for finalize+stamp to complete so tail buffer WALs are on disk before querying.
    if (_pendingFinalizeAndStamp != null) {
      await _pendingFinalizeAndStamp;
      _pendingFinalizeAndStamp = null;
    }
    final phoneSync = _wal.getSyncs().phone;
    final unsyncedWals = phoneSync.getSessionUnsyncedWals(sessionStartSeconds);
    if (unsyncedWals.isEmpty) return;

    Logger.debug('Auto-syncing ${unsyncedWals.length} session WALs to conversation $conversationId');
    for (final wal in unsyncedWals) {
      await _syncSingleWal(wal, conversationId, phoneSync);
    }
  }

  /// Sync a single WAL to a conversation with retry and backoff.
  /// Retries up to 3 times with exponential delays (5s, 10s, 20s).
  /// Network/transient errors (SocketException, no connectivity) do NOT increment retryCount.
  Future<void> _syncSingleWal(Wal wal, String conversationId, LocalWalSyncImpl phoneSync) async {
    if (wal.filePath == null) {
      Logger.debug('Auto-sync WAL ${wal.id}: no filePath, marking corrupted');
      wal.status = WalStatus.corrupted;
      await phoneSync.persistRetryMetadata(wal);
      return;
    }
    final fullPath = await Wal.getFilePath(wal.filePath);
    if (fullPath == null) {
      Logger.debug('Auto-sync WAL ${wal.id}: path resolution failed, marking corrupted');
      wal.status = WalStatus.corrupted;
      await phoneSync.persistRetryMetadata(wal);
      return;
    }
    final file = File(fullPath);
    if (!file.existsSync()) {
      Logger.debug('Auto-sync WAL ${wal.id}: file missing, marking corrupted');
      wal.status = WalStatus.corrupted;
      await phoneSync.persistRetryMetadata(wal);
      return;
    }

    if (!_isConnected) {
      Logger.debug('Auto-sync WAL ${wal.id}: offline, will retry later');
      return;
    }

    // Honor an active fair-use cooldown: don't fire uploads that will just be
    // 429'd, which amplifies the throttle and mislabels recordings as failed.
    if (SyncRateLimiter.instance.isLimited) {
      Logger.debug('Auto-sync WAL ${wal.id}: rate-limited until ${SyncRateLimiter.instance.until}, skipping');
      return;
    }

    // Upload only — no poll-to-terminal, no in-method retry loop. On 202 the
    // WAL becomes `uploaded` and the SyncReconciler resolves the job out of
    // band; on real failure we bump retryCount so orphan recovery / the next
    // sync retries (the local file is retained until confirmed synced).
    try {
      final result = await SyncUploadGate.instance.upload([file], conversationId: conversationId);
      if (result.completed != null) {
        // 200 fast-path: server already produced the result.
        await phoneSync.markWalSyncedAndPersist(wal);
      } else {
        wal.status = WalStatus.uploaded;
        wal.jobId = result.jobId;
        wal.uploadedAt = DateTime.now().millisecondsSinceEpoch ~/ 1000;
        await phoneSync.persistRetryMetadata(wal); // persists the WAL list
        SyncReconciler.instance.poke();
      }
    } on SyncRateLimitedException {
      // Account-level rate limit — do not bump retryCount. The WAL stays
      // pending and the global upload gate owns the cooldown.
      Logger.debug('Auto-sync WAL ${wal.id}: rate-limited, paused until ${SyncRateLimiter.instance.until}');
    } on SocketException {
      Logger.debug('Auto-sync WAL ${wal.id}: network error, aborting without incrementing retryCount');
    } catch (e) {
      wal.retryCount = wal.retryCount + 1;
      wal.lastRetryAt = DateTime.now().millisecondsSinceEpoch ~/ 1000;
      await phoneSync.persistRetryMetadata(wal);
      Logger.debug('Auto-sync WAL ${wal.id} upload failed (retryCount=${wal.retryCount}): $e');
    }
  }

  /// Recover orphaned WALs on startup. Called once after providers are initialized.
  /// Finds WALs with conversationId set but status still miss, and syncs them.
  /// Skips recovery if offline — retryCount is not incremented for transient failures.
  Future<void> recoverOrphanedWals() async {
    // Custom STT users never auto-sync (offline files would use Omi STT + count
    // toward their limit). They back up manually with explicit confirmation.
    if (SharedPreferencesUtil().useCustomStt) {
      Logger.debug('Orphan WAL recovery skipped: custom STT provider enabled');
      return;
    }
    // Honor the user's auto-sync opt-out (device settings). Defaults to on.
    if (!SharedPreferencesUtil().autoSyncOfflineRecordings) {
      Logger.debug('Orphan WAL recovery skipped: auto-sync disabled by user');
      return;
    }
    if (!_isConnected) {
      Logger.debug('Startup recovery: offline, skipping orphan WAL sync');
      _orphanRecoveryDone = false; // Allow retry on next external action update.
      return;
    }
    final phoneSync = _wal.getSyncs().phone;
    await phoneSync.walReady; // Wait for WALs to be loaded from disk
    final orphaned = phoneSync.getOrphanedWals();
    if (orphaned.isEmpty) return;

    Logger.debug('Startup recovery: found ${orphaned.length} orphaned WALs to sync');
    for (final wal in orphaned) {
      await _syncSingleWal(wal, wal.conversationId!, phoneSync);
    }
    // Check if any orphaned WALs remain (e.g., transient SocketException while "online").
    // If so, allow onConnectionStateChanged to re-trigger recovery on next transition.
    final remaining = phoneSync.getOrphanedWals();
    if (remaining.isNotEmpty) {
      _orphanRecoveryDone = false;
    }
  }

  Future<void> _processConversationCreated(ServerConversation? conversation, List<ServerMessage> messages) async {
    if (conversation == null) return;

    // Star the conversation if it was marked for starring
    if (_starOngoingConversation) {
      Logger.debug("Conversation was marked for starring, applying star");
      _starOngoingConversation = false; // Reset the flag
      conversation.starred = true;
      // Call API to star the conversation
      await setConversationStarred(conversation.id, true);
    }

    externalActions.upsertConversation(conversation);
    PlatformManager.instance.analytics.conversationCreated(conversation);
  }

  Future<void> _handleLastConvoEvent(String memoryId) async {
    bool conversationExists = externalActions.hasConversation(memoryId);
    if (conversationExists) {
      return;
    }
    ServerConversation? conversation = await getConversationById(memoryId);
    if (conversation != null) {
      Logger.debug("Adding last conversation to conversations: $memoryId");
      externalActions.upsertConversation(conversation);
    } else {
      Logger.debug("Failed to fetch last conversation: $memoryId");
    }
  }

  void _handleTranslationEvent(List<TranscriptSegment> translatedSegments) {
    try {
      if (translatedSegments.isEmpty) return;

      Logger.debug("Received ${translatedSegments.length} translated segments");

      // Update the segments with the translated ones
      var remainSegments = TranscriptSegment.updateSegments(segments, translatedSegments);
      if (remainSegments.isNotEmpty) {
        Logger.debug("Adding ${remainSegments.length} new translated segments");
      }

      _segmentsPhotosVersion++;
      notifyListeners();
    } catch (e) {
      Logger.debug("Error handling translation event: $e");
    }
  }

  void _handleSegmentsDeletedEvent(SegmentsDeletedEvent event) {
    if (event.segmentIds.isEmpty) return;

    segments.removeWhere((segment) => event.segmentIds.contains(segment.id));
    suggestionsBySegmentId.removeWhere((key, value) => event.segmentIds.contains(key));
    taggingSegmentIds.removeWhere((id) => event.segmentIds.contains(id));
    hasTranscripts = segments.isNotEmpty;
    _segmentsPhotosVersion++;
    notifyListeners();
  }

  void _handleSpeakerLabelSuggestionEvent(SpeakerLabelSuggestionEvent event) {
    // Tagging
    if (taggingSegmentIds.contains(event.segmentId)) {
      return;
    }
    // If segment already exists, check if it's assigned. If so, ignore suggestion.
    var segment = segments.firstWhereOrNull((s) => s.id == event.segmentId);
    if (segment != null && segment.id.isNotEmpty && (segment.personId != null || segment.isUser)) {
      return;
    }

    // Add backend-created person to local cache for UI display (backward compatibility)
    final isUser = event.personId == 'user';
    if (!isUser && event.personId.isNotEmpty && SharedPreferencesUtil().getPersonById(event.personId) == null) {
      SharedPreferencesUtil().addCachedPerson(
        Person(id: event.personId, name: event.personName, createdAt: DateTime.now(), updatedAt: DateTime.now()),
      );
    }

    // Auto-apply assignment if backend provided personId (speaker_auto_assign=enabled)
    if (event.personId.isNotEmpty) {
      for (var seg in segments) {
        if (seg.speakerId == event.speakerId) {
          seg.isUser = isUser;
          seg.personId = isUser ? null : event.personId;
        }
      }
      _segmentsPhotosVersion++; // Trigger UI rebuild after auto-apply
    }
    notifyListeners();
  }

  Future<void> assignSpeakerToConversation(
    int speakerId,
    String personId,
    String personName,
    List<String> segmentIds,
  ) async {
    if (segmentIds.isEmpty) return;

    taggingSegmentIds = List.from(segmentIds);
    notifyListeners();

    try {
      String finalPersonId = personId;

      // Create person if new (old app path - calls idempotent API)
      if (finalPersonId.isEmpty) {
        Person? newPerson = await externalActions.createPerson(personName);
        if (newPerson != null) {
          finalPersonId = newPerson.id;
        }
      }

      // Add person to local cache if not exists (backward compatibility for old apps)
      if (finalPersonId.isNotEmpty &&
          finalPersonId != 'user' &&
          SharedPreferencesUtil().getPersonById(finalPersonId) == null) {
        SharedPreferencesUtil().addCachedPerson(
          Person(id: finalPersonId, name: personName, createdAt: DateTime.now(), updatedAt: DateTime.now()),
        );
      }

      // Find conversation id
      if (_conversation == null) return;

      final isAssigningToUser = finalPersonId == 'user';

      // Update all segments with this speakerId for UI consistency
      for (var segment in segments) {
        if (segment.speakerId == speakerId) {
          segment.isUser = isAssigningToUser;
          segment.personId = isAssigningToUser ? null : finalPersonId;
        }
      }
      _segmentsPhotosVersion++; // Bump version so Selector rebuilds

      // Persist change
      await assignBulkConversationTranscriptSegments(
        _conversation!.id,
        segmentIds,
        isUser: isAssigningToUser,
        personId: isAssigningToUser ? null : finalPersonId,
      );

      // Notify backend session
      if (_socket?.state == SocketServiceState.connected) {
        final payload = jsonEncode({
          'type': 'speaker_assigned',
          'speaker_id': speakerId,
          'person_id': finalPersonId,
          'person_name': personName,
          'segment_ids': segmentIds,
        });
        _socket?.send(payload);
      }

      // Remove all suggestions for this speakerId
      suggestionsBySegmentId.removeWhere((key, value) => value.speakerId == speakerId);
    } finally {
      taggingSegmentIds = [];
      notifyListeners();
    }
  }

  @override
  void onSegmentReceived(List<TranscriptSegment> newSegments) {
    // Forward to interactive device onboarding if active on transcription step
    if (deviceOnboardingProvider?.isOnboardingActive == true && deviceOnboardingProvider!.currentStep == 0) {
      deviceOnboardingProvider!.onTranscriptSegments(newSegments);
    }
    _processNewSegmentReceived(newSegments);
  }

  Future<void> _processNewSegmentReceived(List<TranscriptSegment> newSegments) async {
    if (newSegments.isEmpty) return;

    if (segments.isEmpty && !_isLoadingInProgressConversation) {
      _isLoadingInProgressConversation = true;
      FlutterForegroundTask.sendDataToTask(jsonEncode({'location': true}));
      try {
        await _loadInProgressConversation();
      } finally {
        _isLoadingInProgressConversation = false;
      }
    }

    final remainSegments = TranscriptSegment.updateSegments(segments, newSegments);
    segments.addAll(remainSegments);

    // Refresh people cache if we see unknown personIds (backend-created persons)
    // Check all newSegments, not just remainSegments, to catch updates to existing segments
    if (_peopleRefreshFuture == null && _hasMissingPerson(newSegments)) {
      _peopleRefreshFuture = externalActions.refreshPeople().whenComplete(() {
        _peopleRefreshFuture = null;
      });
    }

    _segmentsPhotosVersion++; // Bump version so Selector rebuilds
    hasTranscripts = true;
    notifyListeners();
  }

  void onConnectionStateChanged(bool isConnected) {
    _isConnected = isConnected;
    // When coming back online, retry orphan recovery if it was skipped due to being offline
    if (isConnected && !_orphanRecoveryDone) {
      _orphanRecoveryDone = true;
      recoverOrphanedWals();
    }
    notifyListeners();
  }

  // ============== Freemium: Threshold Notification ==============

  /// Handle freemium threshold reached: Notify user based on required action
  void _handleFreemiumThresholdReached(FreemiumThresholdReachedEvent event) {
    if (!_freemiumThreshold.handle(event)) return;

    // Update usage provider to reflect approaching limit
    externalActions.refreshSubscription();

    notifyListeners();
  }

  /// Callback for external components to reset their freemium session state
  VoidCallback? onFreemiumSessionReset;

  /// Reset freemium threshold state (e.g., when credits reset or on new session)
  void resetFreemiumThresholdState() {
    _freemiumThreshold.reset();
    // Notify external handlers (e.g., FreemiumSwitchHandler)
    onFreemiumSessionReset?.call();
    notifyListeners();
  }

  /// Check if credits were restored and reset threshold state
  Future<void> checkCreditsAndResetThresholdIfNeeded() async {
    await externalActions.fetchSubscription();
    if (externalActions.isOutOfCredits == false && _freemiumThreshold.reached) {
      Logger.debug('[Freemium] Credits restored! Resetting threshold state.');
      resetFreemiumThresholdState();
    }
  }

  void setIsWalSupported(bool value) {
    _isWalSupported = value;
    notifyListeners();
  }

  Future<void> pauseDeviceRecording() async {
    if (_recordingDevice == null) return;

    // Write mute state first — before BLE cancel which may fire other events
    await BatteryWidgetService().updateMuteState(true);
    // Pause the BLE stream but keep the device connection
    await _bleBytesStream?.cancel();
    await SharedPreferencesUtil().saveBool('nativeBleForegroundReady', false);
    await SharedPreferencesUtil().saveBool('nativeBleStreamingEnabled', false);
    _isPaused = true;
    // Persist so the mute survives an app kill/restart, not just a reconnect.
    SharedPreferencesUtil().deviceMuted = true;
    updateRecordingState(RecordingState.pause);
    notifyListeners();
  }

  Future<void> resumeDeviceRecording() async {
    if (_recordingDevice == null) return;
    _isPaused = false;
    // Clear the persisted mute so we don't re-mute on the next restart.
    SharedPreferencesUtil().deviceMuted = false;
    // Update widget immediately — don't wait for streaming setup
    BatteryWidgetService().updateMuteState(false);
    // Resume streaming from the device
    await _initiateDeviceAudioStreaming();

    updateRecordingState(RecordingState.deviceRecord);
    notifyListeners();
  }
}
