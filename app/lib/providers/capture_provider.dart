import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:collection/collection.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:flutter_provider_utilities/flutter_provider_utilities.dart';
import 'package:geolocator/geolocator.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/geolocation.dart';
import 'package:omi/backend/schema/message.dart';
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
        FreemiumThresholdReachedEvent;
import 'package:omi/backend/schema/person.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/providers/calendar_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/models/custom_stt_config.dart';
import 'package:omi/models/stt_provider.dart';
import 'package:omi/services/connectivity_service.dart';
import 'package:omi/services/services.dart';
import 'package:omi/services/sockets/transcription_service.dart';
import 'package:omi/services/wals.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:omi/utils/debug_log_manager.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/enums.dart';
import 'package:omi/utils/image/image_utils.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/platform/platform_service.dart';
import 'package:path_provider/path_provider.dart';
import 'package:permission_handler/permission_handler.dart';

class CaptureProvider extends ChangeNotifier
    with MessageNotifierMixin, WidgetsBindingObserver
    implements ITransctiptSegmentSocketServiceListener {
  ConversationProvider? conversationProvider;
  MessageProvider? messageProvider;
  PeopleProvider? peopleProvider;
  UsageProvider? usageProvider;
  CalendarProvider? calendarProvider;

  TranscriptSegmentSocketService? _socket;
  Timer? _keepAliveTimer;
  DateTime? _keepAliveLastExecutedAt;

  // Method channel for system audio permissions
  static late MethodChannel _screenCaptureChannel;
  static late MethodChannel _controlBarChannel;

  IWalService get _wal => ServiceManager.instance().wal;

  bool _isWalSupported = false;

  bool get isWalSupported => _isWalSupported;

  StreamSubscription<bool>? _connectionStateListener;
  bool _isConnected = ConnectivityService().isConnected;

  get isConnected => _isConnected;

  String? microphoneName;
  double microphoneLevel = 0.0;
  double systemAudioLevel = 0.0;

  bool _isAutoReconnecting = false;
  bool get isAutoReconnecting => _isAutoReconnecting;

  bool get outOfCredits => usageProvider?.isOutOfCredits ?? false;

  // Freemium: Threshold notification state
  bool _freemiumThresholdReached = false;
  int _freemiumRemainingSeconds = 0;
  bool _freemiumRequiresUserAction = false;

  bool get freemiumThresholdReached => _freemiumThresholdReached;
  int get freemiumRemainingSeconds => _freemiumRemainingSeconds;

  /// Whether user needs to take action (e.g., setup on-device STT)
  bool get freemiumRequiresUserAction => _freemiumRequiresUserAction;

  Timer? _reconnectTimer;
  int _reconnectCountdown = 5;
  int get reconnectCountdown => _reconnectCountdown;

  Timer? _recordingTimer;
  int _recordingDuration = 0; // in seconds

  int _getRecordingDuration() => _recordingDuration;

  List<MessageEvent> _transcriptionServiceStatuses = [];
  List<MessageEvent> get transcriptionServiceStatuses => _transcriptionServiceStatuses;

  List<int> _systemAudioBuffer = [];
  bool _systemAudioCaching = true;

  bool _isLoadingInProgressConversation = false;

  // BLE streaming metrics
  int _blesBytesReceived = 0;
  int _wsSocketBytesSent = 0;
  double _bleReceiveRateKbps = 0.0;
  double _wsSendRateKbps = 0.0;
  DateTime? _metricsLastCalculated;
  Timer? _metricsTimer;

  double get bleReceiveRateKbps => _bleReceiveRateKbps;
  double get wsSendRateKbps => _wsSendRateKbps;

  CaptureProvider() {
    _connectionStateListener = ConnectivityService().onConnectionChange.listen((bool isConnected) {
      onConnectionStateChanged(isConnected);
    });

    if (PlatformService.isDesktop) {
      _screenCaptureChannel = const MethodChannel('screenCapturePlatform');
      _controlBarChannel = const MethodChannel('com.omi/floating_control_bar');

      _initializeAppLifecycleListener();

      WidgetsBinding.instance.addPostFrameCallback((_) {
        _controlBarChannel.setMethodCallHandler(_handleFloatingControlBarMethodCall);
        ServiceManager.instance().systemAudio.setOnRecordingStartedFromNub(_handleRecordingStartedFromNub);
        ServiceManager.instance().systemAudio.setIsRecordingPausedCallback(() => _isPaused);
      });
    }
  }

  void _initializeAppLifecycleListener() {
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    super.didChangeAppLifecycleState(state);

    DebugLogManager.logEvent('app_lifecycle_changed', {
      'state': state.name,
      'recording_state': recordingState.name,
      'has_device': _recordingDevice != null,
      'socket_connected': _socket?.state == SocketServiceState.connected,
    });

    if (state == AppLifecycleState.resumed) {
      _handleAppResumed();
    }
  }

  void _handleAppResumed() async {
    if (!PlatformService.isDesktop || !_shouldAutoResumeAfterWake) return;

    try {
      final nativeRecording = await _screenCaptureChannel.invokeMethod('isRecording') ?? false;

      if (!nativeRecording && recordingState != RecordingState.stop) {
        updateRecordingState(RecordingState.stop);
        await _socket?.stop(reason: 'native recording stopped during sleep');
      }

      if (!nativeRecording && recordingState == RecordingState.stop) {
        await Future.delayed(const Duration(seconds: 2));
        await streamSystemAudioRecording();
      }
    } catch (e) {
      debugPrint('[AutoRecord] Resume error: $e');
    }
  }

  void updateProviderInstances(ConversationProvider? cp, MessageProvider? mp, PeopleProvider? pp, UsageProvider? up) {
    conversationProvider = cp;
    messageProvider = mp;
    peopleProvider = pp;
    usageProvider = up;

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
      case DeviceType.frame:
        return 'frame';
      case DeviceType.appleWatch:
        return 'apple_watch';
      case DeviceType.limitless:
        return 'limitless';
    }
  }

  ServerConversation? _conversation;
  List<TranscriptSegment> segments = [];
  List<ConversationPhoto> photos = [];
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

  StreamSubscription? _storageStream;

  get storageStream => _storageStream;

  RecordingState recordingState = RecordingState.stop;

  bool _isPaused = false;
  bool get isPaused => _isPaused;

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

  // Session-based auto-resume flag
  // Always true on app start, set to false only when user manually stops/pauses
  bool _shouldAutoResumeAfterWake = true;
  bool get shouldAutoResumeAfterWake => _shouldAutoResumeAfterWake;

  bool _transcriptServiceReady = false;

  bool get transcriptServiceReady => _transcriptServiceReady && _isConnected;

  // having a connected device or using the phone's mic for recording
  bool get recordingDeviceServiceReady =>
      _recordingDevice != null ||
      recordingState == RecordingState.record ||
      recordingState == RecordingState.systemAudioRecord;

  bool get havingRecordingDevice => _recordingDevice != null;

  BtDevice? get recordingDevice => _recordingDevice;

  void setHasTranscripts(bool value) {
    hasTranscripts = value;
    notifyListeners();
  }

  void setConversationCreating(bool value) {
    debugPrint('set Conversation creating $value');
    // ConversationCreating = value;
    notifyListeners();
  }

  void _updateRecordingDevice(BtDevice? device) {
    debugPrint('connected device changed from ${_recordingDevice?.id} to ${device?.id}');
    _recordingDevice = device;
    notifyListeners();
  }

  void updateRecordingDevice(BtDevice? device) {
    _updateRecordingDevice(device);
  }

  Future _resetStateVariables() async {
    segments = [];
    photos = [];
    hasTranscripts = false;
    suggestionsBySegmentId = {};
    _conversation = null;
    taggingSegmentIds = [];
    notifyListeners();
  }

  Future<void> onRecordProfileSettingChanged() async {
    await _resetState();
  }

  /// Called when transcription settings are changed (e.g., custom STT provider)
  /// This resets the socket connection to use the new configuration
  Future<void> onTranscriptionSettingsChanged() async {
    debugPrint("Transcription settings changed, refreshing socket connection...");

    // Handle device recording
    if (_recordingDevice != null) {
      await _socket?.stop(reason: 'transcription settings changed');
      BleAudioCodec codec = await _getAudioCodec(_recordingDevice!.id);
      await _initiateWebsocket(
        audioCodec: codec,
        force: true,
        source: _getConversationSourceFromDevice(),
      );
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

    // Handle system audio recording (desktop)
    if (recordingState == RecordingState.systemAudioRecord) {
      await _socket?.stop(reason: 'transcription settings changed');
      await _initiateWebsocket(
        audioCodec: BleAudioCodec.pcm16,
        sampleRate: 16000,
        force: true,
        source: ConversationSource.desktop.name,
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
        audioCodec: audioCodec, sampleRate: sampleRate, channels: channels, isPcm: isPcm, source: source);
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
      debugPrint('[CustomSTT] Codec $codec not supported, falling back to Omi');
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
      debugPrint("Can not create new conversation socket");
      return;
    }
    _socket?.subscribe(this, this);
    _transcriptServiceReady = true;

    _loadInProgressConversation();

    notifyListeners();
  }

  void _processVoiceCommandBytes(String deviceId, List<List<int>> data) async {
    if (data.isEmpty) {
      debugPrint("voice frames is empty");
      return;
    }

    BleAudioCodec codec = await _getAudioCodec(_recordingDevice!.id);
    if (messageProvider != null) {
      await messageProvider?.sendVoiceMessageStreamToServer(
        data,
        onFirstChunkRecived: () {
          _playSpeakerHaptic(deviceId, 2);
        },
        codec: codec,
      );
    }
  }

  // Just incase the ble connection get loss
  void _watchVoiceCommands(String deviceId, DateTime session) {
    Timer.periodic(const Duration(seconds: 3), (t) async {
      debugPrint("voice command watch");
      if (session != _voiceCommandSession) {
        t.cancel();
        return;
      }
      var value = await _getBleButtonState(deviceId);
      if (value.isEmpty || value.length < 4) return;
      var buttonState = ByteData.view(Uint8List.fromList(value.sublist(0, 4).reversed.toList()).buffer).getUint32(0);
      debugPrint("watch device button $buttonState");

      // Force process
      if (buttonState == 5 && session == _voiceCommandSession) {
        _voiceCommandSession = null; // end session
        var data = List<List<int>>.from(_commandBytes);
        _commandBytes = [];
        _processVoiceCommandBytes(deviceId, data);
      }
    });
  }

  Future streamButton(String deviceId) async {
    debugPrint('streamButton in capture_provider');
    _bleButtonStream?.cancel();
    _bleButtonStream = await _getBleButtonListener(deviceId, onButtonReceived: (List<int> value) {
      final snapshot = List<int>.from(value);
      if (snapshot.isEmpty || snapshot.length < 4) return;
      var buttonState = ByteData.view(Uint8List.fromList(snapshot.sublist(0, 4).reversed.toList()).buffer).getUint32(0);
      debugPrint("device button $buttonState");

      // double tap
      if (buttonState == 2) {
        debugPrint("Double tap detected");

        // Guard: ignore if already processing a button event
        if (_isProcessingButtonEvent) {
          debugPrint("Double tap: already processing, ignoring");
          return;
        }

        int doubleTapAction = SharedPreferencesUtil().doubleTapAction;

        if (doubleTapAction == 1) {
          // Pause/resume recording
          debugPrint("Double tap: toggling pause/mute");
          _isProcessingButtonEvent = true;
          if (_isPaused) {
            MixpanelManager().omiDoubleTap(feature: 'unmute');
            resumeDeviceRecording().then((_) {
              _isProcessingButtonEvent = false;
            }).catchError((e) {
              debugPrint("Error resuming device recording: $e");
              _isProcessingButtonEvent = false;
            });
          } else {
            MixpanelManager().omiDoubleTap(feature: 'mute');
            pauseDeviceRecording().then((_) {
              _isProcessingButtonEvent = false;
            }).catchError((e) {
              debugPrint("Error pausing device recording: $e");
              _isProcessingButtonEvent = false;
            });
          }
        } else if (doubleTapAction == 2) {
          // Star ongoing conversation (doesn't end it)
          debugPrint("Double tap: marking conversation for starring");
          if (!_starOngoingConversation) {
            markConversationForStarring();
            MixpanelManager().omiDoubleTap(feature: 'star_conversation');
            // Haptic feedback to confirm
            HapticFeedback.mediumImpact();
          } else {
            // Toggle off if already marked
            unmarkConversationForStarring();
            MixpanelManager().omiDoubleTap(feature: 'unstar_conversation');
            HapticFeedback.lightImpact();
          }
        } else {
          // End conversation and process (default)
          debugPrint("Double tap: processing conversation");
          MixpanelManager().omiDoubleTap(feature: 'process_conversation');
          forceProcessingCurrentConversation();
        }
        return;
      }

      // start long press (for voice commands)
      if (buttonState == 3 && _voiceCommandSession == null) {
        _voiceCommandSession = DateTime.now();
        _commandBytes = [];
        _watchVoiceCommands(deviceId, _voiceCommandSession!);
        _playSpeakerHaptic(deviceId, 1);
      }

      // release (end voice command)
      if (buttonState == 5 && _voiceCommandSession != null) {
        _voiceCommandSession = null; // end session
        var data = List<List<int>>.from(_commandBytes);
        _commandBytes = [];
        _processVoiceCommandBytes(deviceId, data);
      }
    });
  }

  Future streamAudioToWs(String deviceId, BleAudioCodec codec) async {
    debugPrint('streamAudioToWs in capture_provider');
    _bleBytesStream?.cancel();
    _startMetricsTracking();
    _bleBytesStream = await _getBleAudioBytesListener(deviceId, onAudioBytesReceived: (List<int> value) {
      final snapshot = List<int>.from(value);
      if (snapshot.isEmpty || snapshot.length < 3) return;

      // Track bytes received from BLE
      _blesBytesReceived += snapshot.length;

      // Command button triggered
      bool voiceCommandSupported = _recordingDevice != null
          ? (_recordingDevice?.type == DeviceType.omi || _recordingDevice?.type == DeviceType.openglass)
          : false;
      if (_voiceCommandSession != null && voiceCommandSupported) {
        _commandBytes.add(snapshot.sublist(3));
      }

      // Local storage syncs
      var checkWalSupported =
          (_recordingDevice?.type == DeviceType.omi || _recordingDevice?.type == DeviceType.openglass) &&
              codec.isOpusSupported() &&
              (_socket?.state != SocketServiceState.connected || SharedPreferencesUtil().unlimitedLocalStorageEnabled);
      if (checkWalSupported != _isWalSupported) {
        setIsWalSupported(checkWalSupported);
      }
      if (_isWalSupported) {
        _wal.getSyncs().phone.onByteStream(snapshot);
      }

      // Send WS
      if (_socket?.state == SocketServiceState.connected) {
        final paddingLeft =
            (_recordingDevice?.type == DeviceType.omi || _recordingDevice?.type == DeviceType.openglass) ? 3 : 0;
        final trimmedValue = paddingLeft > 0 ? value.sublist(paddingLeft) : value;
        _socket?.send(trimmedValue);

        // Track bytes sent to websocket
        _wsSocketBytesSent += trimmedValue.length;

        // Mark as synced
        if (_isWalSupported) {
          _wal.getSyncs().phone.onBytesSync(value);
        }
      }
    });
    notifyListeners();
  }

  Future<void> _resetState() async {
    debugPrint('resetState');
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

  Future _cleanupCurrentState() async {
    await _closeBleStream();
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

  Future<List<int>> _getBleButtonState(String deviceId) async {
    var connection = await ServiceManager.instance().device.ensureConnection(deviceId);
    if (connection == null) {
      return Future.value(<int>[]);
    }
    return connection.getBleButtonState();
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

    // Set device info for WAL creation
    final pd = await device.getDeviceInfo(connection);
    final deviceModel = pd.modelNumber.isNotEmpty ? pd.modelNumber : "Omi";
    _wal.getSyncs().phone.setDeviceInfo(deviceId, deviceModel);

    await streamButton(deviceId);
    await streamAudioToWs(deviceId, codec);

    // Update state
    updateRecordingState(RecordingState.deviceRecord);
    notifyListeners();
  }

  Future<void> _initiateDevicePhotoStreaming() async {
    if (_recordingDevice == null) return;
    final deviceId = _recordingDevice!.id;
    var connection = await ServiceManager.instance().device.ensureConnection(deviceId);
    if (connection == null) return;

    await connection.performCameraStartPhotoController();
    _blePhotoStream = await connection.performGetImageListener(onImageReceived: (orientedImage) async {
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
    });
    notifyListeners();
  }

  void clearTranscripts() {
    segments = [];
    hasTranscripts = false;
    notifyListeners();
  }

  void _startMetricsTracking() {
    _blesBytesReceived = 0;
    _wsSocketBytesSent = 0;
    _bleReceiveRateKbps = 0.0;
    _wsSendRateKbps = 0.0;
    _metricsLastCalculated = DateTime.now();

    _metricsTimer?.cancel();
    _metricsTimer = Timer.periodic(const Duration(seconds: 5), (timer) {
      _calculateMetricsRates();
    });
  }

  void _calculateMetricsRates() {
    final now = DateTime.now();
    if (_metricsLastCalculated == null) {
      _metricsLastCalculated = now;
      return;
    }

    final elapsedSeconds = now.difference(_metricsLastCalculated!).inMilliseconds / 1000.0;
    if (elapsedSeconds > 0) {
      // Calculate kbps (kilobits per second)
      _bleReceiveRateKbps = (_blesBytesReceived * 8) / (elapsedSeconds * 1000);
      _wsSendRateKbps = (_wsSocketBytesSent * 8) / (elapsedSeconds * 1000);

      // Reset counters for next interval
      _blesBytesReceived = 0;
      _wsSocketBytesSent = 0;
      _metricsLastCalculated = now;

      notifyListeners();
    }
  }

  void _stopMetricsTracking() {
    _metricsTimer?.cancel();
    _metricsTimer = null;
    _blesBytesReceived = 0;
    _wsSocketBytesSent = 0;
    _bleReceiveRateKbps = 0.0;
    _wsSendRateKbps = 0.0;
    _metricsLastCalculated = null;
    notifyListeners();
  }

  Future _closeBleStream() async {
    await _bleBytesStream?.cancel();
    await _blePhotoStream?.cancel();
    _stopMetricsTracking();
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
    _socket?.unsubscribe(this);
    _keepAliveTimer?.cancel();
    _connectionStateListener?.cancel();
    _recordingTimer?.cancel();
    _metricsTimer?.cancel();

    // Remove lifecycle observer
    if (PlatformService.isDesktop) {
      WidgetsBinding.instance.removeObserver(this);
    }

    super.dispose();
  }

  void updateRecordingState(RecordingState state) {
    recordingState = state;
    notifyListeners();
    _broadcastRecordingState();
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

    // record
    await ServiceManager.instance().mic.start(onByteReceived: (bytes) {
      if (_socket?.state == SocketServiceState.connected) {
        _socket?.send(bytes);
      }
    }, onRecording: () {
      updateRecordingState(RecordingState.record);
    }, onStop: () {
      updateRecordingState(RecordingState.stop);
    }, onInitializing: () {
      updateRecordingState(RecordingState.initialising);
    });
  }

  stopStreamRecording() async {
    await _cleanupCurrentState();
    ServiceManager.instance().mic.stop();
    updateRecordingState(RecordingState.stop);
    await _socket?.stop(reason: 'stop stream recording');
  }

  Future streamDeviceRecording({BtDevice? device}) async {
    debugPrint("streamDeviceRecording $device");
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
    await _cleanupCurrentState();
    if (cleanDevice) {
      _updateRecordingDevice(null);
    }
    updateRecordingState(RecordingState.stop);
    await _socket?.stop(reason: 'stop stream device recording');
  }

  Future<void> streamSystemAudioRecording() async {
    if (!PlatformService.isDesktop) {
      notifyError('System audio recording is only available on macOS and Windows.');
      return;
    }

    // User wants to record - enable auto-resume after wake
    _shouldAutoResumeAfterWake = true;

    updateRecordingState(RecordingState.initialising);

    _systemAudioBuffer = [];
    _systemAudioCaching = true;
    Future.delayed(const Duration(seconds: 3), () {
      _systemAudioCaching = false;
      _flushSystemAudioBuffer();
    });

    bool permissionsGranted = await _checkAndRequestSystemAudioPermissions();
    if (permissionsGranted) {
      await _startSystemAudioCapture();
    } else {
      updateRecordingState(RecordingState.stop);
    }
  }

  Future<void> _startSystemAudioCapture() async {
    await changeAudioRecordProfile(audioCodec: BleAudioCodec.pcm16, sampleRate: 16000);

    await ServiceManager.instance().systemAudio.start(
          onFormatReceived: (Map<String, dynamic> format) async {
            // This callback is for information only, no action needed.
          },
          onByteReceived: _processSystemAudioByteReceived,
          onRecording: () {
            updateRecordingState(RecordingState.systemAudioRecord);
            _startRecordingTimer();
            debugPrint('System audio recording started successfully.');
          },
          onStop: () {
            if (_isPaused) {
              updateRecordingState(RecordingState.pause);
            } else {
              updateRecordingState(RecordingState.stop);
            }
            _socket?.stop(reason: 'system audio stream ended from native');
          },
          onError: (error) {
            debugPrint('System audio capture error: $error');
            AppSnackbar.showSnackbarError('An error occurred during recording: $error');
            updateRecordingState(RecordingState.stop);
          },
          onSystemWillSleep: (wasRecording) {
            debugPrint('System will sleep - was recording: $wasRecording');
          },
          onSystemDidWake: (nativeIsRecording) async {
            debugPrint('[SystemWake] Native recording: $nativeIsRecording, Flutter state: $recordingState');

            if (!nativeIsRecording && recordingState == RecordingState.systemAudioRecord) {
              // Native stopped, sync Flutter state
              updateRecordingState(RecordingState.stop);

              // Auto-resume based on session flag (was recording before sleep?)
              if (_shouldAutoResumeAfterWake) {
                debugPrint('[SystemWake] Auto-resuming recording (was recording before sleep)...');
                await Future.delayed(const Duration(seconds: 2));
                await streamSystemAudioRecording();
              } else {
                debugPrint('[SystemWake] Not auto-resuming (user manually stopped)');
              }
            }
          },
          onScreenDidLock: (wasRecording) {
            debugPrint('Screen locked - was recording: $wasRecording');
          },
          onScreenDidUnlock: () {
            debugPrint('Screen unlocked');
          },
          onDisplaySetupInvalid: (reason) {
            debugPrint('Display setup invalid: $reason');
            if (recordingState == RecordingState.systemAudioRecord) {
              updateRecordingState(RecordingState.stop);
              AppSnackbar.showSnackbarError(
                  'Recording stopped: $reason. You may need to reconnect external displays or restart recording.');
            }
          },
          onMicrophoneDeviceChanged: _onMicrophoneDeviceChanged,
          onMicrophoneStatus: _onMicrophoneStatus,
          onStoppedAutomatically: _handleRecordingStoppedAutomatically,
        );
  }

  Future<bool> _checkAndRequestSystemAudioPermissions() async {
    final micStatus = await _screenCaptureChannel.invokeMethod('checkMicrophonePermission');

    if (micStatus != 'granted') {
      if (micStatus == 'undetermined' || micStatus == 'unavailable') {
        final granted = await _screenCaptureChannel.invokeMethod('requestMicrophonePermission');
        if (!granted) {
          AppSnackbar.showSnackbarError('Microphone permission required');
          return false;
        }
      } else if (micStatus == 'denied') {
        AppSnackbar.showSnackbarError('Grant microphone permission in System Preferences');
        return false;
      }
    }

    final screenStatus = await _screenCaptureChannel.invokeMethod('checkScreenCapturePermission');

    if (screenStatus != 'granted') {
      final granted = await _screenCaptureChannel.invokeMethod('requestScreenCapturePermission');
      if (!granted) {
        AppSnackbar.showSnackbarError('Screen recording permission required');
        return false;
      }
    }
    return true;
  }

  Future<void> _onMicrophoneDeviceChanged() async {
    final nativeRecording = await _screenCaptureChannel.invokeMethod('isRecording') ?? false;
    if (!nativeRecording) return;

    _isAutoReconnecting = true;
    _reconnectCountdown = 5;
    notifyListeners();

    await pauseSystemAudioRecording(isAuto: true);

    _reconnectTimer?.cancel();
    _reconnectTimer = Timer.periodic(const Duration(seconds: 1), (timer) {
      if (_reconnectCountdown > 1) {
        _reconnectCountdown--;
        notifyListeners();
      } else {
        _reconnectTimer?.cancel();
        _reconnectTimer = null;
        if (_isAutoReconnecting) {
          resumeSystemAudioRecording().then((_) {
            _isAutoReconnecting = false;
            notifyListeners();
          });
        }
      }
    });
  }

  void _onMicrophoneStatus(String deviceName, double micLevel, double systemAudioLevel) {
    final bool needsUpdate = microphoneName != deviceName ||
        (microphoneLevel - micLevel).abs() > 0.001 ||
        (this.systemAudioLevel - systemAudioLevel).abs() > 0.001;

    if (needsUpdate) {
      microphoneName = deviceName;
      microphoneLevel = micLevel;
      this.systemAudioLevel = systemAudioLevel;
      notifyListeners();
    }
  }

  void _flushSystemAudioBuffer() {
    if (_socket?.state == SocketServiceState.connected) {
      while (_systemAudioBuffer.length >= 320) {
        final chunk = _systemAudioBuffer.sublist(0, 320);
        _socket?.send(chunk);
        _systemAudioBuffer.removeRange(0, 320);
      }
    }
  }

  Future<void> stopSystemAudioRecording() async {
    if (!PlatformService.isDesktop) return;

    // User manually stopped - don't auto-resume after wake
    _shouldAutoResumeAfterWake = false;

    _isAutoReconnecting = false;
    _reconnectTimer?.cancel();
    _reconnectTimer = null;

    ServiceManager.instance().systemAudio.stop();
    _isPaused = false;
    _stopRecordingTimer();
    await _socket?.stop(reason: 'manual stop');
    await _cleanupCurrentState();

    // Tell native to reset recording source since user explicitly stopped
    _screenCaptureChannel.invokeMethod('resetRecordingSource');
  }

  Future<void> pauseSystemAudioRecording({bool isAuto = false}) async {
    if (!PlatformService.isDesktop) return;

    if (!isAuto) {
      // User manually paused - don't auto-resume after wake
      _shouldAutoResumeAfterWake = false;
      _isAutoReconnecting = false;
      _reconnectTimer?.cancel();
      _reconnectTimer = null;
    }

    ServiceManager.instance().systemAudio.stop();
    _isPaused = true;
    // Don't reset duration - just pause the timer
    _pauseRecordingTimer();
    notifyListeners();
    _broadcastRecordingState();
  }

  Future<void> resumeSystemAudioRecording() async {
    if (!PlatformService.isDesktop) return;

    // User wants to resume - enable auto-resume after wake
    _shouldAutoResumeAfterWake = true;
    _isPaused = false;

    // Preserve the current duration before starting
    final preservedDuration = _recordingDuration;
    await streamSystemAudioRecording();
    // Restore duration after streamSystemAudioRecording may have reset it
    _recordingDuration = preservedDuration;
    _broadcastRecordingState();
  }

  Future<void> _handleFloatingControlBarMethodCall(MethodCall call) async {
    if (!PlatformService.isDesktop) return;

    switch (call.method) {
      case 'togglePauseResume':
        if (isPaused) {
          await resumeSystemAudioRecording();
        } else if (recordingState == RecordingState.systemAudioRecord) {
          await pauseSystemAudioRecording();
        } else {
          await streamSystemAudioRecording();
        }
        break;
      case 'requestCurrentState':
        // Control bar is requesting current state (e.g., when it becomes visible)
        _broadcastRecordingState();
        break;
      default:
        Logger.debug('FloatingControlBarChannel: Unhandled method ${call.method}');
    }
  }

  Future<void> _handleRecordingStoppedAutomatically() async {
    debugPrint('CaptureProvider: Recording stopped automatically (meeting ended)');
    // Don't auto-resume after this - meeting is over
    _shouldAutoResumeAfterWake = false;

    // Stop the Flutter-side recording state
    if (PlatformService.isDesktop) {
      _isAutoReconnecting = false;
      _reconnectTimer?.cancel();
      _reconnectTimer = null;
      _isPaused = false;
      _stopRecordingTimer();
      updateRecordingState(RecordingState.stop);
      await _socket?.stop(reason: 'meeting ended - auto stop');
      await _cleanupCurrentState();
    }

    await forceProcessingCurrentConversation();
  }

  Future<void> _handleRecordingStartedFromNub() async {
    debugPrint('CaptureProvider: Recording started from nub - stopping any existing recording and starting fresh');

    // Reset all recording state to ensure clean start
    _isPaused = false;
    _stopRecordingTimer();

    // Stop any existing recording and CLEAR CALLBACKS immediately
    ServiceManager.instance().systemAudio.stopAndClearCallbacks();
    await _socket?.stop(reason: 'nub start - reset');

    // Reset state to stop and broadcast immediately so control bar shows correct state
    recordingState = RecordingState.stop;
    notifyListeners();
    _broadcastRecordingState();

    // Small delay to ensure native stop completes before starting new recording
    await Future.delayed(const Duration(milliseconds: 300));

    // Start fresh recording
    await streamSystemAudioRecording();
  }

  @override
  void onClosed([int? closeCode]) {
    _transcriptionServiceStatuses = [];
    _transcriptServiceReady = false;

    if (closeCode == 4002) {
      usageProvider?.markAsOutOfCreditsAndRefresh();
    }

    notifyListeners();
    _startKeepAliveServices();
  }

  void _startKeepAliveServices() {
    _keepAliveTimer?.cancel();
    _keepAliveTimer = Timer.periodic(const Duration(seconds: 15), (t) async {
      debugPrint("[Provider] keep alive");
      // rate 1/15s
      if (_keepAliveLastExecutedAt != null &&
          DateTime.now().subtract(const Duration(seconds: 15)).isBefore(_keepAliveLastExecutedAt!)) {
        debugPrint("[Provider] keep alive - hitting rate limits 1/15s");
        return;
      }

      _keepAliveLastExecutedAt = DateTime.now();
      if (!recordingDeviceServiceReady || _socket?.state == SocketServiceState.connected) {
        t.cancel();
        return;
      }

      if (_recordingDevice != null) {
        BleAudioCodec codec = await _getAudioCodec(_recordingDevice!.id);
        await _initiateWebsocket(audioCodec: codec, source: _getConversationSourceFromDevice());
        return;
      }
      if (recordingState == RecordingState.record) {
        await _initiateWebsocket(
            audioCodec: BleAudioCodec.pcm16, sampleRate: 16000, source: ConversationSource.phone.name);
        return;
      }
      if (recordingState == RecordingState.systemAudioRecord && PlatformService.isDesktop) {
        debugPrint("System audio socket disconnected, reconnecting...");
        await _initiateWebsocket(
            audioCodec: BleAudioCodec.pcm16, sampleRate: 16000, source: ConversationSource.desktop.name);
        return;
      }
    });
  }

  @override
  void onError(Object err) {
    _transcriptionServiceStatuses = [];
    _transcriptServiceReady = false;

    if (err.toString().contains('Failed to find any displays or windows to capture')) {
      if (recordingState == RecordingState.systemAudioRecord) {
        AppSnackbar.showSnackbarError('Display detection failed. Recording stopped.');
        updateRecordingState(RecordingState.stop);
      }
    }

    notifyListeners();
    _startKeepAliveServices();
  }

  @override
  void onConnected() {
    _transcriptServiceReady = true;
    notifyListeners();
  }

  Future refreshInProgressConversations() async {
    _loadInProgressConversation();
  }

  Future _loadInProgressConversation() async {
    var convos = await getConversations(statuses: [ConversationStatus.in_progress], limit: 1);
    _conversation = convos.isNotEmpty ? convos.first : null;
    if (_conversation != null) {
      segments = _conversation!.transcriptSegments;
      photos = _conversation!.photos;
    } else {
      segments = [];
      photos = [];
    }
    setHasTranscripts(segments.isNotEmpty);
    notifyListeners();
  }

  @override
  void onMessageEventReceived(MessageEvent event) {
    if (event is ConversationProcessingStartedEvent) {
      conversationProvider!.addProcessingConversation(event.memory);
      _resetStateVariables();
      return;
    }

    if (event is ConversationEvent) {
      event.memory.isNew = true;
      conversationProvider!.removeProcessingConversation(event.memory.id);
      _processConversationCreated(event.memory, event.messages.cast<ServerMessage>());
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

    if (event is MessageServiceStatusEvent) {
      // Handle freemium threshold event via status field
      if (event.status == 'freemium_threshold_reached') {
        // Parse as FreemiumThresholdReachedEvent for consistent handling
        final thresholdEvent = FreemiumThresholdReachedEvent.fromJson({
          'status_text': event.statusText,
        });
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
        notifyListeners();
      }
      return;
    }
  }

  Future<void> forceProcessingCurrentConversation() async {
    _resetStateVariables();
    conversationProvider!.addProcessingConversation(
      ServerConversation(
          id: '0', createdAt: DateTime.now(), structured: Structured('', ''), status: ConversationStatus.processing),
    );
    processInProgressConversation().then((result) {
      if (result == null || result.conversation == null) {
        conversationProvider!.removeProcessingConversation('0');
        return;
      }
      conversationProvider!.removeProcessingConversation('0');
      result.conversation!.isNew = true;
      _processConversationCreated(result.conversation, result.messages);
    });

    return;
  }

  Future<void> _processConversationCreated(ServerConversation? conversation, List<ServerMessage> messages) async {
    if (conversation == null) return;

    // Star the conversation if it was marked for starring
    if (_starOngoingConversation) {
      debugPrint("Conversation was marked for starring, applying star");
      _starOngoingConversation = false; // Reset the flag
      conversation.starred = true;
      // Call API to star the conversation
      await setConversationStarred(conversation.id, true);
    }

    conversationProvider?.upsertConversation(conversation);
    MixpanelManager().conversationCreated(conversation);
  }

  Future<void> _handleLastConvoEvent(String memoryId) async {
    bool conversationExists =
        conversationProvider?.conversations.any((conversation) => conversation.id == memoryId) ?? false;
    if (conversationExists) {
      return;
    }
    ServerConversation? conversation = await getConversationById(memoryId);
    if (conversation != null) {
      debugPrint("Adding last conversation to conversations: $memoryId");
      conversationProvider?.upsertConversation(conversation);
    } else {
      debugPrint("Failed to fetch last conversation: $memoryId");
    }
  }

  void _handleTranslationEvent(List<TranscriptSegment> translatedSegments) {
    try {
      if (translatedSegments.isEmpty) return;

      debugPrint("Received ${translatedSegments.length} translated segments");

      // Update the segments with the translated ones
      var remainSegments = TranscriptSegment.updateSegments(segments, translatedSegments);
      if (remainSegments.isNotEmpty) {
        debugPrint("Adding ${remainSegments.length} new translated segments");
      }

      notifyListeners();
    } catch (e) {
      debugPrint("Error handling translation event: $e");
    }
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

    // Auto-accept if enabled for new person suggestions
    if (SharedPreferencesUtil().autoCreateSpeakersEnabled) {
      assignSpeakerToConversation(event.speakerId, event.personId, event.personName, [event.segmentId]);
    } else {
      // Otherwise, store suggestion to be displayed.
      suggestionsBySegmentId[event.segmentId] = event;
      notifyListeners();
    }
  }

  Future<void> assignSpeakerToConversation(
      int speakerId, String personId, String personName, List<String> segmentIds) async {
    if (segmentIds.isEmpty) return;

    taggingSegmentIds = List.from(segmentIds);
    notifyListeners();

    try {
      String finalPersonId = personId;

      // Create person if new
      if (finalPersonId.isEmpty) {
        Person? newPerson = await peopleProvider?.createPersonProvider(personName);
        if (newPerson != null) {
          finalPersonId = newPerson.id;
        }
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
    _processNewSegmentReceived(newSegments);
  }

  void _processNewSegmentReceived(List<TranscriptSegment> newSegments) async {
    if (newSegments.isEmpty) return;

    if (segments.isEmpty && !_isLoadingInProgressConversation) {
      _isLoadingInProgressConversation = true;
      if (!PlatformService.isDesktop) {
        FlutterForegroundTask.sendDataToTask(jsonEncode({'location': true}));
      }
      try {
        await _loadInProgressConversation();
      } finally {
        _isLoadingInProgressConversation = false;
      }
    }

    final remainSegments = TranscriptSegment.updateSegments(segments, newSegments);
    segments.addAll(remainSegments);
    hasTranscripts = true;
    notifyListeners();
  }

  void onConnectionStateChanged(bool isConnected) {
    _isConnected = isConnected;
    notifyListeners();
  }

  // ============== Freemium: Threshold Notification ==============

  /// Handle freemium threshold reached: Notify user based on required action
  void _handleFreemiumThresholdReached(FreemiumThresholdReachedEvent event) {
    if (_freemiumThresholdReached) return;

    _freemiumThresholdReached = true;
    _freemiumRemainingSeconds = event.remainingSeconds;
    _freemiumRequiresUserAction = event.requiresUserAction;

    debugPrint('[Freemium] Threshold reached - ${event.remainingSeconds} seconds remaining');
    debugPrint('[Freemium] Action required: ${event.action.name}, requires user action: ${event.requiresUserAction}');

    if (event.requiresUserAction) {
      debugPrint('[Freemium] User should setup on-device transcription in Settings > Transcription');
    } else {
      debugPrint('[Freemium] No user action required - backend will handle fallback');
    }

    // Update usage provider to reflect approaching limit
    usageProvider?.refreshSubscription();

    notifyListeners();
  }

  /// Callback for external components to reset their freemium session state
  VoidCallback? onFreemiumSessionReset;

  /// Reset freemium threshold state (e.g., when credits reset or on new session)
  void resetFreemiumThresholdState() {
    _freemiumThresholdReached = false;
    _freemiumRemainingSeconds = 0;
    _freemiumRequiresUserAction = false;
    // Notify external handlers (e.g., FreemiumSwitchHandler)
    onFreemiumSessionReset?.call();
    notifyListeners();
  }

  /// Check if credits were restored and reset threshold state
  Future<void> checkCreditsAndResetThresholdIfNeeded() async {
    await usageProvider?.fetchSubscription();
    if (usageProvider?.isOutOfCredits == false && _freemiumThresholdReached) {
      debugPrint('[Freemium] Credits restored! Resetting threshold state.');
      resetFreemiumThresholdState();
    }
  }

  void setIsWalSupported(bool value) {
    _isWalSupported = value;
    notifyListeners();
  }

  void _processSystemAudioByteReceived(Uint8List bytes) {
    _systemAudioBuffer.addAll(bytes);
    if (!_systemAudioCaching) {
      _flushSystemAudioBuffer();
    }
  }

  void _broadcastRecordingState() {
    if (!PlatformService.isDesktop) return;

    final stateData = {
      'isRecording':
          recordingState == RecordingState.systemAudioRecord || recordingState == RecordingState.deviceRecord,
      'isPaused': _isPaused,
      'duration': _getRecordingDuration(),
      'isInitialising': recordingState == RecordingState.initialising,
    };

    _controlBarChannel.invokeMethod('updateRecordingState', stateData);
  }

  void _startRecordingTimer() {
    _recordingDuration = 0;
    _recordingTimer?.cancel();
    _recordingTimer = Timer.periodic(const Duration(seconds: 1), (timer) {
      if (recordingState == RecordingState.systemAudioRecord || recordingState == RecordingState.deviceRecord) {
        _recordingDuration++;
        _broadcastRecordingState();
      }
    });
  }

  void _pauseRecordingTimer() {
    // Stop the timer but preserve the current duration
    _recordingTimer?.cancel();
    _recordingTimer = null;
    // Don't reset _recordingDuration here
  }

  void _stopRecordingTimer() {
    _recordingTimer?.cancel();
    _recordingTimer = null;
    _recordingDuration = 0;
  }

  Future<void> pauseDeviceRecording() async {
    if (_recordingDevice == null) return;

    // Pause the BLE stream but keep the device connection
    await _bleBytesStream?.cancel();
    _isPaused = true;
    updateRecordingState(RecordingState.pause);
    notifyListeners();
  }

  Future<void> resumeDeviceRecording() async {
    if (_recordingDevice == null) return;
    _isPaused = false;
    // Resume streaming from the device
    await _initiateDeviceAudioStreaming();

    final deviceId = _recordingDevice!.id;
    BleAudioCodec codec = await _getAudioCodec(deviceId);
    await _wal.getSyncs().phone.onAudioCodecChanged(codec);

    await streamAudioToWs(deviceId, codec);

    updateRecordingState(RecordingState.deviceRecord);
    notifyListeners();
  }
}
