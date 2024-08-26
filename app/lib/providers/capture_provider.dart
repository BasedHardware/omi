import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:flutter/material.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:flutter_provider_utilities/flutter_provider_utilities.dart';
import 'package:friend_private/backend/database/geolocation.dart';
import 'package:friend_private/backend/database/memory.dart';
import 'package:friend_private/backend/database/transcript_segment.dart';
import 'package:friend_private/backend/http/api/memories.dart';
import 'package:friend_private/backend/http/cloud_storage.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/bt_device.dart';
import 'package:friend_private/backend/schema/memory.dart';
import 'package:friend_private/pages/capture/logic/openglass_mixin.dart';
import 'package:friend_private/pages/capture/logic/websocket_mixin.dart';
import 'package:friend_private/pages/capture/page.dart';
import 'package:friend_private/providers/memory_provider.dart';
import 'package:friend_private/providers/message_provider.dart';
import 'package:friend_private/utils/audio/wav_bytes.dart';
import 'package:friend_private/utils/ble/communication.dart';
import 'package:friend_private/utils/memories/integrations.dart';
import 'package:friend_private/utils/memories/process.dart';
import 'package:friend_private/utils/websockets.dart';
import 'package:uuid/uuid.dart';

class CaptureProvider extends ChangeNotifier with WebSocketMixin, OpenGlassMixin, MessageNotifierMixin {
  MemoryProvider? memoryProvider;
  MessageProvider? messageProvider;

  void updateProviderInstances(MemoryProvider? mp, MessageProvider? p) {
    memoryProvider = mp;
    messageProvider = p;
  }

  bool restartAudioProcessing = false;

  List<TranscriptSegment> segments = [];
  Geolocation? geolocation;

  bool hasTranscripts = false;
  bool memoryCreating = false;
  bool webSocketConnected = false;
  bool webSocketConnecting = false;

  static const quietSecondsForMemoryCreation = 120;

  StreamSubscription? _bleBytesStream;

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

  void setWebSocketConnected(bool value) {
    webSocketConnected = value;
    notifyListeners();
  }

  void setWebSocketConnecting(bool value) {
    webSocketConnecting = value;
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
      memoryProvider?.addMemory(memory);
    }

    if (memory != null && !memory.failed && file != null && segments.isNotEmpty && !memory.discarded) {
      setMemoryCreating(false);
      try {
        memoryPostProcessing(file, memory.id).then((postProcessed) {
          // use memory provider to update memory
          memoryProvider?.updateMemory(postProcessed);
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

  Future<void> initiateWebsocket([
    BleAudioCodec? audioCodec,
    int? sampleRate,
  ]) async {
    setWebSocketConnecting(true);
    print('initiateWebsocket');
    BleAudioCodec codec = audioCodec ?? SharedPreferencesUtil().deviceCodec;
    sampleRate ??= (codec == BleAudioCodec.opus ? 16000 : 8000);
    await initWebSocket(
      codec: codec,
      sampleRate: sampleRate,
      includeSpeechProfile: false,
      onConnectionSuccess: () {
        print('inside onConnectionSuccess');
        setWebSocketConnecting(false);
        setWebSocketConnected(true);
        if (segments.isNotEmpty) {
          // means that it was a reconnection, so we need to reset
          streamStartedAtSecond = null;
          secondsMissedOnReconnect = (DateTime.now().difference(firstStreamReceivedAt!).inSeconds);
        }
        notifyListeners();
      },
      onConnectionFailed: (err) {
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
          // use message provider to send message to chat
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
    print('streamAudioToWs');
    print('wsConnectionState: $wsConnectionState');
    audioStorage = WavBytesUtil(codec: codec);
    _bleBytesStream = await getBleAudioBytesListener(
      id,
      onAudioBytesReceived: (List<int> value) {
        if (value.isEmpty) return;
        audioStorage!.storeFramePacket(value);
        // print(value);
        value.removeRange(0, 3);
        // TODO: if this (0,3) is not removed, deepgram can't seem to be able to detect the audio.
        // https://developers.deepgram.com/docs/determining-your-audio-format-for-live-streaming-audio
        if (wsConnectionState == WebsocketConnectionStatus.connected) {
          websocketChannel?.sink.add(value);
        }
      },
    );
    notifyListeners();
  }

  void setRestartAudioProcessing(bool value) {
    restartAudioProcessing = value;
    notifyListeners();
  }

  Future resetState(
      {bool restartBytesProcessing = true,
      BTDeviceStruct? btDevice,
      required GlobalKey<CapturePageState> captureKey}) async {
    //TODO: Improve this, do not rely on the captureKey. And also get rid of global keys if possible.
    print('inside of resetState');
    debugPrint('resetState: $restartBytesProcessing');
    closeBleStream();
    cancelMemoryCreationTimer();

    if (!restartBytesProcessing && (segments.isNotEmpty || photos.isNotEmpty)) {
      print('inside of resetState and createMemory');
      var res = await createMemory(forcedCreation: true);
      notifyListeners();
      if (res != null && !res) {
        notifyError('Memory creation failed. It\' stored locally and will be retried soon.');
      } else {
        notifyInfo('Memory created successfully 🚀');
      }
    }
    setRestartAudioProcessing(restartBytesProcessing);
    captureKey.currentState?.resetState();
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
}
