import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:flutter_provider_utilities/flutter_provider_utilities.dart';
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
import 'package:internet_connection_checker_plus/internet_connection_checker_plus.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:uuid/uuid.dart';

class CaptureProvider extends ChangeNotifier
    with MessageNotifierMixin
    implements ITransctipSegmentSocketServiceListener {
  ConversationProvider? conversationProvider;
  MessageProvider? messageProvider;
  TranscriptSegmentSocketService? _socket;
  SdCardSocketService sdCardSocket = SdCardSocketService();
  Timer? _keepAliveTimer;

  IWalService get _wal => ServiceManager.instance().wal;

  IDeviceService get _deviceService => ServiceManager.instance().device;
  bool _isWalSupported = false;

  bool get isWalSupported => _isWalSupported;

  StreamSubscription<InternetStatus>? _internetStatusListener;
  InternetStatus? _internetStatus;

  get internetStatus => _internetStatus;

  List<ServerMessageEvent> _transcriptionServiceStatuses = [];
  List<ServerMessageEvent> get transcriptionServiceStatuses => _transcriptionServiceStatuses;

  CaptureProvider() {
    _internetStatusListener = PureCore().internetConnection.onStatusChange.listen((InternetStatus status) {
      onInternetSatusChanged(status);
    });
  }

  void updateProviderInstances(ConversationProvider? cp, MessageProvider? p) {
    conversationProvider = cp;
    messageProvider = p;
    notifyListeners();
  }

  BtDevice? _recordingDevice;
  List<TranscriptSegment> segments = [];

  bool hasTranscripts = false;

  StreamSubscription? _bleBytesStream;

  get bleBytesStream => _bleBytesStream;

  StreamSubscription? _bleButtonStream;
  DateTime? _voiceCommandSession;
  List<List<int>> _commandBytes = [];

  StreamSubscription? _storageStream;

  get storageStream => _storageStream;

  RecordingState recordingState = RecordingState.stop;

  bool _transcriptServiceReady = false;

  bool get transcriptServiceReady => _transcriptServiceReady && _internetStatus == InternetStatus.connected;

  // having a connected device or using the phone's mic for recording
  bool get recordingDeviceServiceReady => _recordingDevice != null || recordingState == RecordingState.record;

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
    hasTranscripts = false;
    notifyListeners();
  }

  Future<void> onRecordProfileSettingChanged() async {
    await _resetState();
  }

  Future<void> changeAudioRecordProfile({
    required BleAudioCodec audioCodec,
    int? sampleRate,
  }) async {
    debugPrint("changeAudioRecordProfile");
    await _resetState();
    await _initiateWebsocket(audioCodec: audioCodec, sampleRate: sampleRate);
  }

  Future<void> _initiateWebsocket({
    required BleAudioCodec audioCodec,
    int? sampleRate,
    bool force = false,
  }) async {
    debugPrint('initiateWebsocket in capture_provider');

    BleAudioCodec codec = audioCodec;
    sampleRate ??= (codec.isOpusSupported() ? 16000 : 8000);

    debugPrint('is ws null: ${_socket == null}');

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
    await _ensureDeviceSocketConnection();
    await _initiateDeviceAudioStreaming();
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

    notifyListeners();
  }

  void clearTranscripts() {
    segments = [];
    hasTranscripts = false;
    notifyListeners();
  }

  Future _closeBleStream() async {
    await _bleBytesStream?.cancel();
    notifyListeners();
  }

  @override
  void dispose() {
    _bleBytesStream?.cancel();
    _socket?.unsubscribe(this);
    _keepAliveTimer?.cancel();
    _internetStatusListener?.cancel();
    super.dispose();
  }

  void updateRecordingState(RecordingState state) {
    recordingState = state;
    notifyListeners();
  }

  streamRecording() async {
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
    await _socket?.stop(reason: 'stop stream recording');
  }

  Future streamDeviceRecording({BtDevice? device}) async {
    debugPrint("streamDeviceRecording $device");
    if (device != null) _updateRecordingDevice(device);

    await _resetState();
  }

  Future stopStreamDeviceRecording({bool cleanDevice = false}) async {
    if (cleanDevice) {
      _updateRecordingDevice(null);
    }
    await _cleanupCurrentState();
    await _socket?.stop(reason: 'stop stream device recording');
  }

  // Socket handling

  @override
  void onClosed() {
    _transcriptionServiceStatuses = [];
    _transcriptServiceReady = false;
    debugPrint('[Provider] Socket is closed');

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
    });
  }

  @override
  void onError(Object err) {
    _transcriptionServiceStatuses = [];
    _transcriptServiceReady = false;
    debugPrint('err: $err');
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
    var convo = convos.isNotEmpty ? convos.first : null;
    if (convo != null) {
      segments = convo.transcriptSegments;
    } else {
      segments = [];
    }
    setHasTranscripts(segments.isNotEmpty);
    notifyListeners();
  }

  @override
  void onMessageEventReceived(ServerMessageEvent event) {
    if (event.type == MessageEventType.conversationProcessingStarted) {
      if (event.conversation == null) {
        debugPrint("Conversation data not received in event. Content is: $event");
        return;
      }
      conversationProvider!.addProcessingConversation(event.conversation!);
      _resetStateVariables();
      return;
    }

    if (event.type == MessageEventType.conversationCreated) {
      if (event.conversation == null) {
        debugPrint("Conversation data not received in event. Content is: $event");
        return;
      }
      event.conversation!.isNew = true;
      conversationProvider!.removeProcessingConversation(event.conversation!.id);
      _processConversationCreated(event.conversation, event.messages ?? []);
      return;
    }

    if (event.type == MessageEventType.lastConversation) {
      if (event.memoryId == null) {
        debugPrint("Conversation ID not received in last_memory event. Content is: $event");
        return;
      }
      _handleLastConvoEvent(event.memoryId!);
      return;
    }

    if (event.type == MessageEventType.translating) {
      if (event.segments == null || event.segments?.isEmpty == true) {
        debugPrint("No segments received in translating event. Content is: $event");
        return;
      }
      _handleTranslationEvent(event.segments!);
      return;
    }

    if (event.type == MessageEventType.serviceStatus) {
      if (event.status == null) {
        return;
      }

      _transcriptionServiceStatuses.add(event);
      _transcriptionServiceStatuses = List.from(_transcriptionServiceStatuses);
      notifyListeners();
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
    var remainSegments = TranscriptSegment.updateSegments(segments, newSegments);
    TranscriptSegment.combineSegments(segments, remainSegments);

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
}
