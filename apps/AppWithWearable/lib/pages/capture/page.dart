import 'dart:async';
import 'dart:io';
import 'dart:math';

import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter_background_service/flutter_background_service.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';
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
import 'package:friend_private/utils/enums.dart';
import 'package:friend_private/utils/memories.dart';
import 'package:friend_private/utils/notifications.dart';
import 'package:friend_private/utils/stt/wav_bytes.dart';
import 'package:path_provider/path_provider.dart';
import 'package:permission_handler/permission_handler.dart';

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

class CapturePageState extends State<CapturePage> with AutomaticKeepAliveClientMixin, WidgetsBindingObserver {
  @override
  bool get wantKeepAlive => true;

  bool _hasTranscripts = false;
  RecordingState _state = RecordingState.stop;

  /// ----
  BTDeviceStruct? btDevice;
  List<TranscriptSegment> segments = [];

  StreamSubscription? audioBytesStream;
  WavBytesUtil? audioStorage;

  Timer? _backgroundTranscriptTimer;
  Timer? _memoryCreationTimer;
  bool memoryCreating = false;
  bool isTranscribing = false;

  DateTime? currentTranscriptStartedAt;
  DateTime? currentTranscriptFinishedAt;

  int lastOffset = 0;
  int partNumber = 1;
  int fileCount = 0;
  int iosDuration = 15;
  int androidDuration = 15;

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
    setState(() => isTranscribing = true);
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
    setState(() => isTranscribing = false);
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
    WidgetsBinding.instance.addObserver(this);
    SchedulerBinding.instance.addPostFrameCallback((_) async {
      debugPrint('SchedulerBinding.instance');
      initiateBytesProcessing();
      FlutterBackgroundService service = FlutterBackgroundService();
      if (await service.isRunning()) {
        setState(() {
          _state = RecordingState.record;
        });
        setState(() {
          iosDuration = 5;
          androidDuration = 15;
        });
      }
      await listenToBackgroundService();
    });
    _processCachedTranscript();
    // processTranscriptContent(context, '''a''', null);
    super.initState();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _memoryCreationTimer?.cancel();
    _backgroundTranscriptTimer?.cancel();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) async {
    final backgroundService = FlutterBackgroundService();
    if (state == AppLifecycleState.paused) {
      _backgroundTranscriptTimer?.cancel();
    }
    if (state == AppLifecycleState.resumed) {
      if (await backgroundService.isRunning()) {
        if (Platform.isAndroid) {
          await androidBgTranscribing(Duration(seconds: androidDuration), state);
        } else if (Platform.isIOS) {
          var path = await getApplicationDocumentsDirectory();
          var filePath = '${path.path}/recording_0.aac';

          await iosBgTranscribing(filePath, Duration(seconds: iosDuration), true);
        }
      }
    }
    super.didChangeAppLifecycleState(state);
  }

  Future androidBgTranscribing(Duration interval, AppLifecycleState state) async {
    final backgroundService = FlutterBackgroundService();

    _backgroundTranscriptTimer?.cancel();
    _backgroundTranscriptTimer = Timer.periodic(interval, (timer) async {
      if (state == AppLifecycleState.resumed) {
        try {
          var path = await getApplicationDocumentsDirectory();
          var filePath = '${path.path}/recording_$fileCount.aac';
          var file = File(filePath);
          backgroundService.invoke('timerUpdate', {'time': '0'});
          if (file.existsSync()) {
            Future.delayed(const Duration(milliseconds: 500), () async {
              setState(() {
                fileCount++;
              });
              backgroundService.invoke('timerUpdate', {'time': '30'});
              _processFileToTranscript(file);
              var paths = SharedPreferencesUtil().recordingPaths;
              SharedPreferencesUtil().recordingPaths = [...paths, filePath];
              setState(() {
                androidDuration = 30;
              });
            });
          } else {
            debugPrint('File does not exist.');
          }
        } catch (e) {
          debugPrint('Error reading and splitting file content: $e');
        }
      } else {
        debugPrint('not performing operation in background');
      }
    });
  }

  Future iosBgTranscribing(String filePath, Duration interval, bool shouldTranscribe) async {
    _backgroundTranscriptTimer?.cancel();
    _backgroundTranscriptTimer = Timer.periodic(interval, (timer) async {
      try {
        final file = File(filePath);

        if (await file.exists()) {
          // Get the current length of the file
          final currentLength = await file.length();

          if (currentLength > lastOffset) {
            // Read the new content from the file
            final content = await file.openRead(lastOffset, currentLength).toList();

            // Flatten the list of lists of bytes
            final newContent = content.expand((bytes) => bytes).toList();

            // Write the new content to a new file
            var path = await getApplicationDocumentsDirectory();
            final newFilePath = '${path.path}/recording_$partNumber.aac';
            final newFile = File(newFilePath);
            await newFile.writeAsBytes((newContent));
            debugPrint('New content written to $newFilePath');
            if (shouldTranscribe) {
              await _processFileToTranscript(newFile);
              var paths = SharedPreferencesUtil().recordingPaths;
              SharedPreferencesUtil().recordingPaths = [...paths, newFilePath];
            }

            // Update the last offset and part number
            setState(() {
              lastOffset = currentLength;
              partNumber++;
              iosDuration = 15;
            });
          }
        } else {
          debugPrint('File does not exist.');
        }
      } catch (e) {
        debugPrint('Error reading and splitting file content: $e');
      }
    });
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
        isTranscribing
            ? const Padding(
                padding: EdgeInsets.only(bottom: 176),
                child: Align(
                  alignment: Alignment.bottomCenter,
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      SizedBox(
                        height: 8,
                        width: 8,
                        child: CircularProgressIndicator(
                          strokeWidth: 2,
                          color: Colors.white,
                        ),
                      ),
                      SizedBox(width: 8),
                      Text('Transcribing...', style: TextStyle(color: Colors.white)),
                    ],
                  ),
                ),
              )
            : const SizedBox(),
        getPhoneMicRecordingButton(_recordingToggled, _state)
      ],
    );
  }

  _recordingToggled() async {
    if (_state == RecordingState.record) {
      await _stopRecording();
    } else if (_state == RecordingState.initialising) {
      debugPrint('initialising, have to wait');
    } else {
      setState(() => _state = RecordingState.initialising);
      await _startRecording();
    }
  }

  Future listenToBackgroundService() async {
    final backgroundService = FlutterBackgroundService();
    backgroundService.on('update').listen((event) async {
      if (event!['path'] != null && File(event['path']).existsSync()) {
        await _processFileToTranscript(File(event['path']));
      }
      debugPrint('received data message in feed: $event');
    }, onError: (e, s) {
      debugPrint('error listening for updates: $e, $s');
    }, onDone: () {
      debugPrint('background listen closed');
    });
    backgroundService.on('stateUpdate').listen((event) async {
      if (event!['state'] == 'recording') {
        setState(() => _state = RecordingState.record);
      } else if (event['state'] == 'stopped') {
        setState(() => _state = RecordingState.stop);
      } else if (event['state'] == 'initialising') {
        setState(() => _state = RecordingState.initialising);
      }
    }, onError: (e, s) {
      debugPrint('error listening for updates: $e, $s');
    }, onDone: () {
      debugPrint('background listen closed');
    });
  }

  _startRecording() async {
    if (Platform.isAndroid) {
      if (!await FlutterForegroundTask.isIgnoringBatteryOptimizations) {
        await FlutterForegroundTask.requestIgnoreBatteryOptimization();
      }
    }

    await Permission.microphone.request();
    await initializeBackgroundService();
  }

  _printFileSize(File file) async {
    int bytes = await file.length();
    var i = (log(bytes) / log(1024)).floor();
    const suffixes = ["B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB"];
    var size = '${(bytes / pow(1024, i)).toStringAsFixed(2)} ${suffixes[i]}';
    debugPrint('File size: $size');
  }

  _stopRecording() async {
    final service = FlutterBackgroundService();
    service.invoke("stop");
    if (Platform.isIOS) {
      var path = await getApplicationDocumentsDirectory();
      var filePath = '${path.path}/recording_0.aac';
      setState(() {
        iosDuration = 2;
      });
      await iosBgTranscribing(filePath, Duration(seconds: iosDuration), true);
      _backgroundTranscriptTimer?.cancel();
    } else if (Platform.isAndroid) {
      androidBgTranscribing(Duration(seconds: androidDuration), AppLifecycleState.resumed);
      _backgroundTranscriptTimer?.cancel();
    }

    Future.delayed(const Duration(seconds: 2), () async {
      var path = await getApplicationDocumentsDirectory();
      var filePaths = [];
      var files = path.listSync();
      if (Platform.isIOS) {
        for (var file in files) {
          if (file is File) {
            if (!file.path.contains('recording_0')) {
              filePaths.add(file.path);
            }
          }
        }
        if (SharedPreferencesUtil().transcriptSegments.isEmpty) {
          // if no segments, process all files (in case of multiple recordings)
          Future.forEach(filePaths, (f) async {
            await _processFileToTranscript(File(f));
          });
        } else {
          // if segments exist, process only the new files
          Future.forEach(filePaths, (f) async {
            if (!SharedPreferencesUtil().recordingPaths.contains(f)) {
              await _processFileToTranscript(File(f));
            }
          });
        }
      } else if (Platform.isAndroid) {
        for (var file in files) {
          if (file is File) {
            if (file.path.contains('recording_')) {
              if (!SharedPreferencesUtil().recordingPaths.contains(file.path)) {
                filePaths.add(file.path);
              }
            }
          }
          if (SharedPreferencesUtil().transcriptSegments.isEmpty) {
            // if no segments, process all files (in case of multiple recordings)
            Future.forEach(filePaths, (f) async {
              await _processFileToTranscript(File(f));
            });
          } else {
            // if segments exist, process only the new files
            Future.forEach(filePaths, (f) async {
              if (!SharedPreferencesUtil().recordingPaths.contains(f)) {
                await _processFileToTranscript(File(f));
              }
            });
          }
        }
      }
    });

    setState(() => _state = RecordingState.stop);
    if (segments.isNotEmpty) {
      setState(() => memoryCreating = true);
      _createMemory();
    }
  }
}
