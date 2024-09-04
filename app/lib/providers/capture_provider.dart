import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';
import 'dart:typed_data';

import 'package:collection/collection.dart';
import 'package:flutter/material.dart';
import 'package:flutter_background_service/flutter_background_service.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:flutter_provider_utilities/flutter_provider_utilities.dart';
import 'package:friend_private/backend/http/api/memories.dart';
import 'package:friend_private/backend/http/cloud_storage.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/bt_device.dart';
import 'package:friend_private/backend/schema/geolocation.dart';
import 'package:friend_private/backend/schema/memory.dart';
import 'package:friend_private/backend/schema/structured.dart';
import 'package:friend_private/backend/schema/transcript_segment.dart';
import 'package:friend_private/pages/capture/logic/mic_background_service.dart';
import 'package:friend_private/pages/capture/logic/openglass_mixin.dart';
import 'package:friend_private/providers/memory_provider.dart';
import 'package:friend_private/providers/message_provider.dart';
import 'package:friend_private/providers/websocket_provider.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/utils/audio/wav_bytes.dart';
import 'package:friend_private/utils/ble/communication.dart';
import 'package:friend_private/utils/enums.dart';
import 'package:friend_private/utils/features/calendar.dart';
import 'package:friend_private/utils/memories/integrations.dart';
import 'package:friend_private/utils/memories/process.dart';
import 'package:friend_private/utils/websockets.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:record/record.dart';
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

  var record = AudioRecorder();
  RecordingState recordingState = RecordingState.stop;

// -----------------------
// Memory creation variables
  double? streamStartedAtSecond;
  DateTime? firstStreamReceivedAt;
  int? secondsMissedOnReconnect;
  WavBytesUtil? audioStorage;
  Timer? _memoryCreationTimer;
  String conversationId = const Uuid().v4();
  DateTime? currentTranscriptStartedAt;
  DateTime? currentTranscriptFinishedAt;
  int elapsedSeconds = 0;

  // -----------------------

  bool resetStateAlreadyCalled = false;

  void setResetStateAlreadyCalled(bool value) {
    resetStateAlreadyCalled = value;
    notifyListeners();
  }

  void setHasTranscripts(bool value) {
    hasTranscripts = value;
    notifyListeners();
  }

  void setMemoryCreating(bool value) {
    memoryCreating = value;
    notifyListeners();
  }

  void setGeolocation(Geolocation? value) {
    geolocation = value;
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

  Future<bool?> createMemory({bool forcedCreation = false}) async {
    debugPrint('_createMemory forcedCreation: $forcedCreation');
    if (memoryCreating) return null;
    if (segments.isEmpty && photos.isEmpty) return false;

    // TODO: should clean variables here? and keep them locally?
    setMemoryCreating(true);
    File? file;
    if (audioStorage?.frames.isNotEmpty == true) {
      try {
        var secs = !forcedCreation ? quietSecondsForMemoryCreation : 0;
        file = (await audioStorage!.createWavFile(removeLastNSeconds: secs)).item1;
        uploadFile(file);
      } catch (e) {
        print("creating and uploading file error: $e");
      } // in case was a local recording and not a BLE recording
    }

    ServerMemory? memory = await processTranscriptContent(
      segments: segments,
      startedAt: currentTranscriptStartedAt,
      finishedAt: currentTranscriptFinishedAt,
      geolocation: geolocation,
      photos: photos,
      sendMessageToChat: (v) {
        // use message provider to send message to chat
        messageProvider?.addMessage(v);
      },
      triggerIntegrations: true,
      language: SharedPreferencesUtil().recordingsLanguage,
      audioFile: file,
    );
    debugPrint(memory.toString());
    if (memory == null && (segments.isNotEmpty || photos.isNotEmpty)) {
      memory = ServerMemory(
        id: const Uuid().v4(),
        createdAt: DateTime.now(),
        structured: Structured('', '', emoji: '⛓️‍💥', category: 'other'),
        discarded: true,
        transcriptSegments: segments,
        geolocation: geolocation,
        photos: photos.map<MemoryPhoto>((e) => MemoryPhoto(e.item1, e.item2)).toList(),
        startedAt: currentTranscriptStartedAt,
        finishedAt: currentTranscriptFinishedAt,
        failed: true,
        source: segments.isNotEmpty ? MemorySource.friend : MemorySource.openglass,
        language: segments.isNotEmpty ? SharedPreferencesUtil().recordingsLanguage : null,
      );
      SharedPreferencesUtil().addFailedMemory(memory);

      // TODO: store anyways something temporal and retry once connected again.
    }

    if (memory != null) {
      // use memory provider to add memory
      MixpanelManager().memoryCreated(memory);
      _handleCalendarCreation(memory);
      memoryProvider?.addMemory(memory);
      if (memoryProvider?.memories.isEmpty ?? false) {
        memoryProvider?.getMoreMemoriesFromServer();
      }
    }

    if (memory != null && !memory.failed && file != null && segments.isNotEmpty && !memory.discarded) {
      setMemoryCreating(false);
      try {
        memoryPostProcessing(file, memory.id).then((postProcessed) {
          if (postProcessed != null) {
            memoryProvider?.updateMemory(postProcessed);
          } else {
            memory!.postprocessing = MemoryPostProcessing(
              status: MemoryPostProcessingStatus.failed,
              model: MemoryPostProcessingModel.fal_whisperx,
            );
            memoryProvider?.updateMemory(memory);
          }
        });
      } catch (e) {
        print('Error occurred during memory post-processing: $e');
      }
    }

    SharedPreferencesUtil().transcriptSegments = [];
    segments = [];
    audioStorage?.clearAudioBytes();
    setHasTranscripts(false);

    currentTranscriptStartedAt = null;
    currentTranscriptFinishedAt = null;
    elapsedSeconds = 0;

    streamStartedAtSecond = null;
    firstStreamReceivedAt = null;
    secondsMissedOnReconnect = null;
    photos = [];
    conversationId = const Uuid().v4();
    setMemoryCreating(false);
    notifyListeners();
    return true;
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
        SharedPreferencesUtil().transcriptSegments = segments;
        setHasTranscripts(true);
        debugPrint('Memory creation timer restarted');
        _memoryCreationTimer?.cancel();
        _memoryCreationTimer = Timer(const Duration(seconds: quietSecondsForMemoryCreation), () => createMemory());
        currentTranscriptStartedAt ??= DateTime.now();
        currentTranscriptFinishedAt = DateTime.now();
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
    _bleBytesStream = await getBleAudioBytesListener(
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

  void clearTranscripts() {
    segments = [];
    SharedPreferencesUtil().transcriptSegments = [];
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

    setResetStateAlreadyCalled(false);
    notifyListeners();
  }

  void _cleanupCurrentState() {
    closeBleStream();
    cancelMemoryCreationTimer();
    setAudioBytesConnected(false);
  }

  Future<void> _handleMemoryCreation(bool restartBytesProcessing) async {
    if (!restartBytesProcessing && (segments.isNotEmpty || photos.isNotEmpty)) {
      bool? result = await createMemory(forcedCreation: true);
      if (result != null && !result) {
        notifyError('Memory creation failed. It\'s stored locally and will be retried soon.');
      } else {
        notifyInfo('Memory created successfully 🚀');
      }
    }
  }

  Future<bool> _checkCodecChange() async {
    if (connectedDevice != null) {
      BleAudioCodec newCodec = await getAudioCodec(connectedDevice!.id);
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

    BleAudioCodec codec = await getAudioCodec(connectedDevice!.id);
    if (SharedPreferencesUtil().deviceCodec != codec) {
      debugPrint('Device codec changed from ${SharedPreferencesUtil().deviceCodec} to $codec');
      SharedPreferencesUtil().deviceCodec = codec;
      notifyInfo('FIM_CHANGE');
      await _manageWebSocketConnection(true, isFromSpeechProfile);
    }

    if (!audioBytesConnected) {
      await streamAudioToWs(connectedDevice!.id, codec);
    }

    notifyListeners();
  }

  processCachedTranscript() async {
    // TODO: only applies to friend, not openglass, fix it
    var segments = SharedPreferencesUtil().transcriptSegments;
    if (segments.isEmpty) return;
    processTranscriptContent(
      segments: segments,
      sendMessageToChat: null,
      triggerIntegrations: false,
      language: SharedPreferencesUtil().recordingsLanguage,
    );
    SharedPreferencesUtil().transcriptSegments = [];
    // TODO: include created at and finished at for this cached transcript
  }

  Future<void> startOpenGlass() async {
    if (connectedDevice == null) return;
    isGlasses = await hasPhotoStreamingCharacteristic(connectedDevice!.id);
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

  startStreamRecording() async {
    await Permission.microphone.request();
    var stream = await record.startStream(
      const RecordConfig(encoder: AudioEncoder.pcm16bits, sampleRate: 16000, numChannels: 1),
    );
    updateRecordingState(RecordingState.record);
    stream.listen((data) async {
      if (webSocketProvider?.wsConnectionState == WebsocketConnectionStatus.connected) {
        webSocketProvider?.websocketChannel?.sink.add(data);
      }
    });
  }

  streamRecordingOnAndroid() async {
    await Permission.microphone.request();
    updateRecordingState(RecordingState.initialising);
    await initializeMicBackgroundService();
    startBackgroundService();
    await listenToBackgroundService();
  }

  listenToBackgroundService() async {
    if (await FlutterBackgroundService().isRunning()) {
      FlutterBackgroundService().on('audioBytes').listen((event) {
        Uint8List convertedList = Uint8List.fromList(event!['data'].cast<int>());
        if (webSocketProvider?.wsConnectionState == WebsocketConnectionStatus.connected)
          webSocketProvider?.websocketChannel?.sink.add(convertedList);
      });
      FlutterBackgroundService().on('stateUpdate').listen((event) {
        if (event!['state'] == 'recording') {
          updateRecordingState(RecordingState.record);
        } else if (event['state'] == 'initializing') {
          updateRecordingState(RecordingState.initialising);
        } else if (event['state'] == 'stopped') {
          updateRecordingState(RecordingState.stop);
        }
      });
    }
  }

  stopStreamRecording() async {
    if (await record.isRecording()) await record.stop();
    updateRecordingState(RecordingState.stop);
    notifyListeners();
  }

  stopStreamRecordingOnAndroid() {
    stopBackgroundService();
  }
}
