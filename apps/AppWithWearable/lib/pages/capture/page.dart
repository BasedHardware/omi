import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';
import 'dart:typed_data';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:friend_private/backend/api_requests/api/other.dart';
import 'package:friend_private/backend/api_requests/api/prompt.dart';
import 'package:friend_private/backend/api_requests/api/server.dart';
import 'package:friend_private/backend/api_requests/cloud_storage.dart';
import 'package:friend_private/backend/database/memory.dart';
import 'package:friend_private/backend/database/message.dart';
import 'package:friend_private/backend/database/message_provider.dart';
import 'package:friend_private/backend/database/transcript_segment.dart';
import 'package:friend_private/backend/growthbook.dart';
import 'package:friend_private/backend/mixpanel.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/bt_device.dart';
import 'package:friend_private/pages/capture/widgets/widgets.dart';
import 'package:friend_private/utils/audio/wav_bytes.dart';
import 'package:friend_private/utils/ble/communication.dart';
import 'package:friend_private/utils/features/backups.dart';
import 'package:friend_private/utils/memories/integrations.dart';
import 'package:friend_private/utils/memories/process.dart';
import 'package:friend_private/utils/other/notifications.dart';
import 'package:friend_private/utils/websockets.dart';
import 'package:instabug_flutter/instabug_flutter.dart';
import 'package:internet_connection_checker_plus/internet_connection_checker_plus.dart';
import 'package:record/record.dart';
import 'package:tuple/tuple.dart';
import 'package:uuid/uuid.dart';
import 'package:web_socket_channel/io.dart';

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

  bool _streamingTranscriptEnabled = false;

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

  StreamSubscription? _bleBytesStream;
  WavBytesUtil? audioStorage;

  Timer? _memoryCreationTimer;
  bool memoryCreating = false;

  DateTime? currentTranscriptStartedAt;
  DateTime? currentTranscriptFinishedAt;

  // ----
  WebsocketConnectionStatus wsConnectionState = WebsocketConnectionStatus.notConnected;
  bool websocketReconnecting = false;
  IOWebSocketChannel? _wsChannel;
  InternetStatus? _internetStatus;

  late StreamSubscription<InternetStatus> _internetListener;
  String conversationId = const Uuid().v4(); // used only for transcript segment plugins

  _processCachedTranscript() async {
    debugPrint('_processCachedTranscript');
    var segments = SharedPreferencesUtil().transcriptSegments;
    if (segments.isEmpty) return;
    String transcript = TranscriptSegment.segmentsAsString(SharedPreferencesUtil().transcriptSegments);
    processTranscriptContent(
      context,
      transcript,
      SharedPreferencesUtil().transcriptSegments,
      null,
      retrievedFromCache: true,
      sendMessageToChat: sendMessageToChat,
    ).then((m) {
      if (m != null && !m.discarded) executeBackupWithUid();
    });
    SharedPreferencesUtil().transcriptSegments = [];
    // TODO: include created at and finished at for this cached transcript
  }

  int elapsedSeconds = 0;
  double streamStartedAtSecond = 0;

  Future<void> initiateBytesStreamingProcessing() async {
    if (btDevice == null) return;

    Tuple3<IOWebSocketChannel?, StreamSubscription?, WavBytesUtil> data = await streamingTranscript(
        btDevice: btDevice!,
        onWebsocketConnectionSuccess: () {
          setState(() {
            wsConnectionState = WebsocketConnectionStatus.connected;
            websocketReconnecting = false;
            _reconnectionAttempts = 0; // Reset counter on successful connection
          });
        },
        onWebsocketConnectionFailed: (err) {
          // connection couldn't be initiated for some reason.
          setState(() {
            wsConnectionState = WebsocketConnectionStatus.failed;
            websocketReconnecting = false;
          });
          _reconnectWebSocket();
        },
        onWebsocketConnectionClosed: (int? closeCode, String? closeReason) {
          // connection was closed, either on resetState, or by backend, or by some other reason.
          setState(() {
            wsConnectionState = WebsocketConnectionStatus.closed;
          });
          if (closeCode != 1000) {
            // attempt to reconnect
            _reconnectWebSocket();
          }
        },
        onWebsocketConnectionError: (err) {
          // connection was okay, but then failed.
          setState(() {
            wsConnectionState = WebsocketConnectionStatus.error;
            websocketReconnecting = false;
          });
          _reconnectWebSocket();
        },
        onMessageReceived: (List<TranscriptSegment> newSegments) {
          if (segments.isEmpty && newSegments.isNotEmpty) {
            debugPrint('newSegments: ${newSegments.last} ${audioStorage!.frames.length ~/ 100}');
            // TODO: small bug
            // - When memory i is created, newSegment.start will still contain the whole websocket time,
            //   so we are removing all audio here, first phrase/ word will be lost from created audio.
            audioStorage?.removeFramesRange(fromSecond: 0, toSecond: max((newSegments.last.end - 1).toInt(), 0));
            streamStartedAtSecond = newSegments[0].start;
          }
          TranscriptSegment.combineSegments(segments, newSegments, streamStartedAtSecond: streamStartedAtSecond);
          if (newSegments.isNotEmpty) {
            SharedPreferencesUtil().transcriptSegments = segments;
            setHasTranscripts(true);
            debugPrint('Memory creation timer restarted');
            _memoryCreationTimer?.cancel();
            _memoryCreationTimer = Timer(const Duration(seconds: quietSecondsForMemoryCreation), () => _createMemory());
            currentTranscriptStartedAt ??= DateTime.now();
            currentTranscriptFinishedAt = DateTime.now();
          }
          setState(() {});
        });

    _wsChannel = data.item1;
    _bleBytesStream = data.item2;
    audioStorage = data.item3;
  }

  int _reconnectionAttempts = 0;

  Future<void> _reconnectWebSocket() async {
    // TODO: fix function
    // - we are closing so that this triggers a new reconnect, but maybe it shouldn't, as this will trigger error sometimes, and close
    //   causing 4 up to 5 reconnect attempts, double notification, double memory creation and so on.
    // if (websocketReconnecting) return;

    if (_reconnectionAttempts >= 3) {
      setState(() => websocketReconnecting = false);
      // TODO: reset here to 0? or not, this could cause infinite loop if it's called in parallel from 2 distinct places
      debugPrint('Max reconnection attempts reached');
      clearNotification(2);
      createNotification(
        notificationId: 2,
        title: 'Error Generating Transcription',
        body: 'Check your internet connection and try again. If the problem persists, restart the app.',
      );
      resetState(restartBytesProcessing: false); // Should trigger this only once, and then disconnects websocket

      return;
    }
    setState(() {
      websocketReconnecting = true;
    });
    _reconnectionAttempts++;
    await Future.delayed(const Duration(seconds: 3)); // Reconnect delay
    debugPrint('Attempting to reconnect $_reconnectionAttempts time');
    // _wsChannel?.
    _bleBytesStream?.cancel();
    _wsChannel?.sink.close(); // trigger one more reconnectWebSocket call
    await initiateBytesStreamingProcessing();
  }

  List<Tuple2<String, String>> photos = [];
  ImageBytesUtil imageBytesUtil = ImageBytesUtil();

  Future<void> openGlassProcessing() async {
    _bleBytesStream = await getBleImageBytesListener(btDevice!.id, onImageBytesReceived: (List<int> value) async {
      if (value.isEmpty) return;
      // print(value);
      Uint8List data = Uint8List.fromList(value);
      Uint8List? completedImage = imageBytesUtil.processChunk(data);
      if (completedImage != null && completedImage.isNotEmpty) {
        debugPrint('Completed image size: ${completedImage.length}');
        getPhotoDescription(completedImage).then((description) {
          photos.add(Tuple2(base64Encode(completedImage), description));
          setState(() {});
          debugPrint('photos: ${photos.length}');
          setHasTranscripts(true);
          // if (photos.length % 10 == 0) determinePhotosToKeep(photos);
        });
      }
    });
    await cameraStopPhotoController(btDevice!.id);
    await cameraStartPhotoController(btDevice!.id);
  }

  bool isGlasses = false;

  Future<void> initiateBytesProcessing() async {
    debugPrint('initiateBytesProcessing: $btDevice');
    if (btDevice == null) return;
    print(SharedPreferencesUtil().deviceName);
    isGlasses = await hasPhotoStreamingCharacteristic(btDevice!.id);
    if (isGlasses) return await openGlassProcessing();

    BleAudioCodec codec = await getAudioCodec(btDevice!.id);
    if (codec == BleAudioCodec.unknown) {
      // TODO: disconnect and show error
    }

    bool firstTranscriptMade = SharedPreferencesUtil().firstTranscriptMade;

    WavBytesUtil toProcessBytes2 = WavBytesUtil(codec: codec);
    audioStorage = WavBytesUtil(codec: codec);
    _bleBytesStream = await getBleAudioBytesListener(
      btDevice!.id,
      onAudioBytesReceived: (List<int> value) async {
        if (value.isEmpty) return;

        toProcessBytes2.storeFramePacket(value);
        audioStorage!.storeFramePacket(value);
        if (toProcessBytes2.hasFrames() && toProcessBytes2.frames.length % 3000 == 0) {
          if (_internetStatus == InternetStatus.disconnected) {
            debugPrint('No internet connection, not processing audio');
            return;
          }
          if (await WavBytesUtil.tempWavExists()) return; // wait til that one is fully processed

          Tuple2<File, List<List<int>>> data = await toProcessBytes2.createWavFile(filename: 'temp.wav');
          try {
            await _processFileToTranscript(data.item1);
            if (segments.isEmpty) audioStorage!.removeFramesRange(fromSecond: 0, toSecond: data.item2.length ~/ 100);
            if (segments.isNotEmpty) elapsedSeconds += data.item2.length ~/ 100;
            if (segments.isNotEmpty && !firstTranscriptMade) {
              SharedPreferencesUtil().firstTranscriptMade = true;
              MixpanelManager().firstTranscriptMade();
              firstTranscriptMade = true;
            }

            // uploadFile(data.item1, prefixTimestamp: true);
          } catch (e, stacktrace) {
            debugPrint('Error processing 30 seconds frame');
            print(e); // don't change this to debugPrint
            CrashReporting.reportHandledCrash(
              e,
              stacktrace,
              level: NonFatalExceptionLevel.warning,
              userAttributes: {'seconds': (data.item2.length ~/ 100).toString()},
            );
            toProcessBytes2.insertAudioBytes(data.item2);
          }
          WavBytesUtil.deleteTempWav();
        }
      },
    );
    if (_bleBytesStream == null) {
      // TODO: error out and disconnect
    }
  }

  _processFileToTranscript(File f) async {
    List<TranscriptSegment> newSegments;
    if (GrowthbookUtil().hasTranscriptServerFeatureOn() == true) {
      newSegments = await transcribe(f);
    } else {
      newSegments = await deepgramTranscribe(f);
    }
    // debugPrint('newSegments: ${newSegments.length} + elapsedSeconds: $elapsedSeconds');
    TranscriptSegment.combineSegments(segments, newSegments, elapsedSeconds: elapsedSeconds); // combines b into a
    if (newSegments.isNotEmpty) {
      triggerTranscriptSegmentReceivedEvents(newSegments, conversationId, sendMessageToChat: sendMessageToChat);
      SharedPreferencesUtil().transcriptSegments = segments;
      setState(() {});
      setHasTranscripts(true);
      debugPrint('Memory creation timer restarted');
      _memoryCreationTimer?.cancel();
      _memoryCreationTimer = Timer(const Duration(seconds: quietSecondsForMemoryCreation), () => _createMemory());
      currentTranscriptStartedAt ??= DateTime.now().subtract(const Duration(seconds: 30));
      currentTranscriptFinishedAt = DateTime.now();
    }
  }

  void resetState({bool restartBytesProcessing = true, BTDeviceStruct? btDevice}) {
    debugPrint('resetState: $restartBytesProcessing');
    _bleBytesStream?.cancel();
    _memoryCreationTimer?.cancel();
    _wsChannel?.sink.close(1000);
    if (!restartBytesProcessing && (segments.isNotEmpty || photos.isNotEmpty)) _createMemory(forcedCreation: true);
    if (btDevice != null) setState(() => this.btDevice = btDevice);
    if (restartBytesProcessing) {
      if (_streamingTranscriptEnabled) {
        initiateBytesStreamingProcessing();
      } else {
        initiateBytesProcessing();
      }
    }
  }

  void sendMessageToChat(Message message, Memory? memory) {
    if (memory != null) message.memories.add(memory);
    MessageProvider().saveMessage(message);
    widget.refreshMessages();
  }

  _createMemory({bool forcedCreation = false}) async {
    if (memoryCreating) return;
    // TODO: should clean variables here? and keep them locally?
    setState(() => memoryCreating = true);
    String transcript = TranscriptSegment.segmentsAsString(segments);
    debugPrint('_createMemory transcript: \n$transcript');
    File? file;
    if (audioStorage?.frames.isNotEmpty == true) {
      try {
        var secs = !forcedCreation ? quietSecondsForMemoryCreation : 0;
        file = (await audioStorage!.createWavFile(removeLastNSeconds: secs)).item1;
        uploadFile(file);
      } catch (e) {} // in case was a local recording and not a BLE recording
    }
    Memory? memory = await processTranscriptContent(
      context,
      transcript,
      segments,
      file?.path,
      startedAt: currentTranscriptStartedAt,
      finishedAt: currentTranscriptFinishedAt,
      photos: photos, // TODO: determinephotosToKeep(photos);
      sendMessageToChat: sendMessageToChat,
    );
    debugPrint(memory.toString());
    // TODO: backup when useful memory created, maybe less later, 2k memories occupy 3MB in the json payload
    if (memory != null && !memory.discarded) executeBackupWithUid();
    if (memory != null && !memory.discarded && SharedPreferencesUtil().postMemoryNotificationIsChecked) {
      postMemoryCreationNotification(memory).then((r) {
        // r = 'Hi there testing notifications stuff';
        debugPrint('Notification response: $r');
        if (r.isEmpty) return;
        sendMessageToChat(Message(DateTime.now(), r, 'ai'), memory);
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
    streamStartedAtSecond = 0;
    photos = [];
    conversationId = const Uuid().v4();
  }

  setHasTranscripts(bool hasTranscripts) {
    if (_hasTranscripts == hasTranscripts) return;
    setState(() => _hasTranscripts = hasTranscripts);
  }

  @override
  void initState() {
    btDevice = widget.device;
    _streamingTranscriptEnabled = GrowthbookUtil().hasStreamingTranscriptFeatureOn();
    WavBytesUtil.clearTempWavFiles();
    SchedulerBinding.instance.addPostFrameCallback((_) async {
      debugPrint('SchedulerBinding.instance');
      if (_streamingTranscriptEnabled) {
        initiateBytesStreamingProcessing();
      } else {
        initiateBytesProcessing();
      }
    });
    _processCachedTranscript();
    _internetListener = InternetConnection().onStatusChange.listen((InternetStatus status) {
      switch (status) {
        case InternetStatus.connected:
          _internetStatus = InternetStatus.connected;
          break;
        case InternetStatus.disconnected:
          _internetStatus = InternetStatus.disconnected;
          _memoryCreationTimer
              ?.cancel(); // so if you have a memory in progress, it doesn't get created, and you don't lose the remaining bytes.
          break;
      }
    });
    // processTranscriptContent(context, '''a''', null);
    super.initState();
  }

  @override
  void dispose() {
    record.dispose();
    _bleBytesStream?.cancel();
    _memoryCreationTimer?.cancel();
    _wsChannel?.sink.close(1000);
    _internetListener.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    // super.build(context);
    return Stack(
      children: [
        ListView(
          children: [
            speechProfileWidget(context, setState, () => resetState(restartBytesProcessing: true)),
            ...getConnectionStateWidgets(context, _hasTranscripts, widget.device),
            getTranscriptWidget(memoryCreating, segments, photos, widget.device),
            if (wsConnectionState == WebsocketConnectionStatus.error ||
                wsConnectionState == WebsocketConnectionStatus.failed)
              getWebsocketErrorWidget(),
            const SizedBox(height: 16),
          ],
        ),
        getPhoneMicRecordingButton(_recordingToggled, _state)
      ],
    );
  }

  _recordingToggled() async {}
}
