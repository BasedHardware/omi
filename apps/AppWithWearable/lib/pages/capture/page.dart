import 'dart:async';
import 'dart:io';
import 'dart:math';

import 'package:disable_battery_optimization/disable_battery_optimization.dart';
import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter_background_service/flutter_background_service.dart';
import 'package:friend_private/backend/api_requests/api/other.dart';
import 'package:friend_private/backend/api_requests/api/prompt.dart';
import 'package:friend_private/backend/api_requests/cloud_storage.dart';
import 'package:friend_private/backend/database/memory.dart';
import 'package:friend_private/backend/database/message.dart';
import 'package:friend_private/backend/database/message_provider.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/bt_device.dart';
import 'package:friend_private/backend/storage/segment.dart';
import 'package:friend_private/pages/capture/background_service.dart';
import 'package:friend_private/pages/capture/widgets/widgets.dart';
import 'package:friend_private/utils/backups.dart';
import 'package:friend_private/utils/ble/communication.dart';
import 'package:friend_private/utils/memories.dart';
import 'package:friend_private/utils/notifications.dart';
import 'package:friend_private/utils/stt/wav_bytes.dart';
import 'package:path_provider/path_provider.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:record/record.dart';

class CapturePage extends StatefulWidget {
  final Function refreshMemories;
  final Function refreshMessages;
  final BTDeviceStruct? device;

  const CapturePage({
    super.key,
    required this.device,
    required this.refreshMemories,
    required this.refreshMessages,
  });

  @override
  State<CapturePage> createState() => CapturePageState();
}

class CapturePageState extends State<CapturePage> with AutomaticKeepAliveClientMixin {
  @override
  bool get wantKeepAlive => true;

  bool _hasTranscripts = false;
  final record = AudioRecorder();
  RecordState _state = RecordState.stop;

  /// ----
  BTDeviceStruct? btDevice;
  List<TranscriptSegment> segments = [];

  StreamSubscription? audioBytesStream;
  WavBytesUtil? audioStorage;

  Timer? _processPhoneMicAudioTimer;
  Timer? _memoryCreationTimer;
  bool memoryCreating = false;

  DateTime? currentTranscriptStartedAt;
  DateTime? currentTranscriptFinishedAt;

  _processCachedTranscript() async {
    debugPrint('_processCachedTranscript');
    var segments = SharedPreferencesUtil().transcriptSegments;
    if (segments.isEmpty) return;
    String transcript = TranscriptSegment.buildDiarizedTranscriptMessage(SharedPreferencesUtil().transcriptSegments);
    processTranscriptContent(context, transcript, null, retrievedFromCache: true).then((m) {
      if (m != null && !m.discarded) executeBackup();
    });
    SharedPreferencesUtil().transcriptSegments = [];
    // TODO: include created at and finished at for this cached transcript
  }

  Future<void> initiateBytesProcessing() async {
    debugPrint('initiateBytesProcessing: $btDevice');
    if (btDevice == null) return;
    WavBytesUtil wavBytesUtil = WavBytesUtil();
    WavBytesUtil toProcessBytes = WavBytesUtil();
    // VadUtil vad = VadUtil();
    // await vad.init();

    StreamSubscription? stream = await getBleAudioBytesListener(btDevice!.id, onAudioBytesReceived: (List<int> value) {
      if (value.isEmpty) return;
      value.removeRange(0, 3);
      // ~ losing because of pipe precision, voltage on device is 0.912391923, it sends 1,
      // so we are losing lots of resolution, and bit depth
      for (int i = 0; i < value.length; i += 2) {
        int byte1 = value[i];
        int byte2 = value[i + 1];
        int int16Value = (byte2 << 8) | byte1;
        wavBytesUtil.addAudioBytes([int16Value]);
        toProcessBytes.addAudioBytes([int16Value]);
      }
      if (toProcessBytes.audioBytes.length % 240000 == 0) {
        var bytesCopy = List<int>.from(toProcessBytes.audioBytes);
        // SharedPreferencesUtil().temporalAudioBytes = wavBytesUtil.audioBytes;
        toProcessBytes.clearAudioBytesSegment(remainingSeconds: 1);
        WavBytesUtil.createWavFile(bytesCopy, filename: 'temp.wav').then((f) async {
          // var containsAudio = await vad.predict(f.readAsBytesSync());
          // debugPrint('Processing audio bytes: ${f.toString()}');
          try {
            _processFileToTranscript(f);
          } catch (e) {
            debugPrint(e.toString());
            toProcessBytes.insertAudioBytes(bytesCopy.sublist(0, 232000)); // remove last 1 sec to avoid duplicate
          }
        });
      }
    });

    audioBytesStream = stream;
    audioStorage = wavBytesUtil;
  }

  _processFileToTranscript(File f) async {
    List<TranscriptSegment> newSegments = await transcribeAudioFile2(f);
    debugPrint('newSegments: $newSegments');
    TranscriptSegment.combineSegments(segments, newSegments); // combines b into a
    if (newSegments.isNotEmpty) {
      SharedPreferencesUtil().transcriptSegments = segments;
      setState(() {});
      setHasTranscripts(true);
      debugPrint('Memory creation timer restarted');
      _memoryCreationTimer?.cancel();
      _memoryCreationTimer = Timer(const Duration(seconds: 120), () => _createMemory());
      currentTranscriptStartedAt ??= DateTime.now();
      currentTranscriptFinishedAt = DateTime.now();
    }
  }

  void resetState({bool restartBytesProcessing = true, BTDeviceStruct? btDevice}) {
    audioBytesStream?.cancel();
    _memoryCreationTimer?.cancel();
    if (!restartBytesProcessing && segments.isNotEmpty) _createMemory();
    if (btDevice != null) setState(() => this.btDevice = btDevice);
    if (restartBytesProcessing) initiateBytesProcessing();
  }

  _createMemory() async {
    setState(() => memoryCreating = true);
    String transcript = TranscriptSegment.buildDiarizedTranscriptMessage(segments);
    debugPrint('_createMemory transcript: \n$transcript');
    File? file;
    try {
      file = await WavBytesUtil.createWavFile(audioStorage!.audioBytes);
      uploadFile(file);
    } catch (e) {} // in case was a local recording and not a BLE recording
    Memory? memory = await processTranscriptContent(
      context,
      transcript,
      file?.path,
      startedAt: currentTranscriptStartedAt,
      finishedAt: currentTranscriptFinishedAt,
    );
    debugPrint(memory.toString());
    // TODO: backup when useful memory created, maybe less later, 2k memories occupy 3MB in the json payload
    if (memory != null && !memory.discarded) executeBackup();
    if (memory != null && !memory.discarded && SharedPreferencesUtil().postMemoryNotificationIsChecked) {
      postMemoryCreationNotification(memory).then((r) {
        // r = 'Hi there testing notifications stuff';
        debugPrint('Notification response: $r');
        if (r.isEmpty) return;
        // TODO: notification UI should be different, maybe a different type of message + use a Enum for message type
        var msg = Message(DateTime.now(), r, 'ai');
        msg.memories.add(memory);
        MessageProvider().saveMessage(msg);
        widget.refreshMessages();
        createNotification(
          notificationId: 2,
          title: 'New Memory Created! ${memory.structured.target!.getEmoji()}',
          body: r,
        );
      });
    }
    await widget.refreshMemories();
    SharedPreferencesUtil().transcriptSegments = [];
    segments = [];
    setState(() => memoryCreating = false);
    audioStorage?.clearAudioBytes();
    setHasTranscripts(false);

    currentTranscriptStartedAt = null;
    currentTranscriptFinishedAt = null;
  }

  setHasTranscripts(bool hasTranscripts) {
    if (_hasTranscripts == hasTranscripts) return;
    setState(() => _hasTranscripts = hasTranscripts);
  }

  @override
  void initState() {
    btDevice = widget.device;
    SchedulerBinding.instance.addPostFrameCallback((_) async {
      debugPrint('SchedulerBinding.instance');
      initiateBytesProcessing();
    });
    listenToBackgroundService();
    _processCachedTranscript();
    // processTranscriptContent(context, '''a''', null);
    super.initState();
  }

  @override
  void dispose() {
    record.dispose();
    _memoryCreationTimer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    // super.build(context);
    return Stack(
      children: [
        ListView(children: [
          speechProfileWidget(context),
          ...getConnectionStateWidgets(context, _hasTranscripts, widget.device),
          getTranscriptWidget(memoryCreating, segments, widget.device),
          const SizedBox(height: 16)
        ]),
        getPhoneMicRecordingButton(_recordingToggled, _state)
      ],
    );
  }

  _recordingToggled() async {
    if (_state == RecordState.record) {
      _stopRecording();
    } else {
      await _startRecording();
    }
  }

  void listenToBackgroundService() {
    final backgroundService = FlutterBackgroundService();
    backgroundService.on('update').listen((event) async {
      if (event!['path'] != null && File(event['path']).existsSync()) {
        await _processFileToTranscript(File(event['path']));
      } else {
        debugPrint('file does not exist');
        var path = await getApplicationDocumentsDirectory();
        var filePath = '${path.path}/recording.aac';
        File f = await File(filePath).writeAsBytes(event['bytes']);
        await _processFileToTranscript(f);
      }
      debugPrint('received data message in feed: $event');
    }, onError: (e, s) {
      debugPrint('error listening for updates: $e, $s');
    }, onDone: () {
      debugPrint('background listen closed');
    });
    backgroundService.on('stateUpdate').listen((event) async {
      if (event!['state'] == 'recording') {
        setState(() => _state = RecordState.record);
      } else if (event['state'] == 'stopped') {
        setState(() => _state = RecordState.stop);
      }
    }, onError: (e, s) {
      debugPrint('error listening for updates: $e, $s');
    }, onDone: () {
      debugPrint('background listen closed');
    });
  }

  _startRecording() async {
    if (Platform.isAndroid) {
      bool isBatteryOptimizationDisabled = await DisableBatteryOptimization.isBatteryOptimizationDisabled ?? false;
      if (!isBatteryOptimizationDisabled) {
        await DisableBatteryOptimization.showDisableBatteryOptimizationSettings();
      }
    }
    await Permission.microphone.request();
    initializeBackgroundService();
  }

  _printFileSize(File file) async {
    int bytes = await file.length();
    var i = (log(bytes) / log(1024)).floor();
    const suffixes = ["B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB"];
    var size = '${(bytes / pow(1024, i)).toStringAsFixed(2)} ${suffixes[i]}';
    debugPrint('File size: $size');
  }

  // final FlutterSoundRecorder _mRecorder = FlutterSoundRecorder();
  // bool _mRecorderIsInited = false;
  // StreamSubscription? _mRecordingDataSubscription;
  // String? _mPath;

  // Future<void> _openRecorder() async {
  //   debugPrint('_openRecorder');
  //   // var status = await Permission.microphone.request();
  //   // if (status != PermissionStatus.granted) {
  //   //   throw RecordingPermissionException('Microphone permission not granted');
  //   // }
  //   await _mRecorder.openRecorder();
  //   debugPrint('Recorder opened');
  //   final session = await AudioSession.instance;
  //   await session.configure(AudioSessionConfiguration(
  //     avAudioSessionCategory: AVAudioSessionCategory.record,
  //     avAudioSessionCategoryOptions:
  //         AVAudioSessionCategoryOptions.allowBluetooth | AVAudioSessionCategoryOptions.defaultToSpeaker,
  //     avAudioSessionMode: AVAudioSessionMode.spokenAudio,
  //     avAudioSessionRouteSharingPolicy: AVAudioSessionRouteSharingPolicy.defaultPolicy,
  //     avAudioSessionSetActiveOptions: AVAudioSessionSetActiveOptions.none,
  //     androidAudioAttributes: const AndroidAudioAttributes(
  //       contentType: AndroidAudioContentType.speech,
  //       flags: AndroidAudioFlags.none,
  //       usage: AndroidAudioUsage.voiceCommunication,
  //     ),
  //     androidAudioFocusGainType: AndroidAudioFocusGainType.gain,
  //     androidWillPauseWhenDucked: true,
  //   ));
  //
  //   setState(() {
  //     _mRecorderIsInited = true;
  //   });
  // }

  // Future<IOSink> createFile() async {
  //   var tempDir = await getTemporaryDirectory();
  //   _mPath = '${tempDir.path}/flutter_sound_example.pcm';
  //   var outputFile = File(_mPath!);
  //   if (outputFile.existsSync()) {
  //     await outputFile.delete();
  //   }
  //   return outputFile.openWrite();
  // }

  // ----------------------  Here is the code to record to a Stream ------------

  _stopRecording() {
    stopBackgroundService();
    setState(() => _state = RecordState.stop);
    if (segments.isNotEmpty) _createMemory();
  }

  _start(String filePath) async {
    // await _mRecorder.startRecorder(
    //   codec: Codec.pcm16,
    //   toFile: filePath,
    //   sampleRate: 16000,
    //   numChannels: 1,
    // );
  }
}
