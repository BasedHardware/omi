import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';

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
import 'package:friend_private/pages/capture/logic/openglass_mixin.dart';
import 'package:friend_private/providers/memory_provider.dart';
import 'package:friend_private/providers/message_provider.dart';
import 'package:friend_private/providers/websocket_provider.dart';
import 'package:friend_private/services/services.dart';
import 'package:friend_private/utils/analytics/growthbook.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/utils/audio/wav_bytes.dart';
import 'package:friend_private/utils/ble/communication.dart';
import 'package:friend_private/utils/enums.dart';
import 'package:friend_private/utils/features/calendar.dart';
import 'package:friend_private/utils/logger.dart';
import 'package:friend_private/utils/memories/integrations.dart';
import 'package:friend_private/utils/memories/process.dart';
import 'package:friend_private/utils/websockets.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:uuid/uuid.dart';

class CaptureProvider extends ChangeNotifier with OpenGlassMixin, MessageNotifierMixin {
  MemoryProvider? memoryProvider;
  MessageProvider? messageProvider;
  WebSocketProvider? webSocketProvider;

  void updateProviderInstances(MemoryProvider? mp, MessageProvider? p, WebSocketProvider? wsProvider) {
    memoryProvider = mp;
    messageProvider = p;
    webSocketProvider = wsProvider;
    notifyListeners();
  }

  BTDeviceStruct? connectedDevice;
  bool isGlasses = false;

  List<TranscriptSegment> segments = [];
  Geolocation? geolocation;

  bool hasTranscripts = false;
  bool memoryCreating = false;
  bool audioBytesConnected = false;

  static const quietSecondsForMemoryCreation = 120;

  StreamSubscription? _bleBytesStream;

  get bleBytesStream => _bleBytesStream;

  StreamSubscription? _storageStream;

  get storageStream => _storageStream;

  RecordingState recordingState = RecordingState.stop;

  // -----------------------
  // Memory creation variables
  double? streamStartedAtSecond;
  DateTime? firstStreamReceivedAt;
  int? secondsMissedOnReconnect;
  WavBytesUtil? audioStorage;
  String conversationId = const Uuid().v4();
  int elapsedSeconds = 0;
  List<int> currentStorageFiles = <int>[];
  StorageBytesUtil storageUtil = StorageBytesUtil();
  Timer? _memoryCreationTimer;

  // -----------------------

  String? processingMemoryId;

  bool resetStateAlreadyCalled = false;
  String dateTimeStorageString = "";

  void setResetStateAlreadyCalled(bool value) {
    resetStateAlreadyCalled = value;
    notifyListeners();
  }

  void setHasTranscripts(bool value) {
    hasTranscripts = value;
    notifyListeners();
  }

  void setMemoryCreating(bool value) {
    print('set memory creating ${value}');
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

  void updateConnectedDevice(BTDeviceStruct? device) {
    debugPrint('connected device changed from ${connectedDevice?.id} to ${device?.id}');
    connectedDevice = device;
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
      print("Can not update processing memory, result null");
    }
  }

  Future<void> _onProcessingMemoryCreated(String processingMemoryId) async {
    this.processingMemoryId = processingMemoryId;
    _updateProcessingMemory();
  }

  Future<void> _onMemoryCreated(ServerMessageEvent event) async {
    if (event.memory == null) {
      print("Memory is not found, processing memory ${event.processingMemoryId}");
      return;
    }
    _processOnMemoryCreated(event.memory, event.messages ?? []);
  }

  void _onMemoryCreateFailed() {
    _processOnMemoryCreated(null, []); // force failed
  }

  Future<void> _onMemoryPostProcessSuccess(String memoryId) async {
    var memory = await getMemoryById(memoryId);
    if (memory == null) {
      print("Memory is not found $memoryId");
      return;
    }

    memoryProvider?.updateMemory(memory);
  }

  Future<void> _onMemoryPostProcessFailed(String memoryId) async {
    var memory = await getMemoryById(memoryId);
    if (memory == null) {
      print("Memory is not found $memoryId");
      return;
    }

    memoryProvider?.updateMemory(memory);
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
    memoryProvider?.addMemory(memory);
    if (memoryProvider?.memories.isEmpty ?? false) {
      memoryProvider?.getMoreMemoriesFromServer();
    }

    _cleanNew();

    // Notify
    setMemoryCreating(false);
    setHasTranscripts(false);
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

    // photos
    if (photos.isNotEmpty) {
      await _createPhotoCharacteristicMemory();
    }

    return;
  }

  Future<bool?> _createPhotoCharacteristicMemory() async {
    debugPrint('_createMemory');

    if (memoryCreating) return null;

    if (photos.isEmpty) return false;

    setMemoryCreating(true);

    // Create new memory
    ServerMemory? memory = await processTranscriptContent(
      geolocation: geolocation,
      photos: photos,
      sendMessageToChat: (v) {
        messageProvider?.addMessage(v);
      },
      triggerIntegrations: true,
      language: SharedPreferencesUtil().recordingsLanguage,
    );
    debugPrint(memory.toString());
    if (memory != null) {
      MixpanelManager().memoryCreated(memory);
      _handleCalendarCreation(memory);
    }

    // Failed, retry later
    if (memory == null) {
      memory = ServerMemory(
        id: const Uuid().v4(),
        createdAt: DateTime.now(),
        startedAt: DateTime.now(),
        structured: Structured('', '', emoji: '⛓️‍💥', category: 'other'),
        discarded: true,
        geolocation: geolocation,
        photos: photos.map<MemoryPhoto>((e) => MemoryPhoto(e.item1, e.item2)).toList(),
        failed: true,
        source: MemorySource.openglass,
        // TODO: Frame device ?
        language: SharedPreferencesUtil().recordingsLanguage,
      );
      SharedPreferencesUtil().addFailedMemory(memory);
    }

    // Warn: it's weird when memory created failed but still adding it to memories
    // use memory provider to add memory
    memoryProvider?.addMemory(memory);
    if (memoryProvider?.memories.isEmpty ?? false) {
      memoryProvider?.getMoreMemoriesFromServer();
    }

    // Clean
    _cleanNew();

    // Notify
    setMemoryCreating(false);
    setHasTranscripts(false);
    notifyListeners();
    return true;
  }

  void _cleanNew() async {
    segments = [];

    audioStorage?.clearAudioBytes();

    elapsedSeconds = 0;

    streamStartedAtSecond = null;
    firstStreamReceivedAt = null;
    secondsMissedOnReconnect = null;
    photos = [];
    conversationId = const Uuid().v4();
    processingMemoryId = null;

    // Create new socket session
    // Warn: should have a better solution to keep the socket alived
    await webSocketProvider?.closeWebSocketWithoutReconnect('reset new memory session');
    await initiateWebsocket();
  }

  _handleCalendarCreation(ServerMemory memory) {
    if (!SharedPreferencesUtil().calendarEnabled) return;
    if (SharedPreferencesUtil().calendarType != 'auto') return;

    List<Event> events = memory.structured.events;
    if (events.isEmpty) return;

    List<int> indexes = events.mapIndexed((index, e) => index).toList();
    setMemoryEventsState(memory.id, indexes, indexes.map((_) => true).toList());
    for (var i = 0; i < events.length; i++) {
      events[i].created = true;
      CalendarUtil().createEvent(
        events[i].title,
        events[i].startsAt,
        events[i].duration,
        description: events[i].description,
      );
    }
  }

  Future<void> initiateWebsocket([
    BleAudioCodec? audioCodec,
    int? sampleRate,
  ]) async {
    // setWebSocketConnecting(true);
    print('initiateWebsocket in capture_provider');
    BleAudioCodec codec = audioCodec ?? SharedPreferencesUtil().deviceCodec;
    sampleRate ??= (codec == BleAudioCodec.opus ? 16000 : 8000);
    print('is ws null: ${webSocketProvider == null}');
    await webSocketProvider?.initWebSocket(
      codec: codec,
      sampleRate: sampleRate,
      includeSpeechProfile: true,
      newMemoryWatch: true,
      // Warn: need clarify about initiateWebsocket
      onConnectionSuccess: () {
        print('inside onConnectionSuccess');
        if (segments.isNotEmpty) {
          // means that it was a reconnection, so we need to reset
          streamStartedAtSecond = null;
          secondsMissedOnReconnect = (DateTime.now().difference(firstStreamReceivedAt!).inSeconds);
        }
        print('bottom in onConnectionSuccess');
        notifyListeners();
      },
      onConnectionFailed: (err) {
        print('inside onConnectionFailed');
        print('err: $err');
        notifyListeners();
      },
      onConnectionClosed: (int? closeCode, String? closeReason) {
        print('inside onConnectionClosed');
        print('closeCode: $closeCode');
        // connection was closed, either on resetState, or by backend, or by some other reason.
        // setState(() {});
      },
      onConnectionError: (err) {
        print('inside onConnectionError');
        print('err: $err');
        // connection was okay, but then failed.
        notifyListeners();
      },
      onMessageEventReceived: (ServerMessageEvent event) {
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
            print("New processing memory created message event is invalid");
            return;
          }
          _onProcessingMemoryCreated(event.processingMemoryId!);
          return;
        }

        if (event.type == MessageEventType.memoryPostProcessingSuccess) {
          if (event.memoryId == null) {
            print("Post proccess message event is invalid");
            return;
          }
          _onMemoryPostProcessSuccess(event.memoryId!);
          return;
        }

        if (event.type == MessageEventType.memoryPostProcessingFailed) {
          if (event.memoryId == null) {
            print("Post proccess message event is invalid");
            return;
          }
          _onMemoryPostProcessFailed(event.memoryId!);
          return;
        }
      },
      onMessageReceived: (List<TranscriptSegment> newSegments) {
        if (newSegments.isEmpty) return;

        if (segments.isEmpty) {
          debugPrint('newSegments: ${newSegments.last}');
          // TODO: small bug -> when memory A creates, and memory B starts, memory B will clean a lot more seconds than available,
          //  losing from the audio the first part of the recording. All other parts are fine.
          FlutterForegroundTask.sendDataToTask(jsonEncode({'location': true}));
          var currentSeconds = (audioStorage?.frames.length ?? 0) ~/ 100;
          var removeUpToSecond = newSegments[0].start.toInt();
          audioStorage?.removeFramesRange(fromSecond: 0, toSecond: min(max(currentSeconds - 5, 0), removeUpToSecond));
          firstStreamReceivedAt = DateTime.now();
        }

        streamStartedAtSecond ??= newSegments[0].start;
        TranscriptSegment.combineSegments(
          segments,
          newSegments,
          toRemoveSeconds: streamStartedAtSecond ?? 0,
          toAddSeconds: secondsMissedOnReconnect ?? 0,
        );
        triggerTranscriptSegmentReceivedEvents(newSegments, conversationId, sendMessageToChat: (v) {
          messageProvider?.addMessage(v);
        });

        debugPrint('Memory creation timer restarted');
        _memoryCreationTimer?.cancel();
        _memoryCreationTimer =
            Timer(const Duration(seconds: quietSecondsForMemoryCreation), () => _createPhotoCharacteristicMemory());
        setHasTranscripts(true);
        notifyListeners();
      },
    );
  }

  Future streamAudioToWs(String id, BleAudioCodec codec) async {
    print('streamAudioToWs in capture_provider');
    audioStorage = WavBytesUtil(codec: codec);
    if (_bleBytesStream != null) {
      _bleBytesStream?.cancel();
    }
    _bleBytesStream = await _getBleAudioBytesListener(
      id,
      onAudioBytesReceived: (List<int> value) {
        if (value.isEmpty) return;
        audioStorage!.storeFramePacket(value);
        final trimmedValue = value.sublist(3);
        // TODO: if this (0,3) is not removed, deepgram can't seem to be able to detect the audio.
        // https://developers.deepgram.com/docs/determining-your-audio-format-for-live-streaming-audio
        if (webSocketProvider?.wsConnectionState == WebsocketConnectionStatus.connected) {
          webSocketProvider?.websocketChannel?.sink.add(trimmedValue);
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

      storageUtil!.storeFrameStoragePacket(value);
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
    writeToStorage(connectedDevice!.id, storageUtil.fileNum, command);
  }

  Future clearFileFromDevice(int fileNum) async {
    storageUtil.fileNum = fileNum;
    int command = 1;
    writeToStorage(connectedDevice!.id, storageUtil.fileNum, command);
  }

  void clearTranscripts() {
    segments = [];
    setHasTranscripts(false);
    notifyListeners();
  }

  Future resetForSpeechProfile() async {
    closeBleStream();
    await webSocketProvider?.closeWebSocketWithoutReconnect('reset for speech profile');
    setAudioBytesConnected(false);
    notifyListeners();
  }

  Future<void> resetState({
    bool restartBytesProcessing = true,
    bool isFromSpeechProfile = false,
    BTDeviceStruct? btDevice,
  }) async {
    if (resetStateAlreadyCalled) {
      debugPrint('resetState already called');
      return;
    }
    setResetStateAlreadyCalled(true);
    debugPrint('resetState: restartBytesProcessing=$restartBytesProcessing, isFromSpeechProfile=$isFromSpeechProfile');

    _cleanupCurrentState();
    await startOpenGlass();
    if (!isFromSpeechProfile) {
      await _handleMemoryCreation(restartBytesProcessing);
    }

    bool codecChanged = await _checkCodecChange();

    if (restartBytesProcessing || codecChanged) {
      await _manageWebSocketConnection(codecChanged, isFromSpeechProfile);
    }

    await initiateFriendAudioStreaming(isFromSpeechProfile);
    // TODO: Commenting this for now as DevKit 2 is not yet used in production
    // await initiateStorageBytesStreaming();

    setResetStateAlreadyCalled(false);
    notifyListeners();
  }

  void _cleanupCurrentState() {
    closeBleStream();
    cancelMemoryCreationTimer();
    setAudioBytesConnected(false);
  }

  Future<void> _handleMemoryCreation(bool restartBytesProcessing) async {
    if (!restartBytesProcessing && (photos.isNotEmpty)) {
      var res = await _createPhotoCharacteristicMemory();
      notifyListeners();
      if (res != null && !res) {
        notifyError('Memory creation failed. It\' stored locally and will be retried soon.');
      } else {
        notifyInfo('Memory created successfully 🚀');
      }
    }
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

  Future<bool> _writeToStorage(String deviceId, int numFile) async {
    var connection = await ServiceManager.instance().device.ensureConnection(deviceId);
    if (connection == null) {
      return Future.value(false);
    }
    return connection.writeToStorage(numFile);
  }

  Future<List<int>> _getStorageList(String deviceId) async {
    var connection = await ServiceManager.instance().device.ensureConnection(deviceId);
    if (connection == null) {
      return [];
    }
    return connection.getStorageList();
  }

  Future<bool> _hasPhotoStreamingCharacteristic(String deviceId) async {
    var connection = await ServiceManager.instance().device.ensureConnection(deviceId);
    if (connection == null) {
      return false;
    }
    return connection.hasPhotoStreamingCharacteristic();
  }

  Future<bool> _checkCodecChange() async {
    if (connectedDevice != null) {
      BleAudioCodec newCodec = await _getAudioCodec(connectedDevice!.id);
      if (SharedPreferencesUtil().deviceCodec != newCodec) {
        debugPrint('Device codec changed from ${SharedPreferencesUtil().deviceCodec} to $newCodec');
        SharedPreferencesUtil().deviceCodec = newCodec;
        return true;
      }
    }
    return false;
  }

  Future<void> _manageWebSocketConnection(bool codecChanged, bool isFromSpeechProfile) async {
    if (codecChanged || webSocketProvider?.wsConnectionState != WebsocketConnectionStatus.connected) {
      await webSocketProvider?.closeWebSocketWithoutReconnect('reset state $isFromSpeechProfile');
      // if (!isFromSpeechProfile) {
      await initiateWebsocket();
      // }
    }
  }

  Future<void> initiateFriendAudioStreaming(bool isFromSpeechProfile) async {
    print('connectedDevice: $connectedDevice in initiateFriendAudioStreaming');
    if (connectedDevice == null) return;

    BleAudioCodec codec = await _getAudioCodec(connectedDevice!.id);
    if (SharedPreferencesUtil().deviceCodec != codec) {
      debugPrint('Device codec changed from ${SharedPreferencesUtil().deviceCodec} to $codec');
      SharedPreferencesUtil().deviceCodec = codec;
      notifyInfo('FIM_CHANGE');
      await _manageWebSocketConnection(true, isFromSpeechProfile);
    }

    // Why is the connectedDevice null at this point?
    if (!audioBytesConnected) {
      if (connectedDevice != null) {
        await streamAudioToWs(connectedDevice!.id, codec);
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
    if (connectedDevice == null) return;
    currentStorageFiles = await _getStorageList(connectedDevice!.id);
    debugPrint('Storage files: $currentStorageFiles');
    await sendStorage(connectedDevice!.id);
    notifyListeners();
  }

  Future<void> startOpenGlass() async {
    if (connectedDevice == null) return;
    isGlasses = await _hasPhotoStreamingCharacteristic(connectedDevice!.id);
    if (!isGlasses) return;
    await openGlassProcessing(connectedDevice!, (p) {}, setHasTranscripts);
    webSocketProvider?.closeWebSocketWithoutReconnect('reset state open glass');
    notifyListeners();
  }

  void closeBleStream() {
    _bleBytesStream?.cancel();
    notifyListeners();
  }

  void cancelMemoryCreationTimer() {
    _memoryCreationTimer?.cancel();
    notifyListeners();
  }

  @override
  void dispose() {
    _bleBytesStream?.cancel();
    _memoryCreationTimer?.cancel();
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
      if (webSocketProvider?.wsConnectionState == WebsocketConnectionStatus.connected) {
        webSocketProvider?.websocketChannel?.sink.add(bytes);
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
}
