import 'dart:async';
import 'dart:io';
import 'dart:math';

import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:friend_private/backend/api_requests/api/other.dart';
import 'package:friend_private/backend/api_requests/api/prompt.dart';
import 'package:friend_private/backend/api_requests/cloud_storage.dart';
import 'package:friend_private/backend/database/memory.dart';
import 'package:friend_private/backend/database/message.dart';
import 'package:friend_private/backend/database/message_provider.dart';
import 'package:friend_private/backend/database/transcript_segment.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/bt_device.dart';
import 'package:friend_private/pages/capture/widgets/widgets.dart';
import 'package:friend_private/utils/backups.dart';
import 'package:friend_private/utils/ble/communication.dart';
import 'package:friend_private/utils/memories.dart';
import 'package:friend_private/utils/notifications.dart';
import 'package:friend_private/utils/stt/wav_bytes.dart';
import 'package:instabug_flutter/instabug_flutter.dart';
import 'package:record/record.dart';
import 'package:tuple/tuple.dart';

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
  static const quietSecondsForMemoryCreation = 120;

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
    processTranscriptContent(
      context,
      transcript,
      SharedPreferencesUtil().transcriptSegments,
      null,
      retrievedFromCache: true,
    ).then((m) {
      if (m != null && !m.discarded) executeBackup();
    });
    SharedPreferencesUtil().transcriptSegments = [];
    // TODO: include created at and finished at for this cached transcript
  }

  Future<void> initiateBytesProcessing() async {
    debugPrint('initiateBytesProcessing: $btDevice');
    if (btDevice == null) return;
    // VadUtil vad = VadUtil();
    // await vad.init();
    // Variables to maintain state
    BleAudioCodec codec = await getDeviceCodec(btDevice!.id);

    WavBytesUtil wavBytesUtil2 = WavBytesUtil(codec: codec);
    WavBytesUtil toProcessBytes2 = WavBytesUtil(codec: codec);
    StreamSubscription? stream =
        await getBleAudioBytesListener(btDevice!.id, onAudioBytesReceived: (List<int> value) async {
      if (value.isEmpty) return;

      toProcessBytes2.storeFramePacket(value);
      if (segments.isNotEmpty && wavBytesUtil2.hasFrames()) wavBytesUtil2.storeFramePacket(value);

      // if (toProcessBytes2.frames.length % 100 == 0) debugPrint('Frames length: ${toProcessBytes2.frames.length}');

      if (toProcessBytes2.frames.isNotEmpty && toProcessBytes2.frames.length % 3000 == 0) {
        Tuple2<File, List<List<int>>> data = await toProcessBytes2.createWavFile(filename: 'temp.wav');
        try {
          var segmentsEmpty = segments.isEmpty;
          await _processFileToTranscript(data.item1);
          if (segmentsEmpty && segments.isNotEmpty) {
            wavBytesUtil2.insertAudioBytes(data.item2);
          }
          // uploadFile(data.item1);
        } catch (e, stacktrace) {
          CrashReporting.reportHandledCrash(e, stacktrace,
              level: NonFatalExceptionLevel.warning,
              userAttributes: {'seconds': (data.item2.length ~/ 100).toString()});
          debugPrint('Error: e.toString() ${e.toString()}');
          toProcessBytes2.insertAudioBytes(data.item2);
        }
      }
    });

    audioBytesStream = stream;
    audioStorage = wavBytesUtil2;
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
      _memoryCreationTimer = Timer(const Duration(seconds: quietSecondsForMemoryCreation), () => _createMemory());
      currentTranscriptStartedAt ??= DateTime.now();
      currentTranscriptFinishedAt = DateTime.now();
    }
  }

  void resetState({bool restartBytesProcessing = true, BTDeviceStruct? btDevice}) {
    audioBytesStream?.cancel();
    _memoryCreationTimer?.cancel();
    if (!restartBytesProcessing && segments.isNotEmpty) _createMemory(forcedCreation: true);
    if (btDevice != null) setState(() => this.btDevice = btDevice);
    if (restartBytesProcessing) initiateBytesProcessing();
  }

  _createMemory({bool forcedCreation = false}) async {
    setState(() => memoryCreating = true);
    String transcript = TranscriptSegment.buildDiarizedTranscriptMessage(segments);
    debugPrint('_createMemory transcript: \n$transcript');
    File? file;
    try {
      // USE VAD HERE
      // var secs = !forcedCreation ? quietSecondsForMemoryCreation - 5 : 0; FIXME
      file = (await audioStorage!.createWavFile()).item1;
      uploadFile(file);
    } catch (e) {} // in case was a local recording and not a BLE recording
    Memory? memory = await processTranscriptContent(
      context,
      transcript,
      segments,
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
      _startRecording();
    }
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

  _stopRecording() async {
    // setState(() => _state = RecordState.stop);
    // await _mRecorder.stopRecorder();
    // _processPhoneMicAudioTimer?.cancel();
    // if (segments.isNotEmpty) _createMemory();
  }

  _startRecording() async {
    // if (!(await record.hasPermission())) return;
    // await _openRecorder();
    //
    // assert(_mRecorderIsInited);
    // var path = await getApplicationDocumentsDirectory();
    // var filePath = '${path.path}/recording.pcm';
    // setState(() => _state = RecordState.record);
    // await _start(filePath);
    // _processPhoneMicAudioTimer = Timer.periodic(const Duration(seconds: 30), (timer) async {
    //   await _mRecorder.stopRecorder();
    //   var f = File(filePath);
    //   // f.writeAsBytesSync([]);
    //   // var fCopy = File('${path.path}/recording_copy.pcm');
    //   // await f.copy(fCopy.path);
    //   _processFileToTranscript(f);
    // });
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
