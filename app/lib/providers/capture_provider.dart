import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:flutter_provider_utilities/flutter_provider_utilities.dart';
import 'package:internet_connection_checker_plus/internet_connection_checker_plus.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:uuid/uuid.dart';

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
  StreamSubscription? _bleButtonStream;
  StreamSubscription? _storageStream;

  DateTime? _voiceCommandSession;
  final List<List<int>> _commandBytes = [];

  RecordingState recordingState = RecordingState.stop;

  // Local images for immediate display
  List<Map<String, dynamic>> localImages = [];
  
  // Cloud images received via WebSocket  
  List<Map<String, dynamic>> cloudImages = [];
  
  StreamSubscription? _speechProfileStream;
  Timer? _blinkTimer;

  // ───────────────────────────────── getters for widgets ────────────────────────────────
  StreamSubscription? get bleBytesStream => _bleBytesStream;
  StreamSubscription? get storageStream => _storageStream;

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
    debugPrint('connected device changed from ${_recordingDevice?.id} to ${device?.id}');
    _recordingDevice = device;
    notifyListeners();
  }

  void updateRecordingDevice(BtDevice? device) => _updateRecordingDevice(device);

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

    final remain = TranscriptSegment.updateSegments(segments, newSegments);
    TranscriptSegment.combineSegments(segments, remain);

    hasTranscripts = true;
    notifyListeners();
  }

  @override
  void onImageReceived(dynamic imageData) {
    debugPrint('CaptureProvider: onImageReceived - $imageData');
    if (imageData != null) {
      // Add cloud image data to the list
      cloudImages.add({
        'id': imageData['id'] ?? 'unknown',
        'thumbnail_url': imageData['thumbnail_url'],
        'mime_type': imageData['mime_type'] ?? 'image/jpeg',
        'created_at': DateTime.tryParse(imageData['created_at'] ?? '') ?? DateTime.now(),
        'type': 'cloud', // Mark as cloud image
      });
      debugPrint('Added cloud image: ${imageData['id']}');
      notifyListeners(); // Trigger UI update
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
  }) async {
    await _resetState();
    await _initiateWebsocket(audioCodec: audioCodec, sampleRate: sampleRate);
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
    notifyListeners();
  }

  Future<void> _ensureDeviceSocketConnection() async {
    if (_recordingDevice == null) return;

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

    // set profile & socket first
    await changeAudioRecordProfile(audioCodec: BleAudioCodec.pcm16, sampleRate: 16000);

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
  }

  Future<void> streamDeviceRecording({BtDevice? device}) async {
    if (device != null) _updateRecordingDevice(device);
    await _resetState();
  }

  Future<void> stopStreamDeviceRecording({bool cleanDevice = false}) async {
    if (cleanDevice) _updateRecordingDevice(null);
    await _cleanupCurrentState();
    await _socket?.stop(reason: 'stop stream device recording');
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
    localImages.add(imageData);
    debugPrint('Added local image for immediate display: ${imageData['id']}');
    notifyListeners(); // Trigger UI update immediately
  }
  
  void clearLocalImages() {
    localImages.clear();
    notifyListeners();
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
    // Force stop the current socket connection to trigger conversation processing
    await _socket?.stop(reason: 'force processing conversation');
    debugPrint('CaptureProvider: forceProcessingCurrentConversation - socket stopped');
    notifyListeners();
  }
}
