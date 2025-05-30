import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:flutter_provider_utilities/flutter_provider_utilities.dart';
import 'package:internet_connection_checker_plus/internet_connection_checker_plus.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:uuid/uuid.dart';
import 'package:dio/dio.dart';
import 'package:http_parser/http_parser.dart';

import 'package:omi/backend/http/api/conversations.dart';
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
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/enums.dart';
import 'package:omi/env/env.dart';

class CaptureProvider extends ChangeNotifier
    with MessageNotifierMixin
    implements ITransctipSegmentSocketServiceListener {
  // ────────────────────────────────── ctor & listeners ──────────────────────────────────
  CaptureProvider() {
    _internetStatusListener =
        PureCore().internetConnection.onStatusChange.listen(onInternetStatusChanged);
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

  IWalService get _wal => ServiceManager.instance().wal;
  IDeviceService get _deviceService => ServiceManager.instance().device;

  // ───────────────────────────────────── state ──────────────────────────────────────────
  bool _isWalSupported = false;
  bool get isWalSupported => _isWalSupported;

  StreamSubscription<InternetStatus>? _internetStatusListener;
  InternetStatus? _internetStatus;
  InternetStatus? get internetStatus => _internetStatus;

  final List<ServerMessageEvent> _transcriptionServiceStatuses = [];
  List<ServerMessageEvent> get transcriptionServiceStatuses => _transcriptionServiceStatuses;

  BtDevice? _recordingDevice;
  List<TranscriptSegment> segments = [];

  bool hasTranscripts = false;
  bool _transcriptServiceReady = false;

  /// Whether the server socket is up **and** we have internet.
  bool get transcriptServiceReady =>
      _transcriptServiceReady && _internetStatus == InternetStatus.connected;

  /// either a device is connected or we're using phone-mic recording
  bool get recordingDeviceServiceReady =>
      _recordingDevice != null || recordingState == RecordingState.record;

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

  // Local images for immediate display
  List<Map<String, dynamic>> localImages = [];
  
  // Cloud images received via WebSocket  
  List<Map<String, dynamic>> cloudImages = [];
  
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

  // ─────────────────────────────────── simple mutators ──────────────────────────────────
  void setHasTranscripts(bool value) {
    hasTranscripts = value;
    notifyListeners();
  }

  void setConversationCreating(bool value) {
    debugPrint('set Conversation creating $value');
    conversationCreating = value;
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
    bool force = false,
  }) async {
    debugPrint('initiateWebsocket in capture_provider');

    final BleAudioCodec codec = audioCodec;
    sampleRate ??= codec.isOpusSupported() ? 16000 : 8000;

    final String language = SharedPreferencesUtil().hasSetPrimaryLanguage
        ? SharedPreferencesUtil().userPrimaryLanguage
        : 'multi';

    _socket = await ServiceManager.instance()
        .socket
        .conversation(codec: codec, sampleRate: sampleRate, language: language, force: force);

    if (_socket == null) {
      _startKeepAliveServices();
      debugPrint('Cannot create new conversation socket');
      return;
    }

    _socket!.subscribe(this, this);
    _transcriptServiceReady = true;

    _loadInProgressConversation();
    notifyListeners();
  }

  @override
  void onClosed() {
    debugPrint('CaptureProvider: WebSocket closed');
  }

  @override
  void onConnected() {
    _transcriptServiceReady = true;
    debugPrint('🔗 WebSocket connected - starting shared in-progress conversation');
    
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

  // ─────────────────────────────────── segment flow ─────────────────────────────────────
  @override
  void onSegmentReceived(List<TranscriptSegment> newSegments) {
    _processNewSegmentReceived(newSegments);
  }

  void _processNewSegmentReceived(List<TranscriptSegment> newSegments) async {
    if (newSegments.isEmpty) return;

    if (segments.isEmpty) {
      debugPrint('newSegments: ${newSegments.last}');
      FlutterForegroundTask.sendDataToTask(jsonEncode({'location': true}));
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
    debugPrint('🔥 CaptureProvider: onImageReceived - START');
    debugPrint('🔥 Raw imageData: $imageData');
    debugPrint('🔥 ImageData type: ${imageData.runtimeType}');
    debugPrint('🔥 ImageData is Map: ${imageData is Map}');
    
    if (imageData != null) {
      if (imageData is Map<String, dynamic>) {
        debugPrint('🔥 ImageData keys: ${imageData.keys.toList()}');
      }
      
      final description = imageData['description'];
      final id = imageData['id'] ?? 'unknown';
      final thumbnailUrl = imageData['thumbnail_url'];
      final isInteresting = imageData['is_interesting'] ?? true; // Default to interesting if not specified
      
      debugPrint('🔍 Image received: ID=$id, Has description: ${description != null}');
      debugPrint('🌐 Full thumbnail URL: $thumbnailUrl');
      debugPrint('🎯 Interesting for summaries: $isInteresting');
      debugPrint('🎬 Has active conversation before: $_hasActiveConversation');
      
      if (description != null) {
        debugPrint('📝 Description content: "${description.toString()}"');
        
        // Store image with description and interesting flag
        Map<String, dynamic> newImage = {
          'id': id,
          'thumbnail_url': thumbnailUrl,
          'url': imageData['url'],
          'mime_type': imageData['mime_type'],
          'created_at': imageData['created_at'],
          'description': description.toString(),
          'is_interesting': isInteresting, // Store the interesting flag for UI
        };
        
        // **IMPROVED: Check if image already exists in cloudImages to avoid duplicates**
        bool foundInCloud = false;
        for (int i = 0; i < cloudImages.length; i++) {
          if (cloudImages[i]['id'] == id) {
            cloudImages[i] = newImage;
            foundInCloud = true;
            debugPrint('🔄 Updated existing cloud image with description: ID=$id');
            break;
          }
        }
        
        // **REMOVED: Don't add to cloudImages here - let the logic below handle it after checking localImages**
        
        // **Also update in-progress images if this image exists there**
        bool foundInProgress = false;
        for (int i = 0; i < _inProgressImages.length; i++) {
          if (_inProgressImages[i]['id'] == id) {
            _inProgressImages[i] = newImage;
            foundInProgress = true;
            debugPrint('🔄 Updated in-progress image with description: ID=$id');
            break;
          }
        }
        
        // **Update local images if this image exists there**
        bool foundLocal = false;
        for (int i = 0; i < localImages.length; i++) {
          if (localImages[i]['id'] == id) {
            localImages[i] = newImage;
            foundLocal = true;
            debugPrint('🔄 Updated local image with description: ID=$id');
            break;
          }
        }
        
        // **FIXED: Only add to cloudImages if NOT found in localImages**
        // This prevents duplicates during live recording sessions
        if (!foundLocal && !foundInCloud) {
          cloudImages.add(newImage);
          debugPrint('📸 Added new image to cloudImages: ID=$id, Is interesting: $isInteresting');
        } else if (foundLocal) {
          debugPrint('🔄 Updated existing local image instead of adding to cloudImages: ID=$id');
        }
        
        debugPrint('🔍 Image update summary: Cloud=$foundInCloud, InProgress=$foundInProgress, Local=$foundLocal');
        debugPrint('🏁 CaptureProvider: onImageReceived - END (with description)');
        notifyListeners();
      } else {
        debugPrint('⚠️ No description found in image data');
        
        // Still store the image even without description, but with interesting flag
        Map<String, dynamic> newImage = {
          'id': id,
          'thumbnail_url': thumbnailUrl,
          'url': imageData['url'],
          'mime_type': imageData['mime_type'],
          'created_at': imageData['created_at'],
          'description': null,
          'is_interesting': isInteresting,
        };
        
        // **IMPROVED: Check for duplicates before adding**
        bool alreadyExists = cloudImages.any((img) => img['id'] == id);
        if (!alreadyExists) {
          cloudImages.add(newImage);
          debugPrint('📸 Added image without description to cloudImages: ID=$id, Is interesting: $isInteresting');
        } else {
          debugPrint('⚠️ Image without description already exists in cloudImages: ID=$id');
        }
        notifyListeners();
      }
    } else {
      debugPrint('❌ imageData is null');
    }
  }

  @override
  void onClearLiveImages(dynamic clearData) {
    debugPrint('🧹 CaptureProvider: onClearLiveImages received');
    debugPrint('🧹 Clear data: $clearData');
    
    if (clearData != null) {
      final conversationId = clearData['conversation_id'];
      final reason = clearData['reason'];
      final processedCount = clearData['processed_image_count'];
      
      debugPrint('🧹 Clearing live images: conversation=$conversationId, reason=$reason, count=$processedCount');
      
      // **UPDATED: Only clear images when a conversation is actually created**
      if (reason == 'conversation_created' || 
          reason == 'added_to_existing_conversation' ||
          reason == 'processed_into_new_conversation' || 
          reason == 'processed_to_existing_conversation') {
        debugPrint('✅ Conversation created - clearing live images');
        clearAllImages();
        clearInProgressConversation();
      } else {
        // For other reasons (like session ended, timeout, etc.), don't clear images
        debugPrint('⚪ Session ended but no conversation created - keeping live images');
        // Just clear the in-progress conversation state but keep images
        clearInProgressConversation();
      }
      
      debugPrint('✅ Processed clear_live_images notification');
    } else {
      debugPrint('❌ clearData is null');
    }
  }

  @override
  void onError(Object err) {
    debugPrint('CaptureProvider: WebSocket error: $err');
    // Handle WebSocket errors if needed.
    // Depending on the error, you might want to update the UI or try to reconnect.
  }

  // ─────────────────────────── event-stream from transcript socket ──────────────────────
  @override
  void onMessageEventReceived(ServerMessageEvent event) {
    switch (event.type) {
      case MessageEventType.conversationProcessingStarted:
        if (event.conversation == null) {
          debugPrint('Conversation data missing: $event');
          return;
        }
        conversationProvider?.addProcessingConversation(event.conversation!);
        _resetStateVariables();
        break;

      case MessageEventType.conversationCreated:
        if (event.conversation == null) {
          debugPrint('Conversation data missing: $event');
          return;
        }
        event.conversation!.isNew = true;
        conversationProvider?.removeProcessingConversation(event.conversation!.id);
        _processConversationCreated(event.conversation, event.messages ?? []);
        break;

      case MessageEventType.lastConversation:
        if (event.memoryId == null) {
          debugPrint('Conversation ID missing in last_memory event: $event');
          return;
        }
        _handleLastConvoEvent(event.memoryId!);
        break;

      case MessageEventType.translating:
        if (event.segments?.isEmpty ?? true) {
          debugPrint('No segments received in translating event: $event');
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
        debugPrint('New conversation creation failed: $event');
        // Handle conversation creation failure if needed
        break;

      case MessageEventType.newProcessingConversationCreated:
        debugPrint('New processing conversation created: $event');
        // Handle new processing conversation creation if needed
        break;

      case MessageEventType.processingConversationStatusChanged:
        debugPrint('Processing conversation status changed: $event');
        // Handle processing conversation status change if needed
        break;

      case MessageEventType.ping:
        debugPrint('Ping received: $event');
        // Handle ping messages (typically used for keep-alive)
        break;

      case MessageEventType.conversationBackwardSynced:
        debugPrint('Conversation backward synced: $event');
        // Handle conversation backward sync events if needed
        break;

      case MessageEventType.unknown:
        debugPrint('Unknown message event type: $event');
        // Handle unknown message events
        break;
    }
  }

  // ──────────────────────────── event helpers / processors ──────────────────────────────
  Future<void> _resetStateVariables() async {
    segments = [];
    hasTranscripts = false;
    clearAllImages();
    notifyListeners();
  }

  Future<void> _processConversationCreated(
      ServerConversation? conversation, List<ServerMessage> messages) async {
    if (conversation == null) return;
    conversationProvider?.upsertConversation(conversation);
    MixpanelManager().conversationCreated(conversation);
  }

  Future<void> _handleLastConvoEvent(String memoryId) async {
    final exists = conversationProvider?.conversations.any((c) => c.id == memoryId) ?? false;
    if (exists) return;

    final convo = await getConversationById(memoryId);
    if (convo != null) {
      debugPrint('Adding last conversation to list: $memoryId');
      conversationProvider?.upsertConversation(convo);
    } else {
      debugPrint('Failed to fetch last conversation: $memoryId');
    }
  }

  void _handleTranslationEvent(List<TranscriptSegment> translatedSegments) {
    try {
      if (translatedSegments.isEmpty) return;

      debugPrint('Received ${translatedSegments.length} translated segments');
      final remain = TranscriptSegment.updateSegments(segments, translatedSegments);
      if (remain.isNotEmpty) {
        debugPrint('Adding ${remain.length} new translated segments');
      }
      notifyListeners();
    } catch (e) {
      debugPrint('Error handling translation event: $e');
    }
  }

  // ─────────────────────────────── internet callback ────────────────────────────────────
  void onInternetStatusChanged(InternetStatus status) {
    debugPrint('[SocketService] Internet connection changed $status');
    _internetStatus = status;
    notifyListeners();
  }

  // ───────────────────────────── keep-alive watchdog ────────────────────────────────────
  void _startKeepAliveServices() {
    _keepAliveTimer?.cancel();
    _keepAliveTimer = Timer.periodic(const Duration(seconds: 15), (t) async {
      debugPrint('[Provider] keep alive...');
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
    });
  }

  // ═════════════════════════════════ device / mic streaming ═════════════════════════════
  Future<void> changeAudioRecordProfile({
    required BleAudioCodec audioCodec,
    int? sampleRate,
    bool isPhoneMic = false,
  }) async {
    if (isPhoneMic) {
      // For phone mic, only initiate WebSocket connection without device-specific setup
      await _initiateWebsocket(audioCodec: audioCodec, sampleRate: sampleRate);
    } else {
      // For devices, do full reset and setup
    await _resetState();
    await _initiateWebsocket(audioCodec: audioCodec, sampleRate: sampleRate);
    }
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
      debugPrint('📷 OpenGlass device detected - skipping WebSocket audio streaming setup');
      return;
    }

    final codec = await _getAudioCodec(_recordingDevice!.id);
    final language = SharedPreferencesUtil().hasSetPrimaryLanguage
        ? SharedPreferencesUtil().userPrimaryLanguage
        : 'multi';

    final socketMismatch = language != _socket?.language ||
        codec != _socket?.codec ||
        _socket?.state != SocketServiceState.connected;

    if (socketMismatch) {
      await _initiateWebsocket(audioCodec: codec, force: true);
    }
  }

  Future<void> _initiateDeviceAudioStreaming() async {
    if (_recordingDevice == null) return;
    
    // Skip audio streaming for OpenGlass devices - they only have camera, no microphone
    if (_recordingDevice!.type == DeviceType.openglass) {
      debugPrint('📷 OpenGlass device detected - skipping audio streaming setup (camera-only device)');
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
      final buttonState =
          ByteData.view(Uint8List.fromList(value.sublist(0, 4).reversed.toList()).buffer).getUint32(0);

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
  Future<void> streamRecording() async {
    await Permission.microphone.request();

    // set profile & socket first - specify this is for phone mic
    await changeAudioRecordProfile(audioCodec: BleAudioCodec.pcm16, sampleRate: 16000, isPhoneMic: true);

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

  Future<void> stopStreamRecording() async {
    await _cleanupCurrentState();
    ServiceManager.instance().mic.stop();
    await _socket?.stop(reason: 'stop stream recording');
    
    // Finalize the shared in-progress conversation
    await finalizeInProgressConversation();
  }

  Future<void> streamDeviceRecording({BtDevice? device}) async {
    if (device != null) _updateRecordingDevice(device);
    
    // Skip device recording setup for OpenGlass - it's camera-only and shouldn't affect audio
    if (device?.type == DeviceType.openglass) {
      debugPrint('📷 OpenGlass connected - setting up image capture only');
      
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
    
    // Use appropriate cleanup based on connected device type
    if (_recordingDevice?.type == DeviceType.openglass) {
      // For OpenGlass, only clean up audio streams but preserve image streams
    await _cleanupCurrentState();
    } else {
      // For regular devices, clean up everything
      await _cleanupDeviceState();
    }
    
    await _socket?.stop(reason: 'stop stream device recording');
    
    // Finalize the shared in-progress conversation
    await finalizeInProgressConversation();
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
      final buttonState =
          ByteData.view(Uint8List.fromList(value.sublist(0, 4).reversed.toList()).buffer).getUint32(0);

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
  int totalBytesReceived = 0;    // bytes already pulled
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
      debugPrint('No storage files found');
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
      debugPrint('SDCard bad state, offset > total');
      storageOffset = 0;
    }

    final codec = await _getAudioCodec(deviceId);
    sdCardSecondsTotal = totalBytes / codec.getFramesLengthInBytes() / codec.getFramesPerSecond();
    sdCardSecondsReceived =
        storageOffset / codec.getFramesLengthInBytes() / codec.getFramesPerSecond();

    // mark ready if >10s left
    if (totalBytes - storageOffset >
        10 * codec.getFramesLengthInBytes() * codec.getFramesPerSecond()) {
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
    debugPrint('CaptureProvider: onRecordProfileSettingChanged called');
    notifyListeners();
  }

  void clearTranscripts() {
    segments.clear();
    hasTranscripts = false;
    notifyListeners();
  }

  void addLocalImage(Map<String, dynamic> imageData) {
    // Check if local image already exists to prevent duplicates
    final imageId = imageData['id'] ?? 'unknown';
    bool alreadyExists = localImages.any((img) => img['id'] == imageId);
    
    if (alreadyExists) {
      debugPrint('Local image already exists, skipping duplicate: $imageId');
      return;
    }
    
    localImages.add(imageData);
    debugPrint('Added local image for immediate display: $imageId');
    debugPrint('Total local images: ${localImages.length}');
    notifyListeners(); // Trigger UI update immediately
  }
  
  void clearLocalImages() {
    localImages.clear();
    notifyListeners();
    debugPrint('🧹 Cleared all local images');
  }
  
  void clearCloudImages() {
    cloudImages.clear();
    notifyListeners();
  }
  
  void clearAllImages() {
    localImages.clear();
    cloudImages.clear();
    notifyListeners();
  }
  
  // Get all images (local + cloud) for display
  List<Map<String, dynamic>> get allImages {
    List<Map<String, dynamic>> all = [];
    all.addAll(localImages);
    all.addAll(cloudImages);
    return all;
  }

  Future<void> forceProcessingCurrentConversation() async {
    debugPrint('CaptureProvider: forceProcessingCurrentConversation called');
    
    // If we have captured images, upload them before processing the conversation
    if (allImages.isNotEmpty) {
      debugPrint('🖼️ Found ${allImages.length} captured images to include in conversation');
      
      try {
        // Send captured images to backend for processing
        await _uploadCapturedImagesForConversation();
        
        // Wait a bit for the backend to process the images
        await Future.delayed(Duration(seconds: 1));
        
      } catch (e) {
        debugPrint('❌ Error uploading captured images: $e');
        // Continue with conversation processing even if image upload fails
      }
    }
    
    // Force stop the current socket connection to trigger conversation processing
    await _socket?.stop(reason: 'force processing conversation');
    debugPrint('CaptureProvider: forceProcessingCurrentConversation - socket stopped');
    notifyListeners();
  }
  
  Future<void> _uploadCapturedImagesForConversation() async {
    if (allImages.isEmpty) return;
    
    final String uid = SharedPreferencesUtil().uid;
    if (uid.isEmpty) {
      debugPrint('❌ No user ID available for image upload');
      return;
    }
    
    debugPrint('📤 Uploading ${allImages.length} captured images for conversation processing...');
    
    try {
      final dio = Dio();
      final String baseUrl = Env.apiBaseUrl!;
      
      // Prepare multipart form data
      FormData formData = FormData();
      
      for (int i = 0; i < allImages.length; i++) {
        final image = allImages[i];
        final isLocalImage = image['type'] != 'cloud';
        
        if (isLocalImage && image['data'] != null) {
          // For local images, create a multipart file from the bytes
          final imageData = image['data'] as Uint8List;
          final String filename = 'openglass_image_${DateTime.now().millisecondsSinceEpoch}_$i.jpg';
          
          formData.files.add(MapEntry(
            'files',
            MultipartFile.fromBytes(
              imageData,
              filename: filename,
              contentType: MediaType('image', 'jpeg'),
            ),
          ));
          
          debugPrint('📸 Added local image $i: $filename (${imageData.length} bytes)');
        }
        // Cloud images are already uploaded, so we skip them here
        // They will be included via the existing WebSocket flow
      }
      
      if (formData.files.isEmpty) {
        debugPrint('ℹ️ No local images to upload (all are cloud images)');
        return;
      }
      
      // Upload to the files endpoint
      final response = await dio.post(
        '${baseUrl}v2/files',
        data: formData,
        options: Options(
          headers: {
            'Authorization': 'Bearer ${SharedPreferencesUtil().authToken}',
            'Content-Type': 'multipart/form-data',
          },
        ),
      );
      
      if (response.statusCode == 200) {
        debugPrint('✅ Successfully uploaded ${formData.files.length} images for conversation processing');
        
        // Clear local images since they're now uploaded
        clearLocalImages();
        
      } else {
        debugPrint('❌ Failed to upload images: ${response.statusCode} - ${response.data}');
      }
      
    } catch (e) {
      debugPrint('❌ Error uploading captured images: $e');
      rethrow;
    }
  }

  // ─────────────────────────── Shared In-Progress Conversation Management ──────────────────────────
  void startInProgressConversation() {
    if (_hasActiveConversation) return;
    
    _inProgressConversationId = 'in_progress_${DateTime.now().millisecondsSinceEpoch}';
    _conversationStartedAt = DateTime.now();
    _inProgressImages.clear();
    _inProgressSegments.clear();
    _hasActiveConversation = true;
    
    debugPrint('🎬 Started shared in-progress conversation: $_inProgressConversationId');
    notifyListeners();
  }
  
  void addImageToInProgressConversation(Map<String, dynamic> imageData) {
    if (!_hasActiveConversation) {
      startInProgressConversation();
    }
    
    // Check for duplicates
    bool alreadyExists = _inProgressImages.any((img) => 
      img['id'] == imageData['id'] || 
      (img['thumbnail_url'] == imageData['thumbnail_url'] && 
       imageData['thumbnail_url'] != null && 
       imageData['thumbnail_url'].toString().isNotEmpty)
    );
    
    if (!alreadyExists) {
      _inProgressImages.add(imageData);
      debugPrint('📸 Added image to in-progress conversation: ${imageData['id']} (Total: ${_inProgressImages.length})');
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
    
    debugPrint('🎙️ Added ${remain.length} segments to in-progress conversation (Total: ${_inProgressSegments.length})');
    notifyListeners();
  }
  
  Future<void> finalizeInProgressConversation() async {
    if (!_hasActiveConversation) return;
    
    debugPrint('🏁 Finalizing in-progress conversation: $_inProgressConversationId');
    debugPrint('   Segments: ${_inProgressSegments.length}');
    debugPrint('   Images: ${_inProgressImages.length}');
    
    // If we have captured images, upload them before finalizing
    if (_inProgressImages.isNotEmpty) {
      debugPrint('🖼️ Uploading ${_inProgressImages.length} captured images to conversation');
      try {
        await _uploadCapturedImagesForConversation();
        debugPrint('✅ Images uploaded successfully');
      } catch (e) {
        debugPrint('❌ Error uploading captured images: $e');
      }
    }
    
    // **CONSERVATIVE: Don't automatically clear live images when stopping**
    // Images will only be cleared when we receive explicit confirmation from backend
    // that a conversation was created (via onClearLiveImages callback)
    debugPrint('⚪ Keeping live images visible - they will be cleared only when conversation is confirmed');
    
    // Clear the in-progress state but keep images
    _hasActiveConversation = false;
    _inProgressConversationId = null;
    _conversationStartedAt = null;
    _inProgressImages.clear();
    _inProgressSegments.clear();
    
    debugPrint('✅ In-progress conversation finalized - images preserved');
    notifyListeners();
  }
  
  void clearInProgressConversation() {
    _hasActiveConversation = false;
    _inProgressConversationId = null;
    _conversationStartedAt = null;
    _inProgressImages.clear();
    _inProgressSegments.clear();
    debugPrint('🧹 Cleared in-progress conversation');
    notifyListeners();
  }

  // Add this method to set up OpenGlass image streaming separately from audio
  Future<void> startOpenGlassImageStreaming(String deviceId) async {
    // **DISABLED: Device provider already handles OpenGlass image streaming**
    // Avoiding duplicate listeners with different timestamps
    debugPrint('📷 OpenGlass image streaming handled by device provider - skipping duplicate setup');
    return;
    
    /* **COMMENTED OUT TO AVOID DUPLICATE LISTENERS**
    await _closeImageStream(); // Cancel any existing stream
    
    debugPrint('📷 Setting up OpenGlass image streaming for device: $deviceId');
    
    final connection = await ServiceManager.instance().device.ensureConnection(deviceId);
    if (connection == null) {
      debugPrint('❌ Failed to get connection for OpenGlass image streaming');
      return;
    }
    
    try {
      _imageStream = await connection.getImageListener(
        onImageReceived: (Uint8List imageData) async {
          debugPrint('📸 Received OpenGlass image: ${imageData.length} bytes');
          
          final timestamp = DateTime.now();
          final imageMap = {
            'id': 'openglass_${timestamp.millisecondsSinceEpoch}',
            'data': imageData,
            'timestamp': timestamp,
            'type': 'local',
            'description': '', // Will be filled by cloud processing
          };
          
          // Add to both local images and in-progress conversation
          addLocalImage(imageMap);
          addImageToInProgressConversation(imageMap);
          
          debugPrint('✅ Added OpenGlass image to conversation');
        },
      );
      
      debugPrint('✅ OpenGlass image streaming started successfully');
      
    } catch (e) {
      debugPrint('❌ Error setting up OpenGlass image streaming: $e');
    }
    */
  }
  
  Future<void> stopOpenGlassImageStreaming() async {
    await _closeImageStream();
    debugPrint('🛑 OpenGlass image streaming stopped');
  }

  // Add a method to explicitly clear images when conversation is confirmed
  void clearImagesAfterConversationCreated() {
    debugPrint('✅ Explicitly clearing images after conversation creation confirmation');
    clearAllImages();
    notifyListeners();
  }
}
