import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:friend_private/backend/api_requests/api_calls.dart';
import 'package:friend_private/backend/api_requests/cloud_storage.dart';
import 'package:friend_private/backend/database/memory.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/bt_device.dart';
import 'package:friend_private/backend/storage/message.dart';
import 'package:friend_private/backend/storage/segment.dart';
import 'package:friend_private/utils/ble/communication.dart';
import 'package:friend_private/utils/memories.dart';
import 'package:friend_private/utils/notifications.dart';
import 'package:friend_private/utils/stt/wav_bytes.dart';
import 'package:uuid/uuid.dart';

class TranscriptWidget extends StatefulWidget {
  final Function refreshMemories;
  final Function(bool) setHasTranscripts;
  final Function(Message) addMessage;

  const TranscriptWidget({
    super.key,
    required this.btDevice,
    required this.refreshMemories,
    required this.setHasTranscripts,
    required this.addMessage,
  });

  final BTDeviceStruct? btDevice;

  @override
  State<TranscriptWidget> createState() => TranscriptWidgetState();
}

class TranscriptWidgetState extends State<TranscriptWidget> {
  BTDeviceStruct? btDevice;
  List<TranscriptSegment> segments = [
    TranscriptSegment(text: '''
  Speaker 0: have a minute i'm thinking of building the backup feature so people don't lose their memory for like any time mhmm is it export or the problem is that export is not for non deaf or for non techy people like it is for like what like we need to make sure people come back to make sure people come back to the app and not to their text why you just called them yes but like i was thinking we have they have a password and they encrypt that but they just put a password yeah i understand we encrypt that and say that some some way now they are encrypted so it's just a random string that we cannot access and then whenever they want to get back to it they just put their id and password the problem is that open source community will not like it do you work for so you work for everyone by default yes by default mhmm what i think it should be is i think it should be a seasonal model is saving all day by default yes yes the problem that that is that made more right i mean let's say we are not like are we charging yet no okay yeah so let's now the second part i we can then opt in for battle can you start that way right yeah we wouldn't have to worry ever about losing memory thread yeah it should be worse it should be worse yeah because people for example yes people are losing the memories we have to make sure that migrations to for example adding new fields to the memory object like work well okay yeah i think i'll open for backup i will leave it by default will leave it by default well well now everyone has to open and i know they they have to set their their own password to encrypt the file yeah being with that is when they want to import memory because i think like yes you have the backup but maybe you don't have them in the app like and you have like right so you have to be able to inform them in some way but like go ahead yeah it doesn't back it say you're in yeah or should so i think realistically unfortunately we're always kept to be worried about people losing something mhmm which is why to determine some super simple structure this will be over the same network which will remove for us the kentucky and the like losing the you can just correct me if i'm wrong but i understand the biggest like issue is that let's say people will let's say people will lose like extra items for example like names both memories and stuff correct or no mhmm not every but like some pieces people will change something and so on 

Speaker 1: yeah they could change something or maybe there there was an update that they had to install the app for example because sometimes apple asked you to install install the app mhmm they do that thing mhmm 

Speaker 0: i think you can't uninstall app but also keep the data sorry i didn't know yes we have to rely on like yeah i think yeah we should do the compass yeah i think that's for the whole one but unfortunately it will be proprietary for the app local so 

Speaker 1: and for the important thing do you agree that they gave us important because if it's just export we can just create an export button and they get the the strings and put it yeah 

Speaker 0: it shouldn't be like export probably 1st it should be more like you know like if you log the data yeah the staging is covered you know and don't log it in cloud which is pretty much i guess what you call i think yes but not like manual aircraft export no no no no even though it might be good that's why i don't need good because that's for developers and that's what people no no it's it's shocking and very simple oh and it's person really wants like i kind of think yeah bro i think we should do that experts yes comcast for given to their super consumer app how many users do they have like that's 200 yeah and what it's different like i'm pressured like out of like a 1000 that bother the device 

Speaker 1: yeah yeah yeah of course but at least like i'm just saying that like situations of hey guys i just need to be cast and i got lost my everything i hate phone i want your mother to die mhmm i think 

Speaker 0: yeah but they yeah they can export it that's fine but then the real user like the real consumers what will they do with that data i think there'll be there'll be there'll be you know slightly do you think that's better than having the backup i think backup is definitely much better much better but i think backup is much more complex mhmm our path is like like a power more correct if i'm wrong yeah that's fine that's fine i think yeah for example for situations like now where we need people to you know speech which is just like automatic and all of that stuff i think it would be and then but the post call yeah i think yes okay okay you you by any chance don't have anyone greatshow less ↑
  ''', speaker: 'speaker_00', isUser: false, start: 10, end: 13)
  ];

  StreamSubscription? audioBytesStream;
  WavBytesUtil? audioStorage;

  Timer? _memoryCreationTimer;
  Timer? _conversationAdvisorTimer;
  bool memoryCreating = false;

  DateTime? currentTranscriptStartedAt;
  DateTime? currentTranscriptFinishedAt;

  @override
  void initState() {
    btDevice = widget.btDevice;
    SchedulerBinding.instance.addPostFrameCallback((_) async {
      initiateBytesProcessing();
    });
    // if (SharedPreferencesUtil().coachIsChecked) {
    //   _initiateConversationAdvisorTimer();
    // }
    _processCachedTranscript();
    super.initState();
  }

  @override
  void dispose() {
    _conversationAdvisorTimer?.cancel();
    _memoryCreationTimer?.cancel();
    debugPrint('TranscriptWidget disposed');
    super.dispose();
  }

  _processCachedTranscript() async {
    debugPrint('_processCachedTranscript');
    var segments = SharedPreferencesUtil().transcriptSegments;
    if (segments.isEmpty) return;
    String transcript = _buildDiarizedTranscriptMessage(SharedPreferencesUtil().transcriptSegments);
    processTranscriptContent(context, transcript, null, retrievedFromCache: true);
    SharedPreferencesUtil().transcriptSegments = [];
    // TODO: include created at and finished at for this cached transcript
  }

  Future<void> initiateBytesProcessing() async {
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
            // List<TranscriptSegment> segments = await transcribeAudioFile(f, SharedPreferencesUtil().uid);
            List<TranscriptSegment> segments = await transcribeAudioFile2(f);
            processCustomTranscript(segments);
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

  void _cleanTranscript(List<TranscriptSegment> segments) {
    var hallucinations = ['Thank you.', 'I don\'t know what to do,', 'I\'m', 'It was the worst case.', 'and,'];
    // TODO: do this with any words that gets repeated twice
    // - Replicate apparently has much more hallucinations
    for (var i = 0; i < segments.length; i++) {
      for (var hallucination in hallucinations) {
        segments[i].text = segments[i]
            .text
            .replaceAll('$hallucination $hallucination $hallucination', '')
            .replaceAll('$hallucination $hallucination', '')
            .replaceAll('  ', ' ')
            .trim();
      }
    }
    // remove empty segments
    segments.removeWhere((element) => element.text.isEmpty);
  }

  void processCustomTranscript(List<TranscriptSegment> data) {
    if (data.isEmpty) return;
    var joinedSimilarSegments = <TranscriptSegment>[];
    for (var value in data) {
      if (joinedSimilarSegments.isNotEmpty &&
          (joinedSimilarSegments.last.speaker == value.speaker ||
              (joinedSimilarSegments.last.isUser && value.isUser))) {
        joinedSimilarSegments.last.text += ' ${value.text}';
      } else {
        joinedSimilarSegments.add(value);
      }
    }

    if (segments.isNotEmpty &&
        (segments.last.speaker == joinedSimilarSegments[0].speaker ||
            (segments.last.isUser && joinedSimilarSegments[0].isUser))) {
      segments.last.text += ' ${joinedSimilarSegments[0].text}';
      joinedSimilarSegments.removeAt(0);
    }

    _cleanTranscript(segments);
    _cleanTranscript(joinedSimilarSegments);

    segments.addAll(joinedSimilarSegments);
    SharedPreferencesUtil().transcriptSegments = segments;
    widget.setHasTranscripts(true);
    setState(() {});
    _initiateMemoryCreationTimer();
    currentTranscriptStartedAt ??= DateTime.now();
    currentTranscriptFinishedAt = DateTime.now();
  }

  void resetState({bool restartBytesProcessing = true, BTDeviceStruct? btDevice}) {
    debugPrint('transcript.dart resetState called');
    audioBytesStream?.cancel();
    _memoryCreationTimer?.cancel();
    if (!restartBytesProcessing && segments.isNotEmpty) _createMemory();
    if (btDevice != null) setState(() => this.btDevice = btDevice);
    if (restartBytesProcessing) initiateBytesProcessing();
  }

  String _buildDiarizedTranscriptMessage(List<TranscriptSegment> segments) {
    String transcript = '';
    for (var segment in segments) {
      if (segment.isUser) {
        transcript += 'You said: ${segment.text} ';
      } else {
        transcript += 'Speaker ${segment.speakerId}: ${segment.text} ';
      }
      transcript += '\n\n';
    }
    return transcript.trim();
  }

  // _initiateConversationAdvisorTimer() {
  //   // TODO: improvements
  //   // - This triggers every 10 minutes when the app opens, but would be great if it triggered, every 10 min of conversation
  //   // - And if the conversation finishes at 6 min, and memory is created, it should grab that portion not advised from, and advise
  //   // - Each advice should be stored, and ideally mapped to a memory
  //   // - Advice should consider conversations in other languages
  //   // - Advice should have a tone, like a conversation purpose, chill with friends, networking, family, etc...
  //   _conversationAdvisorTimer = Timer.periodic(const Duration(seconds: 60 * 10), (timer) async {
  //     addEventToContext('Conversation Advisor Timer Triggered');
  //     var transcript = _buildDiarizedTranscriptMessage(segments);
  //     debugPrint('_initiateConversationAdvisorTimer: $transcript');
  //     var advice = await adviseOnCurrentConversation(transcript);
  //     if (advice.isNotEmpty) {
  //       MixpanelManager().coachAdvisorFeedback(transcript, advice);
  //       clearNotification(3);
  //       createNotification(notificationId: 3, title: 'Your Conversation Coach Says', body: advice);
  //     }
  //   });
  // }

  _initiateMemoryCreationTimer() {
    _memoryCreationTimer?.cancel();
    _memoryCreationTimer = Timer(const Duration(seconds: 10), () => _createMemory());
  }

  _createMemory() async {
    setState(() => memoryCreating = true);
    String transcript = _buildDiarizedTranscriptMessage(segments);
    debugPrint('_createMemory transcript: \n$transcript');
    File file = await WavBytesUtil.createWavFile(audioStorage!.audioBytes);
    await uploadFile(file);
    Memory? memory = await processTranscriptContent(
      context,
      transcript,
      file.path,
      startedAt: currentTranscriptStartedAt,
      finishedAt: currentTranscriptFinishedAt,
    );
    debugPrint(memory.toString());
    if (memory != null && !memory.discarded && SharedPreferencesUtil().postMemoryNotificationIsChecked) {
      postMemoryCreationNotification(memory).then((r) {
        r = 'Hi there testing notifications stuff';
        debugPrint('Notification response: $r');
        if (r.isEmpty) return;
        // TODO: notification UI should be different, maybe a different type of message + use a Enum for message type
        widget.addMessage(Message(text: r, type: 'ai', id: const Uuid().v4(), memoryIds: [memory.id.toString()]));
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
    widget.setHasTranscripts(false);
  }

  @override
  Widget build(BuildContext context) {
    if (memoryCreating) {
      return const Padding(
        padding: EdgeInsets.only(top: 48.0),
        child: Center(
          child: CircularProgressIndicator(
            color: Colors.white,
          ),
        ),
      );
    }

    if (segments.isEmpty) {
      return btDevice != null
          ? const Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                SizedBox(height: 80),
                Align(
                  alignment: Alignment.center,
                  child: Padding(
                    padding: EdgeInsets.symmetric(horizontal: 32.0),
                    child: Text(
                      textAlign: TextAlign.center,
                      'Your transcripts will start appearing\nhere after 30 seconds.',
                      style: TextStyle(color: Colors.white, height: 1.5, decoration: TextDecoration.underline),
                    ),
                  ),
                )
              ],
            )
          : const SizedBox.shrink();
    }
    return _getDeepgramTranscriptUI();
  }

  _getDeepgramTranscriptUI() {
    var needsUtf8 = SharedPreferencesUtil().recordingsLanguage != 'en';
    return ListView.separated(
      padding: EdgeInsets.zero,
      shrinkWrap: true,
      scrollDirection: Axis.vertical,
      itemCount: segments.length + 2,
      physics: const NeverScrollableScrollPhysics(),
      separatorBuilder: (_, __) => const SizedBox(height: 16.0),
      itemBuilder: (context, idx) {
        if (idx == 0) return const SizedBox(height: 32);
        if (idx == segments.length + 1) return const SizedBox(height: 64);
        final data = segments[idx - 1];
        return Padding(
          padding: const EdgeInsetsDirectional.fromSTEB(16.0, 0.0, 16.0, 0.0),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.start,
                crossAxisAlignment: CrossAxisAlignment.center,
                children: [
                  Image.asset(data.isUser ? 'assets/images/speaker_0_icon.png' : 'assets/images/speaker_1_icon.png',
                      width: 26, height: 26),
                  const SizedBox(width: 12),
                  Text(
                    data.isUser ? 'You' : 'Speaker ${data.speakerId}',
                    style: const TextStyle(color: Colors.white, fontSize: 18),
                  )
                ],
              ),
              const SizedBox(height: 12),
              Align(
                alignment: Alignment.centerLeft,
                child: SelectionArea(
                  child: Text(
                    needsUtf8 ? utf8.decode(data.text.toString().codeUnits) : data.text,
                    style: const TextStyle(letterSpacing: 0.0, color: Colors.grey),
                    textAlign: TextAlign.left,
                  ),
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}
