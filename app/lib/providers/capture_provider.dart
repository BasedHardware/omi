import 'dart:async';
import 'dart:convert';
import 'dart:math' as math;

import 'package:collection/collection.dart';
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

      // Local sync
      // Support: opus codec
      var checkWalSupported = codec.isOpusSupported() &&
          (_socket?.state != SocketServiceState.connected || SharedPreferencesUtil().unlimitedLocalStorageEnabled);
      if (checkWalSupported != _isWalSupported) {
        setIsWalSupported(checkWalSupported);
      }
      if (_isWalSupported) {
        _wal.getSyncs().phone.onByteStream(snapshot);
      }

      // Send WS
      if (_socket?.state == SocketServiceState.connected) {
        final trimmedValue = value.sublist(3);
        _socket?.send(trimmedValue);

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

    // Set device info for WAL creation
    var connection = await ServiceManager.instance().device.ensureConnection(_recordingDevice!.id);
    var pd = await _recordingDevice!.getDeviceInfo(connection);
    String deviceModel = pd.modelNumber.isNotEmpty ? pd.modelNumber : "Omi";
    _wal.getSyncs().phone.setDeviceInfo(_recordingDevice!.id, deviceModel);

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
  int sdCardFileNum = 1;

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
    currentStorageFiles = await _getStorageList(_recordingDevice!.id);
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
