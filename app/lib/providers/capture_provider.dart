import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:collection/collection.dart';
import 'package:flutter/material.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:flutter_provider_utilities/flutter_provider_utilities.dart';
import 'package:friend_private/backend/http/api/memories.dart';
import 'package:friend_private/backend/http/api/processing_memories.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/bt_device.dart';
import 'package:friend_private/backend/schema/geolocation.dart';
import 'package:friend_private/backend/schema/memory.dart';
import 'package:friend_private/backend/schema/message.dart';
import 'package:friend_private/backend/schema/message_event.dart';
import 'package:friend_private/backend/schema/structured.dart';
import 'package:friend_private/backend/schema/transcript_segment.dart';
import 'package:friend_private/providers/memory_provider.dart';
import 'package:friend_private/providers/message_provider.dart';
import 'package:friend_private/services/services.dart';
import 'package:friend_private/services/sockets/transcription_connection.dart';
import 'package:friend_private/utils/analytics/growthbook.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/utils/audio/wav_bytes.dart';
import 'package:friend_private/utils/enums.dart';
import 'package:friend_private/utils/features/calendar.dart';
import 'package:friend_private/utils/logger.dart';
import 'package:friend_private/utils/memories/integrations.dart';
import 'package:friend_private/utils/memories/process.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:uuid/uuid.dart';

class CaptureProvider extends ChangeNotifier
    with MessageNotifierMixin
    implements ITransctipSegmentSocketServiceListener {
  MemoryProvider? memoryProvider;
  MessageProvider? messageProvider;
  TranscripSegmentSocketService? _socket;

  Timer? _keepAliveTimer;

  void updateProviderInstances(MemoryProvider? mp, MessageProvider? p) {
    memoryProvider = mp;
    messageProvider = p;
    notifyListeners();
  }

  BTDeviceStruct? _recordingDevice;
  List<TranscriptSegment> segments = [];
  Geolocation? geolocation;

  bool hasTranscripts = false;
  bool memoryCreating = false;
  bool audioBytesConnected = false;

  StreamSubscription? _bleBytesStream;

  get bleBytesStream => _bleBytesStream;

  StreamSubscription? _storageStream;

  get storageStream => _storageStream;

  RecordingState recordingState = RecordingState.stop;

  bool _transcriptServiceReady = false;

  bool get transcriptServiceReady => _transcriptServiceReady;

  bool get recordingDeviceServiceReady => _recordingDevice != null || recordingState == RecordingState.record;

  // -----------------------
  // Memory creation variables
  String conversationId = const Uuid().v4();
  int elapsedSeconds = 0;
  List<int> currentStorageFiles = <int>[];
  StorageBytesUtil storageUtil = StorageBytesUtil();

  // -----------------------

  String? processingMemoryId;
  ServerProcessingMemory? capturingProcessingMemory;
  Timer? _processingMemoryWatchTimer;

  String dateTimeStorageString = "";

  void setHasTranscripts(bool value) {
    hasTranscripts = value;
    notifyListeners();
  }

  void setMemoryCreating(bool value) {
    debugPrint('set memory creating $value');
    memoryCreating = value;
    notifyListeners();
  }

  void setGeolocation(Geolocation? value) {
    geolocation = value;

    // Update processing memory on geolocation
    if (processingMemoryId != null) {
      _updateProcessingMemory();
    }

    notifyListeners();
  }

  void setAudioBytesConnected(bool value) {
    audioBytesConnected = value;
    notifyListeners();
  }

  void _updateRecordingDevice(BTDeviceStruct? device) {
    debugPrint('connected device changed from ${_recordingDevice?.id} to ${device?.id}');
    _recordingDevice = device;
    notifyListeners();
  }

  void _onMemoryCreating() {
    setMemoryCreating(true);
  }

  Future<void> _updateProcessingMemory() async {
    if (processingMemoryId == null) {
      return;
    }

    debugPrint("update processing memory");
    // Update info likes geolocation
    UpdateProcessingMemoryResponse? result = await updateProcessingMemoryServer(
      id: processingMemoryId!,
      geolocation: geolocation,
      emotionalFeedback: GrowthbookUtil().isOmiFeedbackEnabled(),
    );
    if (result?.result == null) {
      debugPrint("Can not update processing memory, result null");
    }
  }

  Future<void> _onProcessingMemoryStatusChanged(String processingMemoryId, ServerProcessingMemoryStatus status) async {
    if (capturingProcessingMemory == null || capturingProcessingMemory?.id != processingMemoryId) {
      debugPrint("Warn: Didn't track processing memory yet $processingMemoryId");
    }

    ProcessingMemoryResponse? result = await fetchProcessingMemoryServer(id: processingMemoryId);
    if (result?.result == null) {
      debugPrint("Can not fetch processing memory, result null");
      return;
    }
    var pm = result!.result!;
    if (status == ServerProcessingMemoryStatus.processing) {
      memoryProvider?.onNewProcessingMemory(pm);
      return;
    }
    if (status == ServerProcessingMemoryStatus.done) {
      memoryProvider?.onProcessingMemoryDone(pm);
      return;
    }
  }

  Future<void> _onProcessingMemoryCreated(String processingMemoryId) async {
    this.processingMemoryId = processingMemoryId;

    // Fetch and watch capturing status
    ProcessingMemoryResponse? result = await fetchProcessingMemoryServer(
      id: processingMemoryId,
    );
    if (result?.result == null) {
      debugPrint("Can not fetch processing memory, result null");
    }
    _setCapturingProcessingMemory(result?.result);

    // Set pre-segments
    if (capturingProcessingMemory != null && (capturingProcessingMemory?.transcriptSegments ?? []).isNotEmpty) {
      segments = capturingProcessingMemory!.transcriptSegments;
      setHasTranscripts(segments.isNotEmpty);
    }

    // Notify capturing
    if (capturingProcessingMemory != null) {
      memoryProvider?.onNewCapturingMemory(capturingProcessingMemory!);
    }

    // Update processing memory
    _updateProcessingMemory();
  }

  void _trackCapturingProcessingMemory() {
    if (capturingProcessingMemory == null) {
      return;
    }

    var pm = capturingProcessingMemory!;

    var delayMs = pm.capturingTo != null
        ? pm.capturingTo!.millisecondsSinceEpoch - DateTime.now().millisecondsSinceEpoch
        : 2 * 60 * 1000; // 2m
    if (delayMs > 0) {
      _processingMemoryWatchTimer?.cancel();
      _processingMemoryWatchTimer = Timer(Duration(milliseconds: delayMs), () async {
        ProcessingMemoryResponse? result = await fetchProcessingMemoryServer(id: pm.id);
        if (result?.result == null) {
          debugPrint("Can not fetch processing memory, result null");
          return;
        }

        _setCapturingProcessingMemory(result?.result);
        if (capturingProcessingMemory == null) {
          // Force clean
          _clean();
        }
      });
    }
  }

  void _setCapturingProcessingMemory(ServerProcessingMemory? pm) {
    if (pm != null &&
        pm.status == ServerProcessingMemoryStatus.capturing &&
        pm.capturingTo != null &&
        pm.capturingTo!.isAfter(DateTime.now())) {
      capturingProcessingMemory = pm;
      _trackCapturingProcessingMemory();

      notifyListeners();
      return;
    }

    capturingProcessingMemory = null;
    _processingMemoryWatchTimer?.cancel();

    notifyListeners();
  }

  Future<void> _onMemoryCreated(ServerMessageEvent event) async {
    if (event.memory == null) {
      debugPrint("Memory is not found, processing memory ${event.processingMemoryId}");
      return;
    }
    _processOnMemoryCreated(event.memory, event.messages ?? []);
  }

  void _onMemoryCreateFailed() {
    _processOnMemoryCreated(null, []); // force failed
  }

  Future<void> _processOnMemoryCreated(ServerMemory? memory, List<ServerMessage> messages) async {
    if (memory == null) {
      return;
    }
    await processMemoryContent(
      memory: memory,
      messages: messages,
      sendMessageToChat: (v) {
        messageProvider?.addMessage(v);
      },
    );

    // use memory provider to add memory
    MixpanelManager().memoryCreated(memory);
    memoryProvider?.upsertMemory(memory);
    if (memoryProvider?.memories.isEmpty ?? false) {
      memoryProvider?.getMoreMemoriesFromServer();
    }

    _cleanNew();

    // Notify
    setMemoryCreating(false);
    setHasTranscripts(false);
    _handleCalendarCreation(memory);
    notifyListeners();
    return;
  }

  Future<void> createMemory() async {
    if (processingMemoryId != null) {
      setMemoryCreating(true);

      // Clean to force close socket to create new memory
      _cleanNew();

      // Notify
      setMemoryCreating(false);
      setHasTranscripts(false);
      notifyListeners();
      return;
    }
  }

  Future _clean() async {
    segments = [];

    elapsedSeconds = 0;

    conversationId = const Uuid().v4();

    processingMemoryId = null;
    capturingProcessingMemory = null;
    _processingMemoryWatchTimer?.cancel();
  }

  Future _cleanNew() async {
    _clean();

    // Create new socket session
    // Warn: should have a better solution to keep the socket alived
    debugPrint("_cleanNew");
    await _initiateWebsocket(force: true);
  }

  _handleCalendarCreation(ServerMemory memory) {
    if (!SharedPreferencesUtil().calendarEnabled) return;
    if (SharedPreferencesUtil().calendarType != 'auto') return;

    List<Event> events = memory.structured.events;
    if (events.isEmpty) return;

    List<int> indexes = events.mapIndexed((index, e) => index).toList();
    setMemoryEventsState(memory.id, indexes, indexes.map((_) => true).toList());
    for (var i = 0; i < events.length; i++) {
      if (events[i].created) continue;
      events[i].created = true;
      CalendarUtil().createEvent(
        events[i].title,
        events[i].startsAt,
        events[i].duration,
        description: events[i].description,
      );
    }
  }

  Future<void> onRecordProfileSettingChanged() async {
    await _resetState(restartBytesProcessing: true);
  }

  Future<void> changeAudioRecordProfile([
    BleAudioCodec? audioCodec,
    int? sampleRate,
  ]) async {
    debugPrint("changeAudioRecordProfile");
    await _resetState(restartBytesProcessing: true);
    await _initiateWebsocket(audioCodec: audioCodec, sampleRate: sampleRate);
  }

  Future<void> _initiateWebsocket({
    BleAudioCodec? audioCodec,
    int? sampleRate,
    bool force = false,
  }) async {
    debugPrint('initiateWebsocket in capture_provider');

    BleAudioCodec codec = audioCodec ?? SharedPreferencesUtil().deviceCodec;
    sampleRate ??= (codec == BleAudioCodec.opus ? 16000 : 8000);

    debugPrint('is ws null: ${_socket == null}');

    // Get memory socket
    _socket = await ServiceManager.instance().socket.memory(codec: codec, sampleRate: sampleRate, force: force);
    if (_socket == null) {
      throw Exception("Can not create new memory socket");
    }
    _socket?.subscribe(this, this);
    _transcriptServiceReady = true;
  }

  Future streamAudioToWs(String id, BleAudioCodec codec) async {
    debugPrint('streamAudioToWs in capture_provider');
    if (_bleBytesStream != null) {
      _bleBytesStream?.cancel();
    }
    _bleBytesStream = await _getBleAudioBytesListener(
      id,
      onAudioBytesReceived: (List<int> value) {
        if (value.isEmpty) return;
        if (_socket?.state == SocketServiceState.connected) {
          final trimmedValue = value.sublist(3);
          _socket?.send(trimmedValue);
        }
      },
    );
    setAudioBytesConnected(true);
    notifyListeners();
  }

  Future sendStorage(String id) async {
    storageUtil = StorageBytesUtil();

    if (_storageStream != null) {
      _storageStream?.cancel();
    }
    _storageStream = await _getBleStorageBytesListener(id, onStorageBytesReceived: (List<int> value) async {
      if (value.isEmpty) return;

      storageUtil.storeFrameStoragePacket(value);
      if (value.length == 1) {
        //result codes i guess
        debugPrint('returned $value');
        if (value[0] == 0) {
          //valid command
          DateTime storageStartTime = DateTime.now();
          dateTimeStorageString = storageStartTime.toIso8601String();
          debugPrint('good to go');
        } else if (value[0] == 3) {
          debugPrint('bad file size. finishing...');
        } else if (value[0] == 4) {
          //file size is zero.
          debugPrint('file size is zero. going to next one....');
          getFileFromDevice(storageUtil.getFileNum() + 1);
        } else if (value[0] == 100) {
          //valid end command
          debugPrint('done. sending to backend....trying to dl more');
          File storageFile = (await storageUtil.createWavFile(removeLastNSeconds: 0)).item1;
          List<ServerMemory> result = await sendStorageToBackend(storageFile, dateTimeStorageString);
          for (ServerMemory memory in result) {
            memoryProvider?.addMemory(memory);
          }
          storageUtil.clearAudioBytes();
          //clear the file to indicate completion
          clearFileFromDevice(storageUtil.getFileNum());
          getFileFromDevice(storageUtil.getFileNum() + 1);
        } else {
          //bad bit
          debugPrint('Error bit returned');
        }
      }
    });

    getFileFromDevice(storageUtil.getFileNum());
    //  notifyListeners();
  }

  Future getFileFromDevice(int fileNum) async {
    storageUtil.fileNum = fileNum;
    int command = 0;
    _writeToStorage(_recordingDevice!.id, storageUtil.fileNum, command);
  }

  Future clearFileFromDevice(int fileNum) async {
    storageUtil.fileNum = fileNum;
    int command = 1;
    _writeToStorage(_recordingDevice!.id, storageUtil.fileNum, command);
  }

  void clearTranscripts() {
    segments = [];
    setHasTranscripts(false);
    notifyListeners();
  }

  Future resetForSpeechProfile() async {
    closeBleStream();
    await _socket?.stop(reason: 'reset for speech profile');
    setAudioBytesConnected(false);
    notifyListeners();
  }

  Future<void> _resetState({
    bool restartBytesProcessing = true,
  }) async {
    debugPrint('resetState: restartBytesProcessing=$restartBytesProcessing');

    _cleanupCurrentState();
    await _recheckCodecChange();
    await _ensureSocketConnection(force: true);
    await _initiateFriendAudioStreaming();
    // TODO: Commenting this for now as DevKit 2 is not yet used in production
    // await initiateStorageBytesStreaming();
    notifyListeners();
  }

  void _cleanupCurrentState() {
    closeBleStream();
    cancelMemoryCreationTimer();
    setAudioBytesConnected(false);
  }

  // TODO: use connection directly
  Future<BleAudioCodec> _getAudioCodec(String deviceId) async {
    var connection = await ServiceManager.instance().device.ensureConnection(deviceId);
    if (connection == null) {
      return BleAudioCodec.pcm8;
    }
    return connection.getAudioCodec();
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

  Future<bool> _writeToStorage(String deviceId, int numFile, int command) async {
    var connection = await ServiceManager.instance().device.ensureConnection(deviceId);
    if (connection == null) {
      return Future.value(false);
    }
    return connection.writeToStorage(numFile, command);
  }

  Future<List<int>> _getStorageList(String deviceId) async {
    var connection = await ServiceManager.instance().device.ensureConnection(deviceId);
    if (connection == null) {
      return [];
    }
    return connection.getStorageList();
  }

  Future<bool> _recheckCodecChange() async {
    if (_recordingDevice != null) {
      BleAudioCodec newCodec = await _getAudioCodec(_recordingDevice!.id);
      if (SharedPreferencesUtil().deviceCodec != newCodec) {
        debugPrint('Device codec changed from ${SharedPreferencesUtil().deviceCodec} to $newCodec');
        await SharedPreferencesUtil().setDeviceCodec(newCodec);
        return true;
      }
    }
    return false;
  }

  Future<void> _ensureSocketConnection({bool force = false}) async {
    debugPrint("_ensureSocketConnection");
    var codec = SharedPreferencesUtil().deviceCodec;
    if (force || (codec != _socket?.codec || _socket?.state != SocketServiceState.connected)) {
      await _socket?.stop(reason: 'reset state, force $force');
      await _initiateWebsocket(force: force);
    }
  }

  Future<void> _initiateFriendAudioStreaming() async {
    if (_recordingDevice == null) return;

    BleAudioCodec codec = await _getAudioCodec(_recordingDevice!.id);
    if (SharedPreferencesUtil().deviceCodec != codec) {
      debugPrint('Device codec changed from ${SharedPreferencesUtil().deviceCodec} to $codec');
      SharedPreferencesUtil().deviceCodec = codec;
      notifyInfo('FIM_CHANGE');
      await _ensureSocketConnection();
    }

    // Why is the _recordingDevice null at this point?
    if (!audioBytesConnected) {
      if (_recordingDevice != null) {
        await streamAudioToWs(_recordingDevice!.id, codec);
      } else {
        // Is the app in foreground when this happens?
        Logger.handle(Exception('Device Not Connected'), StackTrace.current,
            message: 'Device Not Connected. Please make sure the device is turned on and nearby.');
      }
    }

    notifyListeners();
  }

  Future<void> initiateStorageBytesStreaming() async {
    debugPrint('initiateStorageBytesStreaming');
    if (_recordingDevice == null) return;
    currentStorageFiles = await _getStorageList(_recordingDevice!.id);
    debugPrint('Storage files: $currentStorageFiles');
    await sendStorage(_recordingDevice!.id);
    notifyListeners();
  }

  void closeBleStream() {
    _bleBytesStream?.cancel();
    notifyListeners();
  }

  void cancelMemoryCreationTimer() {
    notifyListeners();
  }

  @override
  void dispose() {
    _bleBytesStream?.cancel();
    _socket?.unsubscribe(this);
    _keepAliveTimer?.cancel();
    _processingMemoryWatchTimer?.cancel();
    super.dispose();
  }

  void updateRecordingState(RecordingState state) {
    recordingState = state;
    notifyListeners();
  }

  streamRecording() async {
    await Permission.microphone.request();

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

  stopStreamRecording() {
    ServiceManager.instance().mic.stop();
  }

  Future streamDeviceRecording({
    BTDeviceStruct? device,
    bool restartBytesProcessing = true,
  }) async {
    debugPrint("streamDeviceRecording $device $restartBytesProcessing");
    if (device != null) {
      _updateRecordingDevice(device);
    }

    await _resetState(
      restartBytesProcessing: restartBytesProcessing,
    );
  }

  Future stopStreamDeviceRecording({bool cleanDevice = false}) async {
    if (cleanDevice) {
      _updateRecordingDevice(null);
    }
    _cleanupCurrentState();
    await _socket?.stop(reason: 'stop stream device recording');
    // await _handleMemoryCreation(false);
  }

  // Socket handling

  @override
  void onClosed() {
    _transcriptServiceReady = false;
    debugPrint('[Provider] Socket is closed');

    // Wait reconnect
    if (capturingProcessingMemory == null) {
      _clean();
      setMemoryCreating(false);
      setHasTranscripts(false);
      notifyListeners();
    }

    // Keep alive
    _startKeepAliveServices();
  }

  void _startKeepAliveServices() {
    if (_recordingDevice != null && _socket?.state != SocketServiceState.connected) {
      _keepAliveTimer?.cancel();
      _keepAliveTimer = Timer.periodic(const Duration(seconds: 15), (t) async {
        debugPrint("[Provider] keep alive...");

        if (_recordingDevice == null || _socket?.state == SocketServiceState.connected) {
          t.cancel();
          return;
        }

        await _initiateWebsocket();
      });
    }
  }

  @override
  void onError(Object err) {
    _transcriptServiceReady = false;
    debugPrint('err: $err');
    notifyListeners();
    _startKeepAliveServices();
  }

  @override
  void onMessageEventReceived(ServerMessageEvent event) {
    if (event.type == MessageEventType.newMemoryCreating) {
      _onMemoryCreating();
      return;
    }

    if (event.type == MessageEventType.newMemoryCreated) {
      _onMemoryCreated(event);
      return;
    }

    if (event.type == MessageEventType.newMemoryCreateFailed) {
      _onMemoryCreateFailed();
      return;
    }

    if (event.type == MessageEventType.newProcessingMemoryCreated) {
      if (event.processingMemoryId == null) {
        debugPrint("New processing memory created message event is invalid");
        return;
      }
      _onProcessingMemoryCreated(event.processingMemoryId!);
      return;
    }

    if (event.type == MessageEventType.processingMemoryStatusChanged) {
      if (event.processingMemoryId == null || event.processingMemoryStatus == null) {
        debugPrint("Processing memory message event is invalid");
        return;
      }
      _onProcessingMemoryStatusChanged(event.processingMemoryId!, event.processingMemoryStatus!);
      return;
    }
  }

  @override
  void onSegmentReceived(List<TranscriptSegment> newSegments) {
    if (newSegments.isEmpty) return;

    if (segments.isEmpty) {
      debugPrint('newSegments: ${newSegments.last}');
      FlutterForegroundTask.sendDataToTask(jsonEncode({'location': true}));
    }
    TranscriptSegment.combineSegments(segments, newSegments);
    triggerTranscriptSegmentReceivedEvents(newSegments, conversationId, sendMessageToChat: (v) {
      messageProvider?.addMessage(v);
    });
    setHasTranscripts(true);
    notifyListeners();
  }
}
