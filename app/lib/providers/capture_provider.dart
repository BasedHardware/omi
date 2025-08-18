import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math' as math;

import 'package:collection/collection.dart';
import 'package:path/path.dart' as path;
import 'package:path_provider/path_provider.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:flutter_provider_utilities/flutter_provider_utilities.dart';
import 'package:internet_connection_checker_plus/internet_connection_checker_plus.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/backend/schema/message_event.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/services/devices.dart';
import 'package:omi/services/notifications.dart';
import 'package:omi/services/services.dart';
import 'package:omi/services/sockets/pure_socket.dart';
import 'package:omi/services/sockets/sdcard_socket.dart';
import 'package:omi/services/sockets/transcription_connection.dart';
import 'package:omi/services/wals.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/enums.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/platform/platform_service.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:omi/utils/debug_log_manager.dart';

class CaptureProvider extends ChangeNotifier
    with MessageNotifierMixin, WidgetsBindingObserver
    implements ITransctipSegmentSocketServiceListener {
  ConversationProvider? conversationProvider;
  MessageProvider? messageProvider;
  PeopleProvider? peopleProvider;
  UsageProvider? usageProvider;

  TranscriptSegmentSocketService? _socket;
  SdCardSocketService sdCardSocket = SdCardSocketService();
  Timer? _keepAliveTimer;

  // Method channel for system audio permissions
  static const MethodChannel _screenCaptureChannel = MethodChannel('screenCapturePlatform');

  IWalService get _wal => ServiceManager.instance().wal;

  IDeviceService get _deviceService => ServiceManager.instance().device;
  bool _isWalSupported = false;

  bool get isWalSupported => _isWalSupported;

  StreamSubscription<InternetStatus>? _internetStatusListener;
  InternetStatus? _internetStatus;

  get internetStatus => _internetStatus;

  String? microphoneName;
  double microphoneLevel = 0.0;
  double systemAudioLevel = 0.0;

  bool _isAutoReconnecting = false;
  bool get isAutoReconnecting => _isAutoReconnecting;

  DateTime? _lastUsageLimitDialogShown;
  bool get outOfCredits => usageProvider?.isOutOfCredits ?? false;

  Timer? _reconnectTimer;
  int _reconnectCountdown = 5;
  int get reconnectCountdown => _reconnectCountdown;

  List<MessageEvent> _transcriptionServiceStatuses = [];
  List<MessageEvent> get transcriptionServiceStatuses => _transcriptionServiceStatuses;

  List<int> _systemAudioBuffer = [];
  bool _systemAudioCaching = true;

  CaptureProvider() {
    _internetStatusListener = PureCore().internetConnection.onStatusChange.listen((InternetStatus status) {
      onInternetSatusChanged(status);
    });

    // Add app lifecycle listener to detect sleep/wake cycles
    if (PlatformService.isDesktop) {
      _initializeAppLifecycleListener();
    }
  }

  void _initializeAppLifecycleListener() {
    // Add this instance as a lifecycle observer
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    super.didChangeAppLifecycleState(state);
    if (state == AppLifecycleState.resumed) {
      _handleAppResumed();
    }
  }

  void _handleAppResumed() async {
    if (recordingState == RecordingState.systemAudioRecord) {
      try {
        // Check if native recording is still active
        bool nativeRecording = await _screenCaptureChannel.invokeMethod('isRecording') ?? false;

        if (nativeRecording && recordingState != RecordingState.systemAudioRecord) {
          // Will be handled by existing logic in streamSystemAudioRecording error handling
        } else if (!nativeRecording && recordingState == RecordingState.systemAudioRecord) {
          updateRecordingState(RecordingState.stop);
          await _socket?.stop(reason: 'native recording stopped during sleep');
          await DebugLogManager.logEvent('transcription_socket_stop_due_to_sleep', {});
        }
      } catch (e) {
        debugPrint('Could not check state during app resume: $e');
      }
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

  StreamSubscription? _storageStream;

  get storageStream => _storageStream;

  RecordingState recordingState = RecordingState.stop;

  bool _isPaused = false;
  bool get isPaused => _isPaused;

  bool _transcriptServiceReady = false;

  // Audio level tracking for waveform visualization
  final List<double> _audioLevels = List.generate(8, (_) => 0.15);
  List<double> get audioLevels => List.from(_audioLevels);

  void _processAudioBytesForVisualization(List<int> bytes) {
    if (bytes.isEmpty) return;

    double rms = 0;

    // Process bytes as 16-bit samples (2 bytes per sample)
    for (int i = 0; i < bytes.length - 1; i += 2) {
      // Convert two bytes to a 16-bit signed integer
      int sample = bytes[i] | (bytes[i + 1] << 8);

      // Convert to signed value (if high bit is set)
      if (sample > 32767) {
        sample = sample - 65536;
      }

      // Square the sample and add to sum
      rms += sample * sample;
    }

    // Calculate RMS and normalize to 0.0-1.0 range
    int sampleCount = bytes.length ~/ 2;
    if (sampleCount > 0) {
      rms = math.sqrt(rms / sampleCount) / 32768.0;
    } else {
      rms = 0;
    }

    // Apply non-linear scaling for better dynamic range - quieter on silence, same on noise
    final level = (math.pow(rms, 0.3).toDouble() * 2.1).clamp(0.15, 1.6);

    // Shift all values left and add new level
    for (int i = 0; i < _audioLevels.length - 1; i++) {
      _audioLevels[i] = _audioLevels[i + 1];
    }
    _audioLevels[_audioLevels.length - 1] = level;

    notifyListeners(); // Notify UI to update waveform
  }

  bool get transcriptServiceReady => _transcriptServiceReady && _internetStatus == InternetStatus.connected;

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

  Future<void> changeAudioRecordProfile({
    required BleAudioCodec audioCodec,
    int? sampleRate,
    int? channels,
    bool? isPcm,
  }) async {
    print("changeAudioRecordProfile");
    await _resetState();
    await _initiateWebsocket(audioCodec: audioCodec, sampleRate: sampleRate, channels: channels, isPcm: isPcm);
  }

  Future<void> _initiateWebsocket({
    required BleAudioCodec audioCodec,
    int? sampleRate,
    int? channels,
    bool? isPcm,
    bool force = false,
  }) async {
    Logger.debug('initiateWebsocket in capture_provider');

    BleAudioCodec codec = audioCodec;
    sampleRate ??= mapCodecToSampleRate(codec);
    channels ??= (codec == BleAudioCodec.pcm16 || codec == BleAudioCodec.pcm8) ? 1 : 2;

    Logger.debug('is ws null: ${_socket == null}');
    Logger.debug('Initiating WebSocket with: codec=$codec, sampleRate=$sampleRate, channels=$channels, isPcm=$isPcm');

    // Connect to the transcript socket
    String language =
        SharedPreferencesUtil().hasSetPrimaryLanguage ? SharedPreferencesUtil().userPrimaryLanguage : "multi";

    _socket = await ServiceManager.instance()
        .socket
        .conversation(codec: codec, sampleRate: sampleRate, language: language, force: force);
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

      // start long press
      if (buttonState == 3 && _voiceCommandSession == null) {
        _voiceCommandSession = DateTime.now();
        _commandBytes = [];
        _watchVoiceCommands(deviceId, _voiceCommandSession!);
        _playSpeakerHaptic(deviceId, 1);
      }

      // release
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
    _bleBytesStream = await _getBleAudioBytesListener(deviceId, onAudioBytesReceived: (List<int> value) {
      final snapshot = List<int>.from(value);
      if (snapshot.isEmpty || snapshot.length < 3) return;

      // Command button triggered
      if (_voiceCommandSession != null) {
        _commandBytes.add(snapshot.sublist(3));
      }

      // Support: opus codec, 1m from the first device connects
      var deviceFirstConnectedAt = _deviceService.getFirstConnectedAt();
      var checkWalSupported = codec.isOpusSupported() &&
          (deviceFirstConnectedAt != null &&
              deviceFirstConnectedAt.isBefore(DateTime.now().subtract(const Duration(seconds: 15)))) &&
          SharedPreferencesUtil().localSyncEnabled;
      if (checkWalSupported != _isWalSupported) {
        setIsWalSupported(checkWalSupported);
      }
      if (_isWalSupported) {
        _wal.getSyncs().phone.onByteStream(snapshot);
      }

      // send ws
      if (_socket?.state == SocketServiceState.connected) {
        final trimmedValue = value.sublist(3);
        _socket?.send(trimmedValue);

        // Process audio bytes for waveform visualization
        _processAudioBytesForVisualization(trimmedValue);

        // synced
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

    await initiateStorageBytesStreaming();
    notifyListeners();
  }

  Future _cleanupCurrentState() async {
    await _closeBleStream();
    notifyListeners();
  }

  // TODO: use connection directly
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

  Future<StreamSubscription?> _getBleStorageBytesListener(
    String deviceId, {
    required void Function(List<int>) onStorageBytesReceived,
  }) async {
    var connection = await ServiceManager.instance().device.ensureConnection(deviceId);
    if (connection == null) {
      return Future.value(null);
    }
    return connection.getBleStorageBytesListener(onStorageBytesReceived: onStorageBytesReceived);
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
    if (language != _socket?.language || codec != _socket?.codec || _socket?.state != SocketServiceState.connected) {
      await _initiateWebsocket(audioCodec: codec, force: true);
    }
  }

  Future<void> _initiateDeviceAudioStreaming() async {
    if (_recordingDevice == null) {
      return;
    }
    final deviceId = _recordingDevice!.id;
    BleAudioCodec codec = await _getAudioCodec(deviceId);
    await _wal.getSyncs().phone.onAudioCodecChanged(codec);
    await streamButton(deviceId);
    await streamAudioToWs(deviceId, codec);

    // Set recording state to deviceRecord when device streaming starts
    updateRecordingState(RecordingState.deviceRecord);
    notifyListeners();
  }

  Future<void> _initiateDevicePhotoStreaming() async {
    if (_recordingDevice == null) return;
    final deviceId = _recordingDevice!.id;
    var connection = await ServiceManager.instance().device.ensureConnection(deviceId);
    if (connection == null) return;

    await connection.performCameraStartPhotoController();
    _blePhotoStream = await connection.performGetImageListener(onImageReceived: (photoBytes) async {
      final String tempId = 'temp_img_${DateTime.now().millisecondsSinceEpoch}';
      final String base64Image = base64Encode(photoBytes);

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

  Future _closeBleStream() async {
    await _bleBytesStream?.cancel();
    await _blePhotoStream?.cancel();
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
    _internetStatusListener?.cancel();

    // Remove lifecycle observer
    if (PlatformService.isDesktop) {
      WidgetsBinding.instance.removeObserver(this);
    }

    super.dispose();
  }

  void updateRecordingState(RecordingState state) {
    recordingState = state;
    notifyListeners();
  }

  streamRecording() async {
    updateRecordingState(RecordingState.initialising);
    await Permission.microphone.request();

    // prepare
    await changeAudioRecordProfile(audioCodec: BleAudioCodec.pcm16, sampleRate: 16000);

    // record
    await ServiceManager.instance().mic.start(onByteReceived: (bytes) {
      if (_socket?.state == SocketServiceState.connected) {
        _socket?.send(bytes);
      }
      // Process audio bytes for waveform visualization
      _processAudioBytesForVisualization(bytes);
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
    await _resetStateVariables();
    await _resetState();
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
            debugPrint('System woke up - Native recording: $nativeIsRecording, Flutter state: $recordingState');
            if (!nativeIsRecording && recordingState == RecordingState.systemAudioRecord) {
              updateRecordingState(RecordingState.stop);
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
        );
  }

  Future<bool> _checkAndRequestSystemAudioPermissions() async {
    // Check microphone permission first
    String micStatus = await _screenCaptureChannel.invokeMethod('checkMicrophonePermission');
    debugPrint('Microphone permission status: $micStatus');

    if (micStatus != 'granted') {
      if (micStatus == 'undetermined' || micStatus == 'unavailable') {
        bool micGranted = await _screenCaptureChannel.invokeMethod('requestMicrophonePermission');
        if (!micGranted) {
          AppSnackbar.showSnackbarError('Microphone permission is required for system audio recording.');
          return false;
        }
      } else if (micStatus == 'denied') {
        AppSnackbar.showSnackbarError(
            'Microphone permission denied. Please grant permission in System Preferences > Privacy & Security > Microphone.');
        return false;
      }
    }

    // Check screen capture permission
    String screenStatus = await _screenCaptureChannel.invokeMethod('checkScreenCapturePermission');
    debugPrint('Screen capture permission status: $screenStatus');

    if (screenStatus != 'granted') {
      bool screenGranted = await _screenCaptureChannel.invokeMethod('requestScreenCapturePermission');
      if (!screenGranted) {
        AppSnackbar.showSnackbarError(
            'Screen recording permission is required. Please grant permission in System Preferences > Privacy & Security > Screen Recording.');
        return false;
      }
    }
    return true;
  }

  Future<void> _onMicrophoneDeviceChanged() async {
    debugPrint('Microphone device changed. Restarting recording in 5 seconds...');
    bool nativeRecording = await _screenCaptureChannel.invokeMethod('isRecording') ?? false;
    if (nativeRecording) {
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
    _isAutoReconnecting = false;
    _reconnectTimer?.cancel();
    _reconnectTimer = null;
    ServiceManager.instance().systemAudio.stop();
    _isPaused = false; // Clear paused state when stopping
    await _socket?.stop(reason: 'stop system audio recording from Flutter');
    await _cleanupCurrentState();
  }

  Future<void> pauseSystemAudioRecording({bool isAuto = false}) async {
    if (!PlatformService.isDesktop) return;
    if (!isAuto) {
      _isAutoReconnecting = false;
      _reconnectTimer?.cancel();
      _reconnectTimer = null;
    }
    ServiceManager.instance().systemAudio.stop();
    _isPaused = true; // Set paused state
    notifyListeners();
  }

  Future<void> resumeSystemAudioRecording() async {
    if (!PlatformService.isDesktop) return;
    _isPaused = false; // Clear paused state
    await streamSystemAudioRecording(); // Re-trigger the recording flow
  }

  @override
  void onClosed([int? closeCode]) {
    _transcriptionServiceStatuses = [];
    _transcriptServiceReady = false;
    debugPrint('[Provider] Socket is closed with code: $closeCode');

    if (closeCode == 4002) {
      // Refresh subscription to get latest usage data which will reflect the out of credits status.
      usageProvider?.markAsOutOfCreditsAndRefresh();
    }

    notifyListeners();
    _startKeepAliveServices();
  }

  void _startKeepAliveServices() {
    _keepAliveTimer?.cancel();
    _keepAliveTimer = Timer.periodic(const Duration(seconds: 15), (t) async {
      debugPrint("[Provider] keep alive...");
      if (!recordingDeviceServiceReady || _socket?.state == SocketServiceState.connected) {
        t.cancel();
        return;
      }
      if (_recordingDevice != null) {
        BleAudioCodec codec = await _getAudioCodec(_recordingDevice!.id);
        await _initiateWebsocket(audioCodec: codec);
        return;
      }
      if (recordingState == RecordingState.record) {
        await _initiateWebsocket(audioCodec: BleAudioCodec.pcm16, sampleRate: 16000);
        return;
      }
      if (recordingState == RecordingState.systemAudioRecord && PlatformService.isDesktop) {
        debugPrint("System audio socket disconnected, reconnecting...");
        await _initiateWebsocket(audioCodec: BleAudioCodec.pcm16, sampleRate: 16000);
        return;
      }
    });
  }

  @override
  void onError(Object err) {
    _transcriptionServiceStatuses = [];
    _transcriptServiceReady = false;
    debugPrint('Socket error: $err');

    // Check for display-related errors
    if (err.toString().contains('Failed to find any displays or windows to capture')) {
      debugPrint('Display detection error in socket - likely external display disconnect');
      if (recordingState == RecordingState.systemAudioRecord) {
        AppSnackbar.showSnackbarError(
            'Display detection failed during recording. This often happens when external displays are disconnected. Recording will stop.');
        updateRecordingState(RecordingState.stop);
      }
    }

    notifyListeners();
    _startKeepAliveServices();
  }

  @override
  void onConnected() {
    _transcriptServiceReady = true;
    debugPrint('Socket connected');
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
      _transcriptionServiceStatuses.add(event);
      _transcriptionServiceStatuses = List.from(_transcriptionServiceStatuses);
      notifyListeners();
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

      // Update local state for all segments with this speakerId
      for (var segment in segments) {
        if (segmentIds.contains(segment.id)) {
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

    if (segments.isEmpty) {
      debugPrint('newSegments: ${newSegments.last}');
      if (!PlatformService.isDesktop) {
        FlutterForegroundTask.sendDataToTask(jsonEncode({'location': true}));
      }
      await _loadInProgressConversation();
    }
    var remainSegments = TranscriptSegment.updateSegments(segments, newSegments);
    segments.addAll(remainSegments);

    hasTranscripts = true;
    notifyListeners();
  }

  void onInternetSatusChanged(InternetStatus status) {
    debugPrint("[SocketService] Internet connection changed $status");
    _internetStatus = status;
    notifyListeners();
  }

  void setIsWalSupported(bool value) {
    _isWalSupported = value;
    notifyListeners();
  }

  /*
  *
  *
  *
  *
  *
  * */

  List<int> currentStorageFiles = <int>[];
  List<String> currentStorageFileNames = <String>[];
  int sdCardFileNum = 1;
  
  // Individual file download tracking
  Map<String, bool> _downloadingFiles = <String, bool>{};
  Map<String, double> _downloadProgress = <String, double>{};
  List<String> _downloadedChunkFiles = <String>[];

// To show the progress of the download in the UI
  int currentTotalBytesReceived = 0;
  double currentSdCardSecondsReceived = 0.0;
//--------------------------------------------

  int totalStorageFileBytes = 0; // how much in storage
  int totalBytesReceived = 0; // how much already received
  double sdCardSecondsTotal = 0.0; // time to send the next chunk
  double sdCardSecondsReceived = 0.0;
  bool sdCardDownloadDone = false;
  bool sdCardReady = false;
  bool sdCardIsDownloading = false;
  String btConnectedTime = "";
  Timer? sdCardReconnectionTimer;

  void setSdCardIsDownloading(bool value) {
    sdCardIsDownloading = value;
    notifyListeners();
  }

  Future<void> updateStorageList() async {
    if (_recordingDevice == null) {
      debugPrint('No recording device available for storage list update');
      return;
    }
    
    // Check if device is connected before trying to read storage
    var connection = await ServiceManager.instance().device.ensureConnection(_recordingDevice!.id);
    if (connection == null || !await connection.isConnected()) {
      debugPrint('Device not connected - skipping storage list update');
      // Clear previous data when device is not connected
      currentStorageFiles = <int>[];
      currentStorageFileNames = <String>[];
      notifyListeners();
      return;
    }
    
    try {
      currentStorageFiles = await _getStorageList(_recordingDevice!.id);
      currentStorageFileNames = await _getStorageFileNames(_recordingDevice!.id);
      
      if (currentStorageFiles.isEmpty) {
        debugPrint('No storage files found');
        SharedPreferencesUtil().deviceIsV2 = false;
        debugPrint('Device is not V2');
        return;
      }
      totalStorageFileBytes = currentStorageFiles[0];
      var storageOffset = currentStorageFiles.length < 2 ? 0 : currentStorageFiles[1];
      totalBytesReceived = storageOffset;
      notifyListeners();
    } catch (e) {
      debugPrint('Error updating storage list: $e');
      // Clear data on error
      currentStorageFiles = <int>[];
      currentStorageFileNames = <String>[];
      notifyListeners();
    }
  }

  Future<void> initiateStorageBytesStreaming() async {
    debugPrint('initiateStorageBytesStreaming');
    if (_recordingDevice == null) return;
    String deviceId = _recordingDevice!.id;
    var storageFiles = await _getStorageList(deviceId);
    if (storageFiles.isEmpty) {
      return;
    }
    var totalBytes = storageFiles[0];
    if (totalBytes <= 0) {
      return;
    }
    var storageOffset = storageFiles.length < 2 ? 0 : storageFiles[1];
    if (storageOffset > totalBytes) {
      // bad state?
      debugPrint("SDCard bad state, offset > total");
      storageOffset = 0;
    }

    // 80: frame length, 100: frame per seconds
    BleAudioCodec codec = await _getAudioCodec(deviceId);
    sdCardSecondsTotal = totalBytes / codec.getFramesLengthInBytes() / codec.getFramesPerSecond();
    sdCardSecondsReceived = storageOffset / codec.getFramesLengthInBytes() / codec.getFramesPerSecond();

    // > 10s
    if (totalBytes - storageOffset > 10 * codec.getFramesLengthInBytes() * codec.getFramesPerSecond()) {
      sdCardReady = true;
    }

    notifyListeners();
  }

  Future _getFileFromDevice(int fileNum, int offset) async {
    sdCardFileNum = fileNum;
    int command = 0;
    _writeToStorage(_recordingDevice!.id, sdCardFileNum, command, offset);
  }

  Future _clearFileFromDevice(int fileNum) async {
    sdCardFileNum = fileNum;
    int command = 1;
    _writeToStorage(_recordingDevice!.id, sdCardFileNum, command, 0);
  }

  Future _pauseFileFromDevice(int fileNum) async {
    sdCardFileNum = fileNum;
    int command = 3;
    _writeToStorage(_recordingDevice!.id, sdCardFileNum, command, 0);
  }

  void _notifySdCardComplete() {
    NotificationService.instance.clearNotification(8);
    NotificationService.instance.createNotification(
      notificationId: 8,
      title: 'Sd Card Processing Complete',
      body: 'Your Sd Card data is now processed! Enter the app to see.',
    );
  }

  Future<bool> _writeToStorage(String deviceId, int numFile, int command, int offset) async {
    var connection = await ServiceManager.instance().device.ensureConnection(deviceId);
    if (connection == null) {
      return Future.value(false);
    }
    return connection.writeToStorage(numFile, command, offset);
  }

  Future<List<int>> _getStorageList(String deviceId) async {
    var connection = await ServiceManager.instance().device.ensureConnection(deviceId);
    if (connection == null) {
      return [];
    }
    return connection.getStorageList();
  }

  Future<List<String>> _getStorageFileNames(String deviceId) async {
    var connection = await ServiceManager.instance().device.ensureConnection(deviceId);
    if (connection == null) {
      return [];
    }
    return connection.getStorageFileNames();
  }
  
  // Individual file download functions
  bool isDownloadingFile(String fileName) {
    return _downloadingFiles[fileName] ?? false;
  }
  
  double getDownloadProgress(String fileName) {
    return _downloadProgress[fileName] ?? 0.0;
  }
  
  List<String> get downloadedChunkFiles => List.unmodifiable(_downloadedChunkFiles);
  
  Future<bool> deleteFileFromDevice(String fileName) async {
    if (_recordingDevice == null) {
      debugPrint('No recording device available for file deletion');
      return false;
    }
    
    debugPrint('Deleting file from device: $fileName');
    
    try {
      // Find the file index in our current file list (1-based indexing for firmware)
      int fileIndex = currentStorageFileNames.indexOf(fileName);
      if (fileIndex == -1) {
        debugPrint('File $fileName not found in current file list');
        throw Exception('File not found in device file list');
      }
      
      // Firmware uses 1-based indexing
      int firmwareFileNum = fileIndex + 1;
      
      var connection = await ServiceManager.instance().device.ensureConnection(_recordingDevice!.id);
      if (connection == null) {
        throw Exception('Device connection failed');
      }
      
      debugPrint('Deleting file at index $fileIndex ($firmwareFileNum for firmware): $fileName');
      
      // Send delete command (command 1 = DELETE_COMMAND, 1-based file number)
      bool deleteSuccess = await connection.writeToStorage(firmwareFileNum, 1, 0);
      if (!deleteSuccess) {
        throw Exception('Failed to send delete command');
      }
      
      // Wait a bit for the deletion to complete
      await Future.delayed(const Duration(milliseconds: 1000));
      
      // Refresh the file list to reflect the deletion
      await updateStorageList();
      
      debugPrint('Successfully deleted $fileName from device');
      
      // Show success notification
      if (!PlatformService.isDesktop) {
        NotificationService.instance.createNotification(
          notificationId: 11,
          title: 'File Deleted',
          body: 'Successfully deleted $fileName from device SD card',
        );
      }
      
      return true;
      
    } catch (e) {
      debugPrint('Error deleting file $fileName: $e');
      
      // Show error notification
      if (!PlatformService.isDesktop) {
        NotificationService.instance.createNotification(
          notificationId: 12,
          title: 'Delete Failed',
          body: 'Failed to delete $fileName: ${e.toString()}',
        );
      }
      
      return false;
    }
  }
  
  Future<void> loadDownloadedFiles() async {
    try {
      final directory = await getApplicationDocumentsDirectory();
      final downloadsDir = Directory('${directory.path}/downloaded_chunks');
      
      if (await downloadsDir.exists()) {
        final files = await downloadsDir.list().toList();
        _downloadedChunkFiles = files
            .where((file) => file is File && file.path.endsWith('.b'))
            .map((file) => path.basename(file.path))
            .toList();
        
        debugPrint('Loaded ${_downloadedChunkFiles.length} downloaded chunk files');
        notifyListeners();
      }
    } catch (e) {
      debugPrint('Error loading downloaded files: $e');
    }
  }
  
  Future<void> deleteDownloadedFile(String fileName) async {
    try {
      final directory = await getApplicationDocumentsDirectory();
      final file = File('${directory.path}/downloaded_chunks/$fileName');
      
      if (await file.exists()) {
        await file.delete();
        _downloadedChunkFiles.remove(fileName);
        notifyListeners();
        debugPrint('Deleted downloaded file: $fileName');
      }
    } catch (e) {
      debugPrint('Error deleting file $fileName: $e');
    }
  }
  
  Future<void> downloadChunkFile(String fileName, {bool deleteAfterDownload = false}) async {
    if (_recordingDevice == null) {
      debugPrint('No recording device available for file download');
      return;
    }
    
    if (isDownloadingFile(fileName)) {
      debugPrint('File $fileName is already being downloaded');
      return;
    }
    
    debugPrint('Starting download for chunk file: $fileName');
    _downloadingFiles[fileName] = true;
    _downloadProgress[fileName] = 0.0;
    notifyListeners();
    
    try {
      // Find the file index in our current file list (1-based indexing for firmware)
      int fileIndex = currentStorageFileNames.indexOf(fileName);
      if (fileIndex == -1) {
        debugPrint('File $fileName not found in current file list');
        throw Exception('File not found in device file list');
      }
      
      // Firmware uses 1-based indexing
      int firmwareFileNum = fileIndex + 1;
      
      // Use the existing storage download mechanism
      var connection = await ServiceManager.instance().device.ensureConnection(_recordingDevice!.id);
      if (connection == null) {
        throw Exception('Device connection failed');
      }
      
      debugPrint('Downloading file at index $fileIndex ($firmwareFileNum for firmware): $fileName');
      
      // Set up progress tracking
      StreamSubscription? downloadSubscription;
      List<int> downloadedData = [];
      
      // Listen for storage bytes
      downloadSubscription = await connection.getBleStorageBytesListener(
        onStorageBytesReceived: (List<int> bytes) {
          downloadedData.addAll(bytes);
          
          // Update progress (estimate based on received bytes)
          // For now, we'll use a simple progress indication
          double progress = downloadedData.length / (1024 * 10); // Assume ~10KB average file
          if (progress > 1.0) progress = 1.0;
          
          _downloadProgress[fileName] = progress;
          notifyListeners();
          
          debugPrint('Downloaded ${downloadedData.length} bytes for $fileName (${(progress * 100).toStringAsFixed(1)}%)');
        },
      );
      
      if (downloadSubscription == null) {
        throw Exception('Failed to start download stream');
      }
      
      // Start the download by writing to storage (command 0 = download, 1-based file number)
      bool writeSuccess = await connection.writeToStorage(firmwareFileNum, 0, 0);
      if (!writeSuccess) {
        throw Exception('Failed to initiate file download');
      }
      
      debugPrint('Download command sent for $fileName, waiting for data...');
      
      // Wait for download completion (timeout after 30 seconds)
      int waitTime = 0;
      const int maxWaitTime = 30000; // 30 seconds
      const int checkInterval = 500; // 500ms
      
      while (downloadedData.isEmpty && waitTime < maxWaitTime) {
        await Future.delayed(const Duration(milliseconds: checkInterval));
        waitTime += checkInterval;
        
        // Update progress indicator during wait
        double waitProgress = waitTime / maxWaitTime * 0.3; // First 30% is waiting
        _downloadProgress[fileName] = waitProgress;
        notifyListeners();
      }
      
      if (downloadedData.isEmpty) {
        throw Exception('Download timeout - no data received');
      }
      
      // Continue waiting for complete file (or until timeout)
      waitTime = 0;
      int lastDataSize = downloadedData.length;
      int stableCount = 0;
      
      while (waitTime < maxWaitTime && stableCount < 5) { // 5 stable checks (2.5 seconds)
        await Future.delayed(const Duration(milliseconds: checkInterval));
        waitTime += checkInterval;
        
        if (downloadedData.length == lastDataSize) {
          stableCount++;
        } else {
          stableCount = 0;
          lastDataSize = downloadedData.length;
        }
      }
      
      // Cancel the subscription
      await downloadSubscription.cancel();
      
      // Save the downloaded file
      if (downloadedData.isNotEmpty) {
        await _saveDownloadedChunkFile(fileName, downloadedData);
        debugPrint('Successfully downloaded $fileName: ${downloadedData.length} bytes');
        
        // Add to downloaded files list
        if (!_downloadedChunkFiles.contains(fileName)) {
          _downloadedChunkFiles.add(fileName);
        }
        
        // Delete from device if requested
        if (deleteAfterDownload) {
          debugPrint('Deleting $fileName from device after successful download...');
          bool deleteSuccess = await deleteFileFromDevice(fileName);
          if (deleteSuccess) {
            debugPrint('Successfully deleted $fileName from device after download');
          } else {
            debugPrint('Failed to delete $fileName from device after download');
          }
        }

        // Show success notification with accessible paths
        if (!PlatformService.isDesktop) {
          NotificationService.instance.createNotification(
            notificationId: 9,
            title: 'File Downloaded',
            body: deleteAfterDownload 
                ? 'Downloaded & deleted $fileName (${downloadedData.length} bytes)\nCheck Downloads/omi_chunks/'
                : 'Downloaded $fileName (${downloadedData.length} bytes)\nCheck Downloads/omi_chunks/ or Android/data/com.friend.ios.dev/files/omi_chunks/',
          );
        }
      } else {
        throw Exception('No data received for file download');
      }
      
    } catch (e) {
      debugPrint('Error downloading file $fileName: $e');
      
      // Show error notification
      if (!PlatformService.isDesktop) {
        NotificationService.instance.createNotification(
          notificationId: 10,
          title: 'Download Failed',
          body: 'Failed to download $fileName: ${e.toString()}',
        );
      }
    } finally {
      // Clean up download state
      _downloadingFiles[fileName] = false;
      _downloadProgress[fileName] = 1.0;
      notifyListeners();
      
      // Clear progress after delay
      Future.delayed(const Duration(seconds: 2), () {
        _downloadProgress.remove(fileName);
        _downloadingFiles.remove(fileName);
        notifyListeners();
      });
    }
  }
  
  Future<void> _saveDownloadedChunkFile(String fileName, List<int> data) async {
    try {
      // Save to app's internal directory (for app functionality)
      final directory = await getApplicationDocumentsDirectory();
      final downloadsDir = Directory('${directory.path}/downloaded_chunks');
      
      // Create downloads directory if it doesn't exist
      if (!await downloadsDir.exists()) {
        await downloadsDir.create(recursive: true);
      }
      
      // Save the file
      final file = File('${downloadsDir.path}/$fileName');
      await file.writeAsBytes(data);
      
      debugPrint('Saved downloaded file to: ${file.path}');
      
      // ALSO save to user-accessible external storage for debugging
      try {
        // Get external storage directory (publicly accessible)
        final externalDir = await getExternalStorageDirectory();
        if (externalDir != null) {
          // Save to /storage/emulated/0/Android/data/com.friend.ios.dev/files/omi_chunks
          final publicDir = Directory('${externalDir.path}/omi_chunks');
          if (!await publicDir.exists()) {
            await publicDir.create(recursive: true);
          }
          final publicFile = File('${publicDir.path}/$fileName');
          await publicFile.writeAsBytes(data);
          debugPrint('ALSO saved to external storage: ${publicFile.path}');
          debugPrint('External path accessible via file manager: Android/data/com.friend.ios.dev/files/omi_chunks/');
        }
      } catch (e) {
        debugPrint('Could not save to external storage: $e');
      }
      
      // TRY to save to public Downloads folder (requires permission)
      try {
        final publicDownloads = Directory('/storage/emulated/0/Download/omi_chunks');
        if (!await publicDownloads.exists()) {
          await publicDownloads.create(recursive: true);
        }
        final publicFile = File('${publicDownloads.path}/$fileName');
        await publicFile.writeAsBytes(data);
        debugPrint('ALSO saved to public Downloads: ${publicFile.path}');
        debugPrint('Public Downloads accessible at: Downloads/omi_chunks/ folder');
      } catch (e) {
        debugPrint('Could not save to public Downloads (may need storage permission): $e');
      }
      
    } catch (e) {
      debugPrint('Error saving downloaded file $fileName: $e');
      throw Exception('Failed to save downloaded file: $e');
    }
  }

  void _processSystemAudioByteReceived(Uint8List bytes) {
    _systemAudioBuffer.addAll(bytes);
    if (!_systemAudioCaching) {
      _flushSystemAudioBuffer();
    }
  }

  Future<void> pauseDeviceRecording() async {
    if (_recordingDevice == null) return;
    // Pause the BLE stream but keep the device connection
    await _bleBytesStream?.cancel();
    await _bleButtonStream?.cancel();
    _isPaused = true;
    updateRecordingState(RecordingState.pause);
    notifyListeners();
  }

  Future<void> resumeDeviceRecording() async {
    if (_recordingDevice == null) return;
    _isPaused = false;
    // Resume streaming from the device
    await _initiateDeviceAudioStreaming();
    updateRecordingState(RecordingState.deviceRecord);
    notifyListeners();
  }
}
