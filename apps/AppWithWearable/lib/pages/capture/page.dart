import 'dart:async';
import 'dart:io';
import 'dart:math';

import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter_background_service/flutter_background_service.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:friend_private/backend/api_requests/api/llm.dart';
import 'package:friend_private/backend/api_requests/api/other.dart';
import 'package:friend_private/backend/api_requests/api/prompt.dart';
import 'package:friend_private/backend/api_requests/api/server.dart';
import 'package:friend_private/backend/api_requests/cloud_storage.dart';
import 'package:friend_private/backend/api_requests/stream_api_response.dart';
import 'package:friend_private/backend/database/memory.dart';
import 'package:friend_private/backend/database/message.dart';
import 'package:friend_private/backend/database/message_provider.dart';
import 'package:friend_private/backend/database/transcript_segment.dart';
import 'package:friend_private/backend/growthbook.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/bt_device.dart';
import 'package:friend_private/pages/capture/background_service.dart';
import 'package:friend_private/pages/capture/widgets/widgets.dart';
import 'package:friend_private/utils/audio/wav_bytes.dart';
import 'package:friend_private/utils/ble/communication.dart';
import 'package:friend_private/utils/enums.dart';
import 'package:friend_private/utils/features/backups.dart';
import 'package:friend_private/utils/memories/process.dart';
import 'package:friend_private/utils/other/notifications.dart';
import 'package:friend_private/utils/rag.dart';
import 'package:instabug_flutter/instabug_flutter.dart';
import 'package:path_provider/path_provider.dart';
import 'package:permission_handler/permission_handler.dart';
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

class CapturePageState extends State<CapturePage> with AutomaticKeepAliveClientMixin, WidgetsBindingObserver {
  @override
  bool get wantKeepAlive => true;

  bool _hasTranscripts = false;
  final record = AudioRecorder();
  RecordingState _state = RecordingState.stop;
  static const quietSecondsForMemoryCreation = 120;

  /// ----
  BTDeviceStruct? btDevice;
  List<TranscriptSegment> segments = [
//     TranscriptSegment(text: '''
//     Speaker 0: we they comprehend
//
// Speaker 1: i'd love to sir dig into each of those x risk s risk and irisk so can can you like linger in i risk what is that
//
// Speaker 0: so japanese concept of ikigai you find something which allows you to make money you are good at it and the society says we need it so like you have this awesome job you are podcaster gives you a lot of meaning you have a good life i assume you had that's what we want more people to find to have for many intellectuals it is their occupation which gives them a lot of meaning i'm a researcher philosopher scholar that means something to me in a world where an artist is not feeling appreciated because his art is just not competitive with what is produced by machines so a writer or scientist will lose a lot of that and that's a laurel we're talking about complete technological unemployment not losing 10% of jobs we're losing all jobs what do people do with all that free time what happens when everything society is built on is completely modified in 1 generation it's not a small process when we get to figure out how to live that new lifestyle but it's pretty quick in that world can't humans do what humans currently do with chess play each other even though ai systems are far superior at this time than just so we just create artificial fun fun focus maximize the fun and and let the the ai focus on the productivity it's an option i have a paper where i try to solve the value alignment problem for multiple agents and the solution to our work comp is to give everyone a personal virtual universe you can do whatever you want in that world you could be king you could be slave you decide what happens so it's basically a glorified visual game where you get to enjoy yourself and someone else takes care of your needs and substrate alignment is the only thing we need to solve we don't have to get 8 000 000 000 humans to agree on anything so okay so what why is that not a likely outcome why can't ai systems create video games for us to lose ourselves in each each with an individual video game universe
//
// Speaker 1: some people say that's what happened with the simulation
//
// Speaker 0: and we're playing that video again and now we're creating what maybe we're creating artificial threats for ourselves to be scared about because because fear is really exciting it allows us to play the video game more more vigorously
//
// Speaker 1: and some people choose to play on a more difficult level with more constraints some say okay i'm just gonna enjoy the game
//
// Speaker 0: privilege level absolutely okay what was that paper on multi agent value alignment personal universes personal universes so that's 1 of the possible outcomes but what what what in general is the idea of the paper so it's looking at multiple agents that are human ai like a hybrid system where there's humans and ai or they're looking at humans or just so this intelligent agents in order to solve alignment problem i'm trying to formalize this a little better usually we're talking about getting ais to do what we want which is not well defined i'm talking about creator of the system owner of that ai humanex as a whole we don't agree on much there is no universally accepted ethics morals across cultures religions people have individually very different preferences politically and such so even if we somehow manage all the other aspects programming those fuzzy concepts and getting to follow them closely we don't agree on what to program in so my solution was k we don't have to compromise on room temperature you have your universe i have mine whatever you want and if you like me you can invite me to visit the universe we don't have to be independent but the point is you can be and virtual reality is getting pretty good it's gonna hit a point where you can't tell the difference and if you can't tell if it's real or not what's the difference
//
// Speaker 1: so basically give up on value alignment create and size like the the multiverse theory this is create an entire universe for you where
//
// Speaker 0: your values
//
// Speaker 1: you still have to align with that individual they have to be happy in that simulation but it's a much easier problem to align with 1 agent versus 8 000 000 000 agents plus animals aliens
//
// Speaker 0: so you convert the multi agent problem into a single agent problem i'm proud to do that yeah okay is there any way to so okay that's giving up on the on the value of the problem but is there any way to solve the value of the problem there's a bunch of humans multiple human tens of humans or 8 000 000 000 humans that have very different set of values it seems contradicting
//
// Speaker 1: i haven't seen anyone explain what it means outside of kinda words which pack a lot make it good make it desirable make it something they don't regret but how do you specifically formalize those notions how do you program them in i haven't seen anyone make progress on that so far
//
// Speaker 0: but isn't that optimization journey that we're doing as a human civilization we're looking at geopolitics nations are in a state of anarchy with each other they start wars there's conflict and oftentimes they have a very different to that so we're essentially trying to solve the value on the problem with humans right but the examples you gave some for example 2 different religions saying this is our holy site and we are not willing to compromise it in any way if you can make 2 holy sites in virtual worlds you solve the problem but if you only have 1 it's not divisible you're kinda stuck there
//
// Speaker 1: but what if we want to be a tension with each other and that through that tension we understand ourselves and we understand the world so that that's the intellectual journey we're on we're on as a human civilization it will create into
//
// Speaker 0: and physical conflict and through that figure stuff out if we go back to that idea of simulation and this is entertainment kinda giving meaning to us the question is how much suffering is reasonable for a video game so yeah i don't mind you know a video game where i get haptic feedback there's a little bit of shaking unethical at least by our human standards it's possible to remove suffering if we're looking at human civilization as an optimization problem
//
// Speaker 1: so we know there are some humans who because of a mutation don't experience physical pain so at least physical pain can be mutated out reengineered out suffering in terms of meaning like you burn the only copy of my book is a little harder but even there you can manipulate your hedonic set point you can change change defaults you can reset
//     ''', speaker: 'SPEAKER_00', isUser: false, start: 0, end: 30)
  ];

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

  int elapsedSeconds = 0;

  Future<void> initiateBytesProcessing() async {
    debugPrint('initiateBytesProcessing: $btDevice');
    if (btDevice == null) return;
    // VadUtil vad = VadUtil();
    // await vad.init();
    // Variables to maintain state
    BleAudioCodec codec = await getDeviceCodec(btDevice!.id);

    WavBytesUtil toProcessBytes2 = WavBytesUtil(codec: codec);
    audioStorage = WavBytesUtil(codec: codec);
    audioBytesStream = await getBleAudioBytesListener(btDevice!.id, onAudioBytesReceived: (List<int> value) async {
      if (value.isEmpty) return;

      toProcessBytes2.storeFramePacket(value);
      // if (segments.isNotEmpty && wavBytesUtil2.hasFrames())
      audioStorage!.storeFramePacket(value);

      // if (toProcessBytes2.frames.length % 100 == 0) {
      //   debugPrint('Frames length: ${toProcessBytes2.frames.length / 100} seconds');
      // }
      // debugPrint('toProcessBytes2.frames.length: ${toProcessBytes2.frames.length}');
      if (toProcessBytes2.hasFrames() && toProcessBytes2.frames.length % 3000 == 0) {
        Tuple2<File, List<List<int>>> data = await toProcessBytes2.createWavFile(filename: 'temp.wav');
        // vad.containsVoice(data.item1);
        try {
          await _processFileToTranscript(data.item1);
          if (segments.isEmpty) audioStorage!.removeFramesRange(fromSecond: 0, toSecond: data.item2.length ~/ 100);
          if (segments.isNotEmpty) elapsedSeconds += data.item2.length ~/ 100;
          // uploadFile(data.item1, prefixTimestamp: true);
        } catch (e, stacktrace) {
          // TODO: if it fails, so if more than 30 seconds waiting to be processed, createMemory should wait until < 30 seconds
          CrashReporting.reportHandledCrash(
            e,
            stacktrace,
            level: NonFatalExceptionLevel.warning,
            userAttributes: {'seconds': (data.item2.length ~/ 100).toString()},
          );
          debugPrint('Error: e.toString() ${e.toString()}');
          toProcessBytes2.insertAudioBytes(data.item2);
        }
      }
    });
  }

  _processFileToTranscript(File f) async {
    setState(() => isTranscribing = true);
    List<TranscriptSegment> newSegments;
    if (GrowthbookUtil().hasTranscriptServerFeatureOn() == true) {
      newSegments = await transcribe(f, SharedPreferencesUtil().uid);
    } else {
      newSegments = await deepgramTranscribe(f);
    }
    // debugPrint('newSegments: ${newSegments.length} + elapsedSeconds: $elapsedSeconds');
    TranscriptSegment.combineSegments(segments, newSegments, elapsedSeconds: elapsedSeconds); // combines b into a
    if (newSegments.isNotEmpty) {
      SharedPreferencesUtil().transcriptSegments = segments;
      setState(() {});
      setHasTranscripts(true);
      debugPrint('Memory creation timer restarted');
      _memoryCreationTimer?.cancel();
      _memoryCreationTimer = Timer(const Duration(seconds: quietSecondsForMemoryCreation), () => _createMemory());
      currentTranscriptStartedAt ??= DateTime.now().subtract(const Duration(seconds: 30));
      currentTranscriptFinishedAt = DateTime.now();
    }
    _doProcessingOfInstructions();
    setState(() => isTranscribing = false);
  }

  Map<int, int> processedSegments = {};

  _doProcessingOfInstructions() async {
    for (var element in segments) {
      var hotWords = ['hey friend', 'hey frend', 'hey fren', 'hey bren', 'hey frank'];
      for (var option in hotWords) {
        if (element.text.toLowerCase().contains(option)) {
          debugPrint('Hey Friend detected');
          var index = element.text.lastIndexOf(option);
          if (processedSegments.containsKey(element.id) && processedSegments[element.id] == index) continue;

          var substring = element.text.substring(index + option.length);
          var words = substring.split(' ');
          if (words.length >= 5) {
            debugPrint('Hey Friend detected and 10 words after');
            String message = await executeGptPrompt('''
          The following is an instruction the user sent as a voice message by saying "Hey Friend" + instruction.
          Extract the only the instruction the user is asking in 5 to 10 words.
          
          ${element.text.substring(index)}''');
            debugPrint('Message: $message');

            MessageProvider().saveMessage(Message(DateTime.now(), message, 'human'));
            widget.refreshMessages();
            dynamic ragInfo = await retrieveRAGContext(message);
            String ragContext = ragInfo[0];
            List<Memory> memories = ragInfo[1].cast<Memory>();
            String body = qaStreamedBody(ragContext, await MessageProvider().retrieveMostRecentMessages(limit: 10));
            var response = await executeGptPrompt(body);
            var aiMessage = Message(DateTime.now(), response, 'ai');
            aiMessage.memories.addAll(memories);
            MessageProvider().saveMessage(aiMessage);
            widget.refreshMessages();
            processedSegments[element.id] = index;
          }
        }
      }
    }
  }

  void resetState({bool restartBytesProcessing = true, BTDeviceStruct? btDevice}) {
    debugPrint('resetState: $restartBytesProcessing');
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
      var secs = !forcedCreation ? quietSecondsForMemoryCreation : 0;
      if (audioStorage != null) {
        file = (await audioStorage!.createWavFile()).item1;
        uploadFile(file);
      }
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
    elapsedSeconds = 0;
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
          iosDuration = 5;
          androidDuration = 15;
        });
        if (Platform.isAndroid) {
          await androidBgTranscribing(Duration(seconds: androidDuration), AppLifecycleState.resumed);
        } else if (Platform.isIOS) {
          var path = await getApplicationDocumentsDirectory();
          var filePath = '${path.path}/recording_0.aac';

          await iosBgTranscribing(filePath, Duration(seconds: iosDuration), true);
        }
        setState(() {
          _state = RecordingState.record;
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
      debugPrint('timer triggered at ${DateTime.now()}');
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
              iosDuration = 10;
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
          speechProfileWidget(context, setState),
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
    setState(() {
      _state = RecordingState.stop;
      isTranscribing = true;
    });
    if (Platform.isIOS) {
      var path = await getApplicationDocumentsDirectory();
      var filePath = '${path.path}/recording_0.aac';
      setState(() {
        iosDuration = 1;
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
    }).then((value) async {
      setState(() => isTranscribing = false);
      if (segments.isNotEmpty) {
        setState(() => memoryCreating = true);
        await _createMemory();
      }
    });
  }
}
