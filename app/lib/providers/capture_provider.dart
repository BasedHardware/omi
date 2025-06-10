import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:flutter_provider_utilities/flutter_provider_utilities.dart';
import 'package:internet_connection_checker_plus/internet_connection_checker_plus.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:uuid/uuid.dart';
import 'package:dio/dio.dart';
import 'package:http_parser/http_parser.dart';

import 'package:omi/backend/http/api/conversations.dart' as conversations_api;
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/backend/schema/message_event.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/message_provider.dart';
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
import 'package:omi/env/env.dart';
import 'package:omi/utils/platform/platform_service.dart';

class CaptureProvider extends ChangeNotifier
    with MessageNotifierMixin
    implements ITransctipSegmentSocketServiceListener {
  // ────────────────────────────────── ctor & listeners ──────────────────────────────────
  CaptureProvider() {
    _internetStatusListener = PureCore().internetConnection.onStatusChange.listen(onInternetStatusChanged);
  }

  // Initialize after construction
  void initialize() {
    // Simple initialization - no complex stale image clearing needed
  }

  // ────────────────────────────────── provider links ────────────────────────────────────
  ConversationProvider? conversationProvider;
  MessageProvider? messageProvider;

  void updateProviderInstances(ConversationProvider? cp, MessageProvider? mp) {
    conversationProvider = cp;
    messageProvider = mp;
    notifyListeners();
  }

  // ────────────────────────────────── services & sockets ─────────────────────────────────
  TranscriptSegmentSocketService? _socket;
  final SdCardSocketService sdCardSocket = SdCardSocketService();
  Timer? _keepAliveTimer;

  // Method channel for system audio permissions
  static const MethodChannel _screenCaptureChannel = MethodChannel('screenCapturePlatform');

  IWalService get _wal => ServiceManager.instance().wal;
  IDeviceService get _deviceService => ServiceManager.instance().device;

  // ───────────────────────────────────── state ──────────────────────────────────────────
  bool _isWalSupported = false;
  bool get isWalSupported => _isWalSupported;

  StreamSubscription<InternetStatus>? _internetStatusListener;
  InternetStatus? _internetStatus;
  InternetStatus? get internetStatus => _internetStatus;

  List<ServerMessageEvent> _transcriptionServiceStatuses = [];
  List<ServerMessageEvent> get transcriptionServiceStatuses => _transcriptionServiceStatuses;

  BtDevice? _recordingDevice;
  List<TranscriptSegment> segments = [];

  bool hasTranscripts = false;
  bool _transcriptServiceReady = false;

  /// Whether the server socket is up **and** we have internet.
  bool get transcriptServiceReady => _transcriptServiceReady && _internetStatus == InternetStatus.connected;

  /// either a device is connected or we're using phone-mic recording
  bool get recordingDeviceServiceReady =>
      _recordingDevice != null ||
      recordingState == RecordingState.record ||
      recordingState == RecordingState.systemAudioRecord;

  bool get havingRecordingDevice => _recordingDevice != null;

  /// flag you referenced earlier but never declared
  bool conversationCreating = false;

  StreamSubscription? _bleBytesStream;
  StreamSubscription? _imageStream;
  StreamSubscription? _bleButtonStream;
  StreamSubscription? _storageStream;

  DateTime? _voiceCommandSession;
  final List<List<int>> _commandBytes = [];

  RecordingState recordingState = RecordingState.stop;

  // Simple image storage - no complex session management
  List<Map<String, dynamic>> capturedImages = [];

  // Keep these for compatibility with existing code that references them
  bool _conversationCompleted = false;

  // Backward compatibility getters for unified approach
  List<Map<String, dynamic>> get allImages => allCapturedImages;
  List<Map<String, dynamic>> get localImages => capturedImages.where((img) => img['data'] != null).toList();
  List<Map<String, dynamic>> get cloudImages => capturedImages.where((img) => img['url'] != null).toList();

  // Shared in-progress conversation state
  String? _inProgressConversationId;
  DateTime? _conversationStartedAt;
  List<Map<String, dynamic>> _inProgressImages = [];
  List<TranscriptSegment> _inProgressSegments = [];
  bool _hasActiveConversation = false;

  StreamSubscription? _speechProfileStream;
  Timer? _blinkTimer;

  // ───────────────────────────────── getters for widgets ────────────────────────────────
  StreamSubscription? get bleBytesStream => _bleBytesStream;
  StreamSubscription? get storageStream => _storageStream;

  // Shared in-progress conversation getters
  String? get inProgressConversationId => _inProgressConversationId;
  DateTime? get conversationStartedAt => _conversationStartedAt;
  bool get hasActiveConversation => _hasActiveConversation;
  List<Map<String, dynamic>> get inProgressImages => _inProgressImages;
  List<TranscriptSegment> get inProgressSegments => _inProgressSegments;

  // Conversation state getters
  bool get conversationCompleted => _conversationCompleted;

  // ─────────────────────────────────── simple mutators ──────────────────────────────────

  void setHasTranscripts(bool value) {
    hasTranscripts = value;
    notifyListeners();
  }

  void setConversationCreating(bool value) {
    conversationCreating = value;
    notifyListeners();
  }

  void setConversationCompleted(bool value) {
    _conversationCompleted = value;
    notifyListeners();
  }

  void setIsWalSupported(bool value) {
    _isWalSupported = value;
    notifyListeners();
  }

  // ───────────────────────────── recording-device management ────────────────────────────
  void _updateRecordingDevice(BtDevice? device) {
    _recordingDevice = device;
    notifyListeners();
  }

  // Public method for external classes to update recording device
  void updateRecordingDevice(BtDevice? device) {
    _updateRecordingDevice(device);

    // If OpenGlass is being set as recording device, set up image streaming
    if (device?.type == DeviceType.openglass) {
      startOpenGlassImageStreaming(device!.id);
    } else if (_recordingDevice?.type == DeviceType.openglass && device == null) {
      // If removing OpenGlass device, stop image streaming
      stopOpenGlassImageStreaming();
    }
  }

  // ─────────────────────────────────── lifecycle ────────────────────────────────────────
  @override
  void dispose() {
    _bleBytesStream?.cancel();
    _bleButtonStream?.cancel();
    _storageStream?.cancel();
    _socket?.unsubscribe(this);
    _keepAliveTimer?.cancel();
    _internetStatusListener?.cancel();
    super.dispose();
  }

  // ─────────────────────────────── Web-socket bootstrap ────────────────────────────────
  Future<void> _initiateWebsocket({
    required BleAudioCodec audioCodec,
    int? sampleRate,
    int? channels,
    bool? isPcm,
    bool force = false,
  }) async {
    print('initiateWebsocket in capture_provider');

    BleAudioCodec codec = audioCodec;
    sampleRate ??= mapCodecToSampleRate(codec);
    channels ??= (codec == BleAudioCodec.pcm16 || codec == BleAudioCodec.pcm8) ? 1 : 2;

    debugPrint('is ws null: ${_socket == null}');
    print('Initiating WebSocket with: codec=$codec, sampleRate=$sampleRate, channels=$channels, isPcm=$isPcm');

    // Connect to the transcript socket
    String language =
        SharedPreferencesUtil().hasSetPrimaryLanguage ? SharedPreferencesUtil().userPrimaryLanguage : "multi";

    _socket = await ServiceManager.instance()
        .socket
        .conversation(codec: codec, sampleRate: sampleRate!, language: language, force: force);

    if (_socket == null) {
      _startKeepAliveServices();
      return;
    }

    _socket!.subscribe(this, this);
    _transcriptServiceReady = true;

    _loadInProgressConversation();
    notifyListeners();
  }

  @override
  void onClosed() {
    _transcriptionServiceStatuses = [];
    _transcriptServiceReady = false;
    debugPrint('[Provider] Socket is closed');
    notifyListeners();
  }

  @override
  void onConnected() {
    _transcriptServiceReady = true;

    // Clear stale images when WebSocket connects to ensure fresh start
    clearStaleImages();

    // Ensure shared in-progress conversation is started when WebSocket connects
    if (!_hasActiveConversation) {
      startInProgressConversation();
    }

    notifyListeners();
  }

  Future refreshInProgressConversations() async {
    _loadInProgressConversation();
  }

  Future _loadInProgressConversation() async {
    // ... existing code ...
  }

  // ─────────────────────────────────── segment flow ────────────────────────────────────
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

    // Update both legacy segments and shared in-progress conversation
    final remain = TranscriptSegment.updateSegments(segments, newSegments);
    TranscriptSegment.combineSegments(segments, remain);

    // Add to shared in-progress conversation
    addSegmentsToInProgressConversation(newSegments);

    hasTranscripts = true;
    notifyListeners();
  }

  @override
  void onImageReceived(dynamic imageData) {
    // Simple blocking check - only block during conversation creation
    if (conversationCreating) {
      return;
    }

    if (imageData != null && imageData is Map<String, dynamic>) {
      final description = imageData['description'];
      final id = imageData['id'] ?? 'unknown';
      final thumbnailUrl = imageData['thumbnail_url'];
      final isInteresting = imageData['is_interesting'] ?? true;

      // Create unified image object
      Map<String, dynamic> newImage = {
        'id': id,
        'thumbnail_url': thumbnailUrl,
        'url': imageData['url'],
        'mime_type': imageData['mime_type'],
        'created_at': imageData['created_at'],
        'description': description?.toString(),
        'is_interesting': isInteresting,
      };

      // Add to unified captured images
      addCapturedImage(newImage);

      notifyListeners();
    } else {
      // Invalid image data
    }
  }

  @override
  void onClearLiveImages(dynamic clearData) {
    if (clearData != null) {
      final conversationId = clearData['conversation_id'];
      final reason = clearData['reason'];
      final processedCount = clearData['processed_image_count'];

      // Clear all captured images when conversation is created
      if (reason == 'conversation_created' ||
          reason == 'added_to_existing_conversation' ||
          reason == 'processed_into_new_conversation' ||
          reason == 'processed_to_existing_conversation') {
        // Simple immediate cleanup
        capturedImages.clear();
        _inProgressImages.clear();
        clearInProgressConversation();

        // Brief block then allow new sessions
        setConversationCreating(false);
        setConversationCompleted(false);

        notifyListeners();
      }
    }
  }

  @override
  void onError(Object err) {
    // Handle WebSocket errors if needed.
    // Depending on the error, you might want to update the UI or try to reconnect.
  }

  // ─────────────────────────── event-stream from transcript socket ──────────────────────
  @override
  void onMessageEventReceived(ServerMessageEvent event) {
    switch (event.type) {
      case MessageEventType.conversationProcessingStarted:
        if (event.conversation == null) {
          return;
        }
        conversationProvider?.addProcessingConversation(event.conversation!);
        _resetStateVariables();
        break;

      case MessageEventType.conversationCreated:
        if (event.conversation == null) {
          return;
        }
        event.conversation!.isNew = true;
        conversationProvider?.removeProcessingConversation(event.conversation!.id);
        _processConversationCreated(event.conversation, event.messages ?? []);
        break;

      case MessageEventType.lastConversation:
        if (event.memoryId == null) {
          return;
        }
        _handleLastConvoEvent(event.memoryId!);
        break;

      case MessageEventType.translating:
        if (event.segments?.isEmpty ?? true) {
          return;
        }
        _handleTranslationEvent(event.segments!);
        break;

      case MessageEventType.serviceStatus:
        if (event.status == null) return;
        _transcriptionServiceStatuses
          ..add(event)
          ..replaceRange(0, 0, []); // swap list instance so listeners fire
        notifyListeners();
        break;

      case MessageEventType.newConversationCreateFailed:
        // Handle conversation creation failure if needed
        break;

      case MessageEventType.newProcessingConversationCreated:
        // Handle new processing conversation creation if needed
        break;

      case MessageEventType.processingConversationStatusChanged:
        // Handle processing conversation status change if needed
        break;

      case MessageEventType.ping:
        // Handle ping messages (typically used for keep-alive)
        break;

      case MessageEventType.conversationBackwardSynced:
        // Handle conversation backward sync events if needed
        break;

      case MessageEventType.unknown:
        // Handle unknown message events
        break;
    }
  }

  // ──────────────────────────── event helpers / processors ──────────────────────────────
  Future<void> _resetStateVariables() async {
    segments = [];
    hasTranscripts = false;

    // Reset conversation completion state for new conversation
    setConversationCompleted(false);
    setConversationCreating(false);

    // Clear captured images for fresh start
    clearCapturedImages();

    notifyListeners();
  }

  Future<void> _processConversationCreated(ServerConversation? conversation, List<ServerMessage> messages) async {
    if (conversation == null) return;
    conversationProvider?.upsertConversation(conversation);
    MixpanelManager().conversationCreated(conversation);
  }

  Future<void> streamRecording() async {
    updateRecordingState(RecordingState.initialising);
    await Permission.microphone.request();
    
    // set profile & socket first - specify this is for phone mic
    await changeAudioRecordProfile(audioCodec: BleAudioCodec.pcm16, sampleRate: 16000, isPcm: true);

    // Reset conversation completion state for new recording session
    setConversationCompleted(false);

    // Start shared in-progress conversation
    startInProgressConversation();

    // begin mic
    await ServiceManager.instance().mic.start(
          onByteReceived: (bytes) {
            if (_socket?.state == SocketServiceState.connected) _socket!.send(bytes);
          },
          onRecording: () => updateRecordingState(RecordingState.record),
          onStop: () => updateRecordingState(RecordingState.stop),
          onInitializing: () => updateRecordingState(RecordingState.initialising),
        );
  }

  Future<void> _handleLastConvoEvent(String memoryId) async {
    final exists = conversationProvider?.conversations.any((c) => c.id == memoryId) ?? false;
    if (exists) return;

    final convo = await conversations_api.getConversationById(memoryId);
    if (convo != null) {
      conversationProvider?.upsertConversation(convo);
    } else {
      // Failed to fetch conversation
    }
  }

  void _handleTranslationEvent(List<TranscriptSegment> translatedSegments) {
    try {
      if (translatedSegments.isEmpty) return;

      final remain = TranscriptSegment.updateSegments(segments, translatedSegments);
      if (remain.isNotEmpty) {
        // Added new translated segments
      }
      notifyListeners();
    } catch (e) {
      // Error handling translation event
    }
  }

  // ─────────────────────────────── internet callback ────────────────────────────────────
  void onInternetStatusChanged(InternetStatus status) {
    _internetStatus = status;
    notifyListeners();
  }

  Future _stopStreamRecordingLegacy({bool cleanDevice = false}) async {
    if (cleanDevice) {
      _updateRecordingDevice(null);
    }
    await _cleanupCurrentState();
    updateRecordingState(RecordingState.stop);
    await _socket?.stop(reason: 'stop stream device recording');
  }

  Future<void> streamSystemAudioRecording() async {
    if (!PlatformService.isDesktop) {
      notifyError('System audio recording is only available on macOS and Windows.');
      return;
    }

    updateRecordingState(RecordingState.initialising);

    // WORKAROUND FOR MACOS SONOMA BUG: Try recording first without checking permissions
    // This works around the bug where permissions show as undetermined even when granted
    debugPrint('Attempting to start system audio recording directly (macOS bug workaround)');

    try {
      await changeAudioRecordProfile(audioCodec: BleAudioCodec.pcm16, sampleRate: 16000);

      // Try to start recording immediately - if permissions are actually granted, this will work
      bool recordingStarted = false;

      await ServiceManager.instance().systemAudio.start(onFormatReceived: (Map<String, dynamic> format) async {
        final int sampleRate = ((format['sampleRate'] ?? 16000) as num).toInt();
        final int channels = ((format['channels'] ?? 1) as num).toInt();
        BleAudioCodec determinedCodec = BleAudioCodec.pcm16;
      }, onByteReceived: (bytes) {
        if (_socket?.state == SocketServiceState.connected) {
          _socket?.send(bytes);
        }
      }, onRecording: () {
        recordingStarted = true;
        updateRecordingState(RecordingState.systemAudioRecord);
        debugPrint('System audio recording started successfully - permissions were actually granted');
      }, onStop: () {
        updateRecordingState(RecordingState.stop);
        _socket?.stop(reason: 'system audio stream ended from native');
      }, onError: (error) {
        debugPrint('System audio failed to start, error: $error');
        // Only now do we check and request permissions
        _handleSystemAudioPermissionError(error);
      });

      // Give it a moment to start or fail
      await Future.delayed(const Duration(milliseconds: 500));

      if (recordingStarted) {
        // Success! Recording started despite potentially incorrect permission status
        return;
      } else {
        // If we get here, try the permission flow
        debugPrint('Recording did not start immediately, checking permissions');
        await _checkAndRequestPermissions();
      }
    } catch (e) {
      debugPrint('Error attempting direct system audio start: $e');
      await _checkAndRequestPermissions();
    }
  }

  Future<void> _handleSystemAudioPermissionError(String error) async {
    debugPrint('System audio failed with error: $error');

    if (error.contains('MIC_PERMISSION_REQUIRED') || error.contains('microphone')) {
      AppSnackbar.showSnackbarError(
          'Microphone permission is required. Please grant permission in System Preferences > Privacy & Security > Microphone.');
    } else if (error.contains('SCREEN_PERMISSION_REQUIRED') || error.contains('screen')) {
      AppSnackbar.showSnackbarError(
          'Screen recording permission is required. Please grant permission in System Preferences > Privacy & Security > Screen Recording.');
    } else {
      // Generic permission error - try the full permission check
      await _checkAndRequestPermissions();
    }

    updateRecordingState(RecordingState.stop);
  }

  Future<void> _checkAndRequestPermissions() async {
    try {
      // Check microphone permission first
      String micStatus = await _screenCaptureChannel.invokeMethod('checkMicrophonePermission');
      debugPrint('Microphone permission status: $micStatus');

      if (micStatus != 'granted') {
        if (micStatus == 'undetermined' || micStatus == 'unavailable') {
          bool micGranted = await _screenCaptureChannel.invokeMethod('requestMicrophonePermission');
          if (!micGranted) {
            AppSnackbar.showSnackbarError('Microphone permission is required for system audio recording.');
            updateRecordingState(RecordingState.stop);
            return;
          }
        } else if (micStatus == 'denied') {
          AppSnackbar.showSnackbarError(
              'Microphone permission denied. Please grant permission in System Preferences > Privacy & Security > Microphone.');
          updateRecordingState(RecordingState.stop);
          return;
        }
      }

      // Check screen capture permission
      String screenStatus = await _screenCaptureChannel.invokeMethod('checkScreenCapturePermission');
      debugPrint('Screen capture permission status: $screenStatus');

      if (screenStatus != 'granted') {
        // Try once more to start recording before requesting permission
        // This is the key workaround for the macOS bug
        debugPrint('Screen permission not granted, but trying recording once more due to macOS bug');

        try {
          bool secondAttemptWorked = false;

          await ServiceManager.instance().systemAudio.start(onFormatReceived: (Map<String, dynamic> format) async {
            final int sampleRate = ((format['sampleRate'] ?? 16000) as num).toInt();
            final int channels = ((format['channels'] ?? 1) as num).toInt();
            BleAudioCodec determinedCodec = BleAudioCodec.pcm16;
          }, onByteReceived: (bytes) {
            if (_socket?.state == SocketServiceState.connected) {
              _socket?.send(bytes);
            }
          }, onRecording: () {
            secondAttemptWorked = true;
            updateRecordingState(RecordingState.systemAudioRecord);
            debugPrint('Second attempt succeeded - macOS permission bug confirmed');
          }, onStop: () {
            updateRecordingState(RecordingState.stop);
            _socket?.stop(reason: 'system audio stream ended from native');
          }, onError: (error) {
            debugPrint('Second attempt also failed: $error');
          });

          await Future.delayed(const Duration(milliseconds: 500));

          if (secondAttemptWorked) {
            return; // Success on second try!
          }
        } catch (e) {
          debugPrint('Second attempt exception: $e');
        }

        // Only request permission if both attempts failed
        bool screenGranted = await _screenCaptureChannel.invokeMethod('requestScreenCapturePermission');
        if (!screenGranted) {
          AppSnackbar.showSnackbarError(
              'Screen recording permission is required. The app is already granted permission in System Preferences, but you may need to restart the app due to a macOS bug.');
          updateRecordingState(RecordingState.stop);
          return;
        }

        // Try one final time after permission request
        await streamSystemAudioRecording();
      }
    } catch (e) {
      debugPrint('Error in permission checking: $e');
      notifyError('Permission error: $e');
      updateRecordingState(RecordingState.stop);
    }
  }

  Future<void> stopSystemAudioRecording() async {
    if (!Platform.isMacOS) return;
    ServiceManager.instance().systemAudio.stop();
    updateRecordingState(RecordingState.stop);
    await _socket?.stop(reason: 'stop system audio recording from Flutter');
    await _cleanupCurrentState();
  }

  // ───────────────────────────── keep-alive watchdog ────────────────────────────────────
  void _startKeepAliveServices() {
    _keepAliveTimer?.cancel();
    _keepAliveTimer = Timer.periodic(const Duration(seconds: 15), (t) async {
      if (!recordingDeviceServiceReady || _socket?.state == SocketServiceState.connected) {
        t.cancel();
        return;
      }

      if (_recordingDevice != null) {
        final codec = await _getAudioCodec(_recordingDevice!.id);
        await _initiateWebsocket(audioCodec: codec);
        return;
      }

      if (recordingState == RecordingState.record) {
        await _initiateWebsocket(audioCodec: BleAudioCodec.pcm16, sampleRate: 16000);
      }
      if (recordingState == RecordingState.systemAudioRecord && Platform.isMacOS) {
        debugPrint("[Provider] System audio was recording, but socket disconnected. Consider manual restart.");
      }
    });
  }

  // ═════════════════════════════════ device / mic streaming ═════════════════════════════
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

  Future<void> _resetState() async {
    await _cleanupCurrentState();
    await _ensureDeviceSocketConnection();
    await _initiateDeviceAudioStreaming();
    await initiateStorageBytesStreaming();
    notifyListeners();
  }

  Future<void> _cleanupCurrentState() async {
    await _closeBleStream();
    await _closeImageStream();
    notifyListeners();
  }

  Future<void> _ensureDeviceSocketConnection() async {
    if (_recordingDevice == null) return;

    // Skip WebSocket setup for OpenGlass devices - they don't stream audio
    if (_recordingDevice!.type == DeviceType.openglass) {
      return;
    }

    final codec = await _getAudioCodec(_recordingDevice!.id);
    final language =
        SharedPreferencesUtil().hasSetPrimaryLanguage ? SharedPreferencesUtil().userPrimaryLanguage : 'multi';

    final socketMismatch =
        language != _socket?.language || codec != _socket?.codec || _socket?.state != SocketServiceState.connected;

    if (socketMismatch) {
      await _initiateWebsocket(audioCodec: codec, force: true);
    }
  }

  Future<void> _initiateDeviceAudioStreaming() async {
    if (_recordingDevice == null) return;

    // Skip audio streaming for OpenGlass devices - they only have camera, no microphone
    if (_recordingDevice!.type == DeviceType.openglass) {
      return;
    }

    final deviceId = _recordingDevice!.id;
    final codec = await _getAudioCodec(deviceId);

    await _wal.getSyncs().phone.onAudioCodecChanged(codec);
    await streamButton(deviceId);
    await streamAudioToWs(deviceId, codec);
    notifyListeners();
  }

  // ═════════════════════════════════ BLE helpers ════════════════════════════════════════
  Future<BleAudioCodec> _getAudioCodec(String deviceId) async {
    final connection = await ServiceManager.instance().device.ensureConnection(deviceId);
    if (connection == null) return BleAudioCodec.pcm8;
    return connection.getAudioCodec();
  }

  Future<bool> _playSpeakerHaptic(String deviceId, int level) async {
    final conn = await ServiceManager.instance().device.ensureConnection(deviceId);
    if (conn == null) return false;
    return await conn.performPlayToSpeakerHaptic(level);
  }

  Future<StreamSubscription?> _getBleAudioBytesListener(
    String deviceId, {
    required void Function(List<int>) onAudioBytesReceived,
  }) async {
    final conn = await ServiceManager.instance().device.ensureConnection(deviceId);
    return conn?.getBleAudioBytesListener(onAudioBytesReceived: onAudioBytesReceived);
  }

  Future<StreamSubscription?> _getBleButtonListener(
    String deviceId, {
    required void Function(List<int>) onButtonReceived,
  }) async {
    final conn = await ServiceManager.instance().device.ensureConnection(deviceId);
    return conn?.getBleButtonListener(onButtonReceived: onButtonReceived);
  }

  Future<List<int>> _getBleButtonState(String deviceId) async {
    final conn = await ServiceManager.instance().device.ensureConnection(deviceId);
    if (conn == null) return <int>[];
    return await conn.getBleButtonState();
  }

  Future<StreamSubscription?> _getBleStorageBytesListener(
    String deviceId, {
    required void Function(List<int>) onStorageBytesReceived,
  }) async {
    final conn = await ServiceManager.instance().device.ensureConnection(deviceId);
    return conn?.getBleStorageBytesListener(onStorageBytesReceived: onStorageBytesReceived);
  }

  // ──────────────────────────── BLE streaming entry-points ──────────────────────────────
  Future<void> streamButton(String deviceId) async {
    _bleButtonStream?.cancel();
    _bleButtonStream = await _getBleButtonListener(deviceId, onButtonReceived: (value) {
      if (value.length < 4) return;
      final buttonState = ByteData.view(Uint8List.fromList(value.sublist(0, 4).reversed.toList()).buffer).getUint32(0);

      // start long press
      if (buttonState == 3 && _voiceCommandSession == null) {
        _voiceCommandSession = DateTime.now();
        _commandBytes.clear();
        _watchVoiceCommands(deviceId, _voiceCommandSession!);
        _playSpeakerHaptic(deviceId, 1);
      }

      // release
      if (buttonState == 5 && _voiceCommandSession != null) {
        _voiceCommandSession = null;
        final data = List<List<int>>.from(_commandBytes);
        _commandBytes.clear();
        _processVoiceCommandBytes(deviceId, data);
      }
    });
  }

  Future<void> streamAudioToWs(String deviceId, BleAudioCodec codec) async {
    _bleBytesStream?.cancel();
    _bleBytesStream = await _getBleAudioBytesListener(deviceId, onAudioBytesReceived: (value) {
      if (value.length < 3) return;

      // accumulate command bytes during press-and-hold
      if (_voiceCommandSession != null) {
        _commandBytes.add(value.sublist(3));
      }

      // check WAL support
      final deviceFirstConnectedAt = _deviceService.getFirstConnectedAt();
      final shouldEnableWal = codec.isOpusSupported() &&
          deviceFirstConnectedAt != null &&
          deviceFirstConnectedAt.isBefore(DateTime.now().subtract(const Duration(seconds: 15))) &&
          SharedPreferencesUtil().localSyncEnabled;

      if (shouldEnableWal != _isWalSupported) setIsWalSupported(shouldEnableWal);
      if (_isWalSupported) {
        _wal.getSyncs().phone.onByteStream(value);
      }

      // forward to websocket
      if (_socket?.state == SocketServiceState.connected) {
        _socket!.send(value.sublist(3));
        if (_isWalSupported) _wal.getSyncs().phone.onBytesSync(value);
      }
    });
  }

  // ────────────────────────── mic (phone) streaming helpers ─────────────────────────────
  Future<void> stopStreamRecording() async {
    // Set conversation creating flag to prevent new images during stopping
    setConversationCreating(true);

    await _cleanupCurrentState();
    ServiceManager.instance().mic.stop();
    await _socket?.stop(reason: 'stop stream recording');

    // Don't finalize the in-progress conversation yet - let the API call process it first
    // finalizeInProgressConversation will be called after successful conversation creation
  }

  Future<void> streamDeviceRecording({BtDevice? device}) async {
    if (device != null) _updateRecordingDevice(device);

    // Reset conversation completion state for new device recording session
    setConversationCompleted(false);

    // Skip device recording setup for OpenGlass - it's camera-only and shouldn't affect audio
    if (device?.type == DeviceType.openglass) {
      // Start shared in-progress conversation for image tracking
      startInProgressConversation();

      // Set up dedicated OpenGlass image streaming
      await startOpenGlassImageStreaming(device!.id);

      // Skip audio-related state reset to avoid interfering with phone mic
      await initiateStorageBytesStreaming();
      notifyListeners();
      return;
    }

    // Start shared in-progress conversation for device recording
    startInProgressConversation();

    await _resetState();
  }

  Future<void> stopStreamDeviceRecording({bool cleanDevice = false}) async {
    if (cleanDevice) _updateRecordingDevice(null);

    // Set conversation creating flag to prevent new images during stopping
    setConversationCreating(true);

    // Use appropriate cleanup based on connected device type
    if (_recordingDevice?.type == DeviceType.openglass) {
      // For OpenGlass, only clean up audio streams but preserve image streams
      await _cleanupCurrentState();
    } else {
      // For regular devices, clean up everything
      await _cleanupDeviceState();
    }

    await _socket?.stop(reason: 'stop stream device recording');

    // Don't finalize the in-progress conversation yet - let the API call process it first
    // finalizeInProgressConversation will be called after successful conversation creation
  }

  // ─────────────────────────── helper: update recording flag ────────────────────────────
  void updateRecordingState(RecordingState state) {
    recordingState = state;
    notifyListeners();
  }

  // ────────────────────────────── voice-command capture ────────────────────────────────
  void _watchVoiceCommands(String deviceId, DateTime session) {
    Timer.periodic(const Duration(seconds: 3), (t) async {
      if (session != _voiceCommandSession) {
        t.cancel();
        return;
      }
      final value = await _getBleButtonState(deviceId);
      final buttonState = ByteData.view(Uint8List.fromList(value.sublist(0, 4).reversed.toList()).buffer).getUint32(0);

      // force process if BLE missed release
      if (buttonState == 5 && session == _voiceCommandSession) {
        _voiceCommandSession = null;
        final data = List<List<int>>.from(_commandBytes);
        _commandBytes.clear();
        _processVoiceCommandBytes(deviceId, data);
      }
    });
  }

  void _processVoiceCommandBytes(String deviceId, List<List<int>> data) async {
    if (data.isEmpty || messageProvider == null) return;
    final codec = await _getAudioCodec(deviceId);
    await messageProvider!.sendVoiceMessageStreamToServer(
      data,
      onFirstChunkRecived: () => _playSpeakerHaptic(deviceId, 2),
      codec: codec,
    );
  }

  // ─────────────────────────────── BLE cleanup helpers ────────────────────────────────
  Future<void> _closeBleStream() async {
    await _bleBytesStream?.cancel();
  }

  Future<void> _closeImageStream() async {
    await _imageStream?.cancel();
  }

  Future<void> _cleanupDeviceState() async {
    await _closeBleStream();
    await _closeImageStream();
    notifyListeners();
  }

  // ═══════════════════════════════ SD-card download section ═════════════════════════════
  // state fields
  List<int> currentStorageFiles = <int>[];
  int sdCardFileNum = 1;

  int currentTotalBytesReceived = 0;
  double currentSdCardSecondsReceived = 0.0;

  int totalStorageFileBytes = 0; // bytes on storage
  int totalBytesReceived = 0; // bytes already pulled
  double sdCardSecondsTotal = 0.0;
  double sdCardSecondsReceived = 0.0;

  bool sdCardDownloadDone = false;
  bool sdCardReady = false;
  bool sdCardIsDownloading = false;

  String btConnectedTime = '';
  Timer? sdCardReconnectionTimer;

  void setSdCardIsDownloading(bool value) {
    sdCardIsDownloading = value;
    notifyListeners();
  }

  Future<void> updateStorageList() async {
    if (_recordingDevice == null) return;
    currentStorageFiles = await _getStorageList(_recordingDevice!.id);
    if (currentStorageFiles.isEmpty) {
      SharedPreferencesUtil().deviceIsV2 = false;
      return;
    }
    totalStorageFileBytes = currentStorageFiles[0];
    final storageOffset = currentStorageFiles.length < 2 ? 0 : currentStorageFiles[1];
    totalBytesReceived = storageOffset;
    notifyListeners();
  }

  Future<void> initiateStorageBytesStreaming() async {
    if (_recordingDevice == null) return;
    final deviceId = _recordingDevice!.id;

    final storageFiles = await _getStorageList(deviceId);
    if (storageFiles.isEmpty) return;

    final totalBytes = storageFiles[0];
    if (totalBytes <= 0) return;

    var storageOffset = storageFiles.length < 2 ? 0 : storageFiles[1];
    if (storageOffset > totalBytes) {
      storageOffset = 0;
    }

    final codec = await _getAudioCodec(deviceId);
    sdCardSecondsTotal = totalBytes / codec.getFramesLengthInBytes() / codec.getFramesPerSecond();
    sdCardSecondsReceived = storageOffset / codec.getFramesLengthInBytes() / codec.getFramesPerSecond();

    // mark ready if >10s left
    if (totalBytes - storageOffset > 10 * codec.getFramesLengthInBytes() * codec.getFramesPerSecond()) {
      sdCardReady = true;
    }
    notifyListeners();
  }

  Future<void> _getFileFromDevice(int fileNum, int offset) async {
    sdCardFileNum = fileNum;
    await _writeToStorage(_recordingDevice!.id, fileNum, 0, offset);
  }

  Future<void> _clearFileFromDevice(int fileNum) async {
    sdCardFileNum = fileNum;
    await _writeToStorage(_recordingDevice!.id, fileNum, 1, 0);
  }

  Future<void> _pauseFileFromDevice(int fileNum) async {
    sdCardFileNum = fileNum;
    await _writeToStorage(_recordingDevice!.id, fileNum, 3, 0);
  }

  void _notifySdCardComplete() {
    NotificationService.instance.clearNotification(8);
    NotificationService.instance.createNotification(
      notificationId: 8,
      title: 'Sd Card Processing Complete',
      body: 'Your Sd Card data is now processed! Enter the app to see.',
    );
  }

  Future<bool> _writeToStorage(String deviceId, int fileNum, int command, int offset) async {
    final conn = await ServiceManager.instance().device.ensureConnection(deviceId);
    if (conn == null) return false;
    return await conn.writeToStorage(fileNum, command, offset);
  }

  Future<List<int>> _getStorageList(String deviceId) async {
    final conn = await ServiceManager.instance().device.ensureConnection(deviceId);
    if (conn == null) return <int>[];
    return await conn.getStorageList();
  }

  void onRecordProfileSettingChanged() {
    // TODO: Implement this method if needed, or remove calls to it.
    notifyListeners();
  }

  void clearTranscripts() {
    segments.clear();
    hasTranscripts = false;
    notifyListeners();
  }

  void addCapturedImage(Map<String, dynamic> imageData) {
    // Simple blocking check - only block during conversation creation
    if (conversationCreating) {
      return;
    }

    // Simple deduplication by ID
    final imageId = imageData['id']?.toString() ?? 'unknown_${DateTime.now().millisecondsSinceEpoch}';
    bool alreadyExists = capturedImages.any((img) => img['id']?.toString() == imageId);

    if (!alreadyExists) {
      capturedImages.add(imageData);

      // Add to in-progress conversation for timeline display
      addImageToInProgressConversation(imageData);
    } else {
      // Skipping duplicate image
    }

    notifyListeners();
  }

  void clearCapturedImages() {
    final oldCount = capturedImages.length;
    capturedImages.clear();
    notifyListeners();
  }

  // Get all captured images for display
  List<Map<String, dynamic>> get allCapturedImages {
    final imageList = List<Map<String, dynamic>>.from(capturedImages);
    return imageList;
  }

  // ─────────────────────────── Shared In-Progress Conversation Management ──────────────────────────
  void startInProgressConversation() {
    if (_hasActiveConversation) return;

    _inProgressConversationId = 'in_progress_${DateTime.now().millisecondsSinceEpoch}';
    _conversationStartedAt = DateTime.now();
    _inProgressImages.clear();
    _inProgressSegments.clear();
    _hasActiveConversation = true;

    notifyListeners();
  }

  void addImageToInProgressConversation(Map<String, dynamic> imageData) {
    if (!_hasActiveConversation) {
      startInProgressConversation();
    }

    // Simple duplicate check
    bool alreadyExists = _inProgressImages.any((img) => img['id'] == imageData['id']);

    if (!alreadyExists) {
      _inProgressImages.add(imageData);
      notifyListeners();
    }
  }

  void addSegmentsToInProgressConversation(List<TranscriptSegment> newSegments) {
    if (!_hasActiveConversation) {
      startInProgressConversation();
    }

    // Update segments using existing logic
    final remain = TranscriptSegment.updateSegments(_inProgressSegments, newSegments);
    TranscriptSegment.combineSegments(_inProgressSegments, remain);

    notifyListeners();
  }

  Future<void> finalizeInProgressConversation() async {
    if (!_hasActiveConversation) return;

    // Clear the in-progress state
    _hasActiveConversation = false;
    _inProgressConversationId = null;
    _conversationStartedAt = null;
    _inProgressImages.clear();
    _inProgressSegments.clear();

    // SIMPLE & ELEGANT: Clear images immediately and set up fallback
    Timer(const Duration(seconds: 2), () {
      capturedImages.clear();
      setConversationCreating(false);
      setConversationCompleted(false);
      notifyListeners();
    });

    notifyListeners();
  }

  void clearInProgressConversation() {
    _hasActiveConversation = false;
    _inProgressConversationId = null;
    _conversationStartedAt = null;
    _inProgressImages.clear();
    _inProgressSegments.clear();
    notifyListeners();
  }

  // Simple OpenGlass image streaming methods
  Future<void> startOpenGlassImageStreaming(String deviceId) async {
    // Device provider already handles OpenGlass image streaming
    return;
  }

  Future<void> stopOpenGlassImageStreaming() async {
    await _closeImageStream();
  }

  Future<void> stop() async {
    // Unified stop method for both phone mic and device recording
    if (recordingState == RecordingState.record) {
      // Phone mic recording is active
      await stopStreamRecording();
    } else if (_recordingDevice != null) {
      // Device recording is active
      await stopStreamDeviceRecording();
    } else {
      // Just stop the socket if no specific recording type
      await _socket?.stop(reason: 'stop conversation');
    }

    // Don't automatically finalize - let the conversation creation flow handle it
  }

  void clearStaleImages() {
    // Simple wrapper for unified approach - just clear captured images
    clearCapturedImages();
  }

  void addLocalImage(Map<String, dynamic> localImage) {
    // Backward compatibility wrapper for unified approach
    addCapturedImage(localImage);
  }

  // Elegant method to update images with descriptions from backend response
  void updateImageWithDescription({
    required String imageId,
    required String description,
    String? thumbnailUrl,
    String? fullUrl,
  }) {
    bool updated = false;

    // Update in captured images (main list)
    for (int i = 0; i < capturedImages.length; i++) {
      if (capturedImages[i]['id'] == imageId) {
        capturedImages[i] = {
          ...capturedImages[i],
          'description': description,
          'thumbnail_url': thumbnailUrl,
          'url': fullUrl,
          'hasDescription': true,
        };
        updated = true;
        break;
      }
    }

    // Update in in-progress images
    for (int i = 0; i < _inProgressImages.length; i++) {
      if (_inProgressImages[i]['id'] == imageId) {
        _inProgressImages[i] = {
          ..._inProgressImages[i],
          'description': description,
          'thumbnail_url': thumbnailUrl,
          'url': fullUrl,
          'hasDescription': true,
        };
        updated = true;
        break;
      }
    }

    if (updated) {
      notifyListeners();
    } else {
      // Could not find image to update
    }
  }
}
