import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:friend_private/backend/database/geolocation.dart';
import 'package:friend_private/backend/database/memory.dart';
import 'package:friend_private/backend/database/transcript_segment.dart';
import 'package:friend_private/backend/http/cloud_storage.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/bt_device.dart';
import 'package:friend_private/backend/schema/memory.dart';
import 'package:friend_private/backend/schema/message.dart';
import 'package:friend_private/pages/capture/location_service.dart';
import 'package:friend_private/pages/capture/logic/openglass_mixin.dart';
import 'package:friend_private/pages/capture/widgets/widgets.dart';
import 'package:friend_private/pages/home/storage.dart';
import 'package:friend_private/utils/audio/wav_bytes.dart';
import 'package:friend_private/utils/ble/communication.dart';
import 'package:friend_private/utils/enums.dart';
import 'package:friend_private/utils/memories/integrations.dart';
import 'package:friend_private/utils/memories/process.dart';
import 'package:friend_private/utils/websockets.dart';
import 'package:friend_private/widgets/dialog.dart';
import 'package:internet_connection_checker_plus/internet_connection_checker_plus.dart';
import 'package:location/location.dart';
import 'package:uuid/uuid.dart';

import 'logic/phone_recorder_mixin.dart';
import 'logic/websocket_mixin.dart';

class CapturePage extends StatefulWidget {
  final Function addMemory;
  final Function addMessage;
  final BTDeviceStruct? device;

  const CapturePage({
    super.key,
    required this.device,
    required this.addMemory,
    required this.addMessage,
  });

  @override
  State<CapturePage> createState() => CapturePageState();
}

class CapturePageState extends State<CapturePage>
    with AutomaticKeepAliveClientMixin, WidgetsBindingObserver, PhoneRecorderMixin, WebSocketMixin, OpenGlassMixin {
  @override
  bool get wantKeepAlive => true;

  BTDeviceStruct? btDevice;
  bool _hasTranscripts = false;
  static const quietSecondsForMemoryCreation = 120;

  /// ----
  List<TranscriptSegment> segments = [];

  StreamSubscription? _bleBytesStream;
  WavBytesUtil? audioStorage;

  Timer? _memoryCreationTimer;
  bool memoryCreating = false;

  DateTime? currentTranscriptStartedAt;
  DateTime? currentTranscriptFinishedAt;

  InternetStatus? _internetStatus;

  late StreamSubscription<InternetStatus> _internetListener;
  bool isGlasses = false;
  String conversationId = const Uuid().v4(); // used only for transcript segment plugins

  double? streamStartedAtSecond;
  DateTime? firstStreamReceivedAt;
  int? secondsMissedOnReconnect;

  Geolocation? geolocation;

  Future<void> initiateWebsocket([BleAudioCodec? audioCodec, int? sampleRate]) async {
    BleAudioCodec codec = audioCodec ?? (btDevice?.id == null ? BleAudioCodec.pcm8 : await getAudioCodec(btDevice!.id));
    sampleRate ??= (codec == BleAudioCodec.opus ? 16000 : 8000);
    await initWebSocket(
      codec: codec,
      sampleRate: sampleRate,
      onConnectionSuccess: () {
        if (segments.isNotEmpty) {
          // means that it was a reconnection, so we need to reset
          streamStartedAtSecond = null;
          secondsMissedOnReconnect = (DateTime.now().difference(firstStreamReceivedAt!).inSeconds);
        }
        setState(() {});
      },
      onConnectionFailed: (err) => setState(() {}),
      onConnectionClosed: (int? closeCode, String? closeReason) {
        // connection was closed, either on resetState, or by backend, or by some other reason.
        setState(() {});
      },
      onConnectionError: (err) {
        // connection was okay, but then failed.
        setState(() {});
      },
      onMessageReceived: (List<TranscriptSegment> newSegments) {
        if (newSegments.isEmpty) return;
        if (segments.isEmpty) {
          debugPrint('newSegments: ${newSegments.last}');
          // TODO: small bug -> when memory A creates, and memory B starts, memory B will clean a lot more seconds than available,
          //  losing from the audio the first part of the recording. All other parts are fine.
          FlutterForegroundTask.sendDataToTask(jsonEncode({'location': true}));
          audioStorage?.removeFramesRange(fromSecond: 0, toSecond: newSegments[0].start.toInt());
          firstStreamReceivedAt = DateTime.now();
        }
        streamStartedAtSecond ??= newSegments[0].start;

        TranscriptSegment.combineSegments(
          segments,
          newSegments,
          toRemoveSeconds: streamStartedAtSecond ?? 0,
          toAddSeconds: secondsMissedOnReconnect ?? 0,
        );
        triggerTranscriptSegmentReceivedEvents(newSegments, conversationId, sendMessageToChat: sendMessageToChat);
        SharedPreferencesUtil().transcriptSegments = segments;
        setHasTranscripts(true);
        debugPrint('Memory creation timer restarted');
        _memoryCreationTimer?.cancel();
        _memoryCreationTimer = Timer(const Duration(seconds: quietSecondsForMemoryCreation), () => _createMemory());
        currentTranscriptStartedAt ??= DateTime.now();
        currentTranscriptFinishedAt = DateTime.now();
        setState(() {});
      },
    );
  }

  Future<void> initiateFriendAudioStreaming() async {
    if (btDevice == null) return;
    BleAudioCodec codec = await getAudioCodec(btDevice!.id);
    if (codec != BleAudioCodec.pcm8) restartWebSocket();
    audioStorage = WavBytesUtil(codec: codec);
    /* start section modified */
    await setStorageMode(btDevice!.id, 1);
    storageMode = false;
    /* end section modified */
    _bleBytesStream = await getBleAudioBytesListener(
      btDevice!.id,
      onAudioBytesReceived: (List<int> value) {
        if (value.isEmpty) return;
        audioStorage!.storeFramePacket(value);
        value.removeRange(0, 3);
        if (wsConnectionState == WebsocketConnectionStatus.connected) {
          websocketChannel?.sink.add(value);
        }
      },
    );
  }

  int elapsedSeconds = 0;

  Future<void> startOpenGlass() async {
    if (btDevice == null) return;
    isGlasses = await hasPhotoStreamingCharacteristic(btDevice!.id);
    debugPrint('startOpenGlass isGlasses: $isGlasses');
    if (!isGlasses) return;

    await openGlassProcessing(btDevice!, (p) => setState(() {}), setHasTranscripts);
    closeWebSocket();
  }

  void resetState({bool restartBytesProcessing = true, BTDeviceStruct? btDevice}) {
    debugPrint('resetState: $restartBytesProcessing');
    _bleBytesStream?.cancel();
    _memoryCreationTimer?.cancel();
    if (!restartBytesProcessing && (segments.isNotEmpty || photos.isNotEmpty)) _createMemory(forcedCreation: true);
    if (btDevice != null) setState(() => this.btDevice = btDevice);
    if (restartBytesProcessing) {
      startOpenGlass();
      initiateFriendAudioStreaming();
    }
  }

  void restartWebSocket() {
    closeWebSocket();
    initiateWebsocket();
  }

  void sendMessageToChat(ServerMessage message) {
    widget.addMessage(message);
  }

  _createMemory({bool forcedCreation = false}) async {
    debugPrint('_createMemory forcedCreation: $forcedCreation');
    if (memoryCreating) return;
    if (segments.isEmpty && photos.isEmpty) return;

    // TODO: should clean variables here? and keep them locally?
    setState(() => memoryCreating = true);
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
      segments,
      startedAt: currentTranscriptStartedAt,
      finishedAt: currentTranscriptFinishedAt,
      geolocation: geolocation,
      photos: photos,
      sendMessageToChat: sendMessageToChat,
      triggerIntegrations: true,
      language: SharedPreferencesUtil().recordingsLanguage,
    );
    debugPrint(memory.toString());
    if (memory == null && segments.isNotEmpty && photos.isNotEmpty) {
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
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
        content: Text(
          'Memory creation failed. It\' stored locally and will be retried soon.',
          style: TextStyle(color: Colors.white, fontSize: 14),
        ),
      ));
      // TODO: store anyways something temporal and retry once connected again.
    }

    widget.addMemory(memory);
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
    setState(() => memoryCreating = false);
  }

  setHasTranscripts(bool hasTranscripts) {
    if (_hasTranscripts == hasTranscripts) return;
    setState(() => _hasTranscripts = hasTranscripts);
  }

  processCachedTranscript() async {
    // TODO: only applies to friend, not openglass, fix it
    debugPrint('_processCachedTranscript');
    var segments = SharedPreferencesUtil().transcriptSegments;
    if (segments.isEmpty) return;
    processTranscriptContent(
      segments,
      retrievedFromCache: true,
      sendMessageToChat: null,
      triggerIntegrations: false,
      language: SharedPreferencesUtil().recordingsLanguage,
    );
    SharedPreferencesUtil().transcriptSegments = [];
    // TODO: include created at and finished at for this cached transcript
  }

  void _onReceiveTaskData(dynamic data) {
    if (data is Map<String, dynamic>) {
      if (data.containsKey('latitude') && data.containsKey('longitude')) {
        geolocation = Geolocation(
          latitude: data['latitude'],
          longitude: data['longitude'],
          accuracy: data['accuracy'],
          altitude: data['altitude'],
          time: DateTime.parse(data['time']),
        );
        debugPrint('Location data received from background: $geolocation');
      } else {
        geolocation = null;
      }
    }
  }

  @override
  void initState() {
    btDevice = widget.device;
    WavBytesUtil.clearTempWavFiles();
    initiateWebsocket();
    startOpenGlass();
    initiateFriendAudioStreaming();
    processCachedTranscript();

    FlutterForegroundTask.addTaskDataCallback(_onReceiveTaskData);
    WidgetsBinding.instance.addObserver(this);
    SchedulerBinding.instance.addPostFrameCallback((_) async {
      if (await LocationService().displayPermissionsDialog()) {
        await showDialog(
          context: context,
          builder: (c) => getDialog(
            context,
            () => Navigator.of(context).pop(),
            () async {
              await requestLocationPermission();
              await LocationService().requestBackgroundPermission();
              if (mounted) Navigator.of(context).pop();
            },
            'Enable Location Services?  🌍',
            'We need your location permissions to add a location tag to your memories. This will help you remember where they happened.\n\nFor location to work in background, you\'ll have to set Location Permission to "Always Allow" in Settings',
            singleButton: false,
          ),
        );
      }
    });
    _internetListener = InternetConnection().onStatusChange.listen((InternetStatus status) {
      switch (status) {
        case InternetStatus.connected:
          _internetStatus = InternetStatus.connected;
          break;
        case InternetStatus.disconnected:
          _internetStatus = InternetStatus.disconnected;
          // so if you have a memory in progress, it doesn't get created, and you don't lose the remaining bytes.
          _memoryCreationTimer?.cancel();
          break;
      }
    });
    super.initState();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    record.dispose();

    _bleBytesStream?.cancel();
    _memoryCreationTimer?.cancel();
    _internetListener.cancel();

    closeWebSocket();

    super.dispose();
  }

  Future requestLocationPermission() async {
    LocationService locationService = LocationService();
    bool serviceEnabled = await locationService.enableService();
    if (!serviceEnabled) {
      debugPrint('Location service not enabled');
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text(
              'Location services are disabled. Enable them for a better experience.',
              style: TextStyle(color: Colors.white, fontSize: 14),
            ),
          ),
        );
      }
    } else {
      PermissionStatus permissionGranted = await locationService.requestPermission();
      if (permissionGranted == PermissionStatus.denied) {
        debugPrint('Location permission not granted');
      } else if (permissionGranted == PermissionStatus.deniedForever) {
        debugPrint('Location permission denied forever');
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text(
                'If you change your mind, you can enable location services in your device settings.',
                style: TextStyle(color: Colors.white, fontSize: 14),
              ),
            ),
          );
        }
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    return Stack(
      children: [
        ListView(children: [
          speechProfileWidget(context, setState, restartWebSocket),
          ...getConnectionStateWidgets(context, _hasTranscripts, widget.device, wsConnectionState, _internetStatus),
          getTranscriptWidget(memoryCreating, segments, photos, widget.device),
          ...connectionStatusWidgets(context, segments, wsConnectionState, _internetStatus),
          const SizedBox(height: 16)
        ]),
        getPhoneMicRecordingButton(_recordingToggled, recordingState)
      ],
    );
  }

  _recordingToggled() async {
    if (recordingState == RecordingState.record) {
      if (Platform.isAndroid) {
        stopStreamRecordingOnAndroid();
      } else {
        await stopStreamRecording(wsConnectionState, websocketChannel);
      }
      setState(() => recordingState = RecordingState.stop);
      _memoryCreationTimer?.cancel();
      _createMemory();
    } else if (recordingState == RecordingState.initialising) {
      debugPrint('initialising, have to wait');
    } else {
      showDialog(
        context: context,
        builder: (c) => getDialog(
          context,
          () => Navigator.pop(context),
          () async {
            Navigator.pop(context);
            setState(() => recordingState = RecordingState.initialising);
            closeWebSocket();
            await initiateWebsocket(BleAudioCodec.pcm16, 16000);
            if (Platform.isAndroid) {
              await streamRecordingOnAndroid(wsConnectionState, websocketChannel);
            } else {
              await startStreamRecording(wsConnectionState, websocketChannel);
            }
          },
          'Limited Capabilities',
          'Recording with your phone microphone has a few limitations, including but not limited to: speaker profiles, background reliability.',
          okButtonText: 'Ok, I understand',
        ),
      );
    }
  }
}
