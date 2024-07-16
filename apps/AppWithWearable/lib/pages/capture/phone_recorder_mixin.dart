import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_background_service/flutter_background_service.dart';
import 'package:friend_private/backend/database/transcript_segment.dart';
import 'package:path_provider/path_provider.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:friend_private/utils/enums.dart';
import 'package:friend_private/pages/capture/background_service.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';

import 'microphone_transcribing_util.dart';

mixin PhoneRecorderMixin<T extends StatefulWidget> on State<T> {
  int lastOffset = 0;
  int partNumber = 1;
  int fileCount = 0;
  int iosDuration = 30;
  int androidDuration = 30;
  bool isTranscribing = false;
  RecordingState recordingState = RecordingState.stop;
  Timer? backgroundTranscriptTimer;

  startRecording(Function processFileToTranscript) async {
    setState(() {
      fileCount = 0;
    });
    if (Platform.isAndroid) {
      if (!await FlutterForegroundTask.isIgnoringBatteryOptimizations) {
        await FlutterForegroundTask.requestIgnoreBatteryOptimization();
      }
    }
    await Permission.microphone.request();
    await initializeBackgroundService();
    if (backgroundTranscriptTimer != null && !backgroundTranscriptTimer!.isActive) {
      debugPrint('Timer is not active');
      if (recordingState == RecordingState.record) {
        if (Platform.isIOS) {
          setState(() {
            iosDuration = 30;
          });
          await iosBgTranscribing(
            Duration(seconds: iosDuration),
            true,
            processFileToTranscript,
          );
        } else if (Platform.isAndroid) {
          setState(() {
            androidDuration = 30;
          });
          await androidBgTranscribing(
              Duration(seconds: androidDuration), AppLifecycleState.resumed, processFileToTranscript);
        }
      }
    }
  }

  Future<void> waitForTranscriptionToFinish() async {
    while (isTranscribing) {
      debugPrint('Waiting for transcription to finish...');
      await Future.delayed(const Duration(milliseconds: 200));
    }
    debugPrint('Transcription finished');
  }

  stopRecording(Function processFileToTranscript, List<TranscriptSegment> segments, VoidCallback memoryUpdate) async {
    final service = FlutterBackgroundService();
    service.invoke("stop");
    setState(() {
      recordingState = RecordingState.stop;
    });
    if (Platform.isIOS) {
      await waitForTranscriptionToFinish();
      await iosBgCallback(
        shouldTranscribe: false,
        lastOffset: lastOffset,
        partNumber: partNumber,
        processFileToTranscript: processFileToTranscript,
        updateState: (currentLength) {
          setState(() {
            lastOffset = currentLength;
            partNumber++;
            iosDuration = 10;
            isTranscribing = false;
          });
        },
      );
      backgroundTranscriptTimer?.cancel();
      setState(() {
        partNumber = 1;
      });
    } else if (Platform.isAndroid) {
      backgroundTranscriptTimer?.cancel();
    }

    if (Platform.isIOS) {
      await waitForTranscriptionToFinish();
      await transcribeAfterStopiOS(
        processFileToTranscript: processFileToTranscript,
        updateState: () {
          setState(() {
            isTranscribing = false;
          });
        },
        memory: memoryUpdate,
        segments: segments,
      );
    } else if (Platform.isAndroid) {
      setState(() {
        isTranscribing = true;
      });
      Future.delayed(const Duration(seconds: 2), () async {
        await transcribeAfterStopAndroid(
          processFileToTranscript: processFileToTranscript,
          updateState: () {
            setState(() {
              isTranscribing = false;
            });
          },
          memory: memoryUpdate,
          segments: segments,
        );
      });
    }
  }

  Future phonerecorderInit(Function processTranscript) async {
    FlutterBackgroundService service = FlutterBackgroundService();
    if (await service.isRunning()) {
      setState(() {
        iosDuration = 30;
        androidDuration = 30;
      });
      if (Platform.isAndroid) {
        await androidBgTranscribing(Duration(seconds: androidDuration), AppLifecycleState.resumed, processTranscript);
      } else if (Platform.isIOS) {
        await iosBgTranscribing(Duration(seconds: iosDuration), true, processTranscript);
      }
      setState(() {
        recordingState = RecordingState.record;
      });
    }
    final backgroundService = FlutterBackgroundService();
    backgroundService.on('stateUpdate').listen((event) async {
      if (event!['state'] == 'recording') {
        setState(() {
          recordingState = RecordingState.record;
        });
      } else if (event['state'] == 'stopped') {
        setState(() {
          recordingState = RecordingState.stop;
        });
      } else if (event['state'] == 'initialising') {
        setState(() {
          recordingState = RecordingState.initialising;
        });
      }
    }, onError: (e, s) {
      debugPrint('error listening for updates: $e, $s');
    }, onDone: () {
      debugPrint('background listen closed');
    });
  }

  @override
  void dispose() {
    backgroundTranscriptTimer?.cancel();
    super.dispose();
  }

  Future iosBgTranscribing(Duration interval, bool shouldTranscribe, Function processFileToTranscript) async {
    backgroundTranscriptTimer?.cancel();
    backgroundTranscriptTimer = Timer.periodic(interval, (timer) async {
      debugPrint('timer triggered at ${DateTime.now()}');
      var path = await getApplicationDocumentsDirectory();
      var filePath = '${path.path}/recording_0.wav';
      try {
        debugPrint('isTranscribing: $isTranscribing');
        if (isTranscribing) return;
        await iosBgCallback(
          shouldTranscribe: shouldTranscribe,
          lastOffset: lastOffset,
          partNumber: partNumber,
          processFileToTranscript: processFileToTranscript,
          updateState: (currentLength) {
            setState(() {
              lastOffset = currentLength;
              partNumber++;
              iosDuration = 10;
              isTranscribing = false;
            });
          },
        );
      } catch (e) {
        debugPrint('Error for file: $filePath');
        debugPrint('Error reading and splitting file content: $e');
      }
    });
  }

  Future androidBgTranscribing(Duration interval, AppLifecycleState state, Function processFileToTranscript) async {
    final backgroundService = FlutterBackgroundService();
    backgroundTranscriptTimer?.cancel();
    backgroundTranscriptTimer = Timer.periodic(interval, (timer) async {
      if (state == AppLifecycleState.resumed) {
        try {
          if (isTranscribing) return;
          await androidBgCallback(
            backgroundService: backgroundService,
            fileCount: fileCount,
            updateState: () {
              setState(() {
                fileCount++;
                androidDuration = 30;
              });
            },
            processFileToTranscript: processFileToTranscript,
          );
        } catch (e) {
          debugPrint('Error changing recorder to new file: $e');
        }
      } else {
        debugPrint('not performing operation in background');
      }
    });
  }
}
