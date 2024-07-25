import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_background_service/flutter_background_service.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:friend_private/backend/database/transcript_segment.dart';
import 'package:friend_private/pages/capture/background_service.dart';
import 'package:friend_private/utils/enums.dart';
import 'package:friend_private/utils/websockets.dart';
import 'package:path_provider/path_provider.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:record/record.dart';
import 'package:web_socket_channel/io.dart';

import 'microphone_transcribing_util.dart';

// TODO: to be fixed.
// - handle errors processing, no internet or anything
// - Fix backend, use multichannel instead of single channel when recorded from device

mixin PhoneRecorderMixin<T extends StatefulWidget> on State<T> {
  int lastOffset = 0;
  int partNumber = 1;
  int fileCount = 0;
  int iosDuration = 30;
  int androidDuration = 30;
  bool isTranscribing = false;
  RecordingState recordingState = RecordingState.stop;
  Timer? backgroundTranscriptTimer;

  // stream related
  List<Uint8List> audioChunks = [];
  int totalBytes = 0;
  Timer? timer;
  var record = AudioRecorder();

  startStreamRecording(WebsocketConnectionStatus wsConnectionState, IOWebSocketChannel? websocketChannel) async {
    await Permission.microphone.request();
    debugPrint("input device: ${await record.listInputDevices()}");
    InputDevice? inputDevice;
    if (Platform.isIOS) {
      inputDevice = const InputDevice(id: "Built-In Microphone", label: "iPhone Microphone");
    } else {}
    var stream = await record.startStream(
        RecordConfig(encoder: AudioEncoder.pcm16bits, sampleRate: 16000, numChannels: 1, device: inputDevice));
    setState(() => recordingState = RecordingState.record);
    stream.listen((data) async {
      if (wsConnectionState == WebsocketConnectionStatus.connected) {
        websocketChannel?.sink.add(data);
      }
    });
  }

  stopStreamRecording(WebsocketConnectionStatus wsConnectionState, IOWebSocketChannel? websocketChannel) async {
    if (timer != null) {
      timer?.cancel();
    }
    if (await record.isRecording()) {
      await record.stop();
    }

    if (wsConnectionState == WebsocketConnectionStatus.connected) {
      websocketChannel?.sink.close();
    }

    setState(() => recordingState = RecordingState.stop);
  }

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
    debugPrint('Timer is not active and null');
    await waitForTimerToFinish();
    Future.delayed(const Duration(seconds: 2), () async {
      debugPrint('Recording state is record');
      setState(() {
        iosDuration = 30;
        androidDuration = 30;
      });
      if (Platform.isIOS) {
        await iosBgTranscribing(
          Duration(seconds: iosDuration),
          true,
          processFileToTranscript,
        );
      } else if (Platform.isAndroid) {
        await androidBgTranscribing(
          Duration(seconds: androidDuration),
          AppLifecycleState.resumed,
          processFileToTranscript,
        );
      }
    });
  }

  Future<void> waitForTimerToFinish() async {
    while (backgroundTranscriptTimer?.isActive ?? false) {
      debugPrint('Waiting for timer to finish...');
      await Future.delayed(const Duration(milliseconds: 500));
    }
    debugPrint('Timer finished');
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
            iosDuration = 5;
            isTranscribing = false;
          });
        },
      );
      backgroundTranscriptTimer?.cancel();
      setState(() {
        partNumber = 1;
        lastOffset = 0;
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

  Future onAppIsResumed(Function processTranscript) async {
    FlutterBackgroundService service = FlutterBackgroundService();
    await bgServiceNotifier();
    if (await service.isRunning()) {
      setState(() {
        iosDuration = 10;
        androidDuration = 10;
      });
      if (Platform.isAndroid) {
        await androidBgTranscribing(Duration(seconds: androidDuration), AppLifecycleState.resumed, processTranscript);
      } else if (Platform.isIOS) {
        await iosBgTranscribing(Duration(seconds: iosDuration), true, processTranscript);
      }
    }
  }

  Future phoneRecorderInit(Function processTranscript) async {
    FlutterBackgroundService service = FlutterBackgroundService();
    await bgServiceNotifier();
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

      // setState(() {
      //   recordingState = RecordingState.record;
      // });
    }
  }

  Future bgServiceNotifier() async {
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
  void dispose() async {
    backgroundTranscriptTimer?.cancel();
    timer?.cancel();
    await record.dispose();
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
              iosDuration = 30;
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
