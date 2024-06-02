import 'dart:async';
import 'dart:io';

import 'package:collection/collection.dart';
import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:friend_private/backend/api_requests/api_calls.dart';
import 'package:friend_private/backend/mixpanel.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/storage/segment.dart';
import 'package:friend_private/utils/ble/communication.dart';
import 'package:friend_private/utils/memories.dart';
import 'package:friend_private/backend/api_requests/cloud_storage.dart';
import 'package:friend_private/utils/notifications.dart';
import 'package:friend_private/utils/sentry_log.dart';
import 'package:friend_private/utils/stt/wav_bytes.dart';
import 'package:friend_private/utils/vad.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:lottie/lottie.dart';

import '/backend/schema/structs/index.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import 'info_button.dart';
import 'ota_update_button.dart';

class TranscriptWidget extends StatefulWidget {
  final Function refreshMemories;

  const TranscriptWidget({
    super.key,
    required this.btDevice,
    required this.refreshMemories,
  });

  final BTDeviceStruct? btDevice;

  @override
  State<TranscriptWidget> createState() => TranscriptWidgetState();
}

class TranscriptWidgetState extends State<TranscriptWidget> {
  BTDeviceStruct? btDevice;
  List<Map<int, String>> whispersDiarized = [{}];

  StreamSubscription? audioBytesStream;
  WavBytesUtil? audioStorage;

  Timer? _memoryCreationTimer;
  Timer? _conversationAdvisorTimer;
  bool memoryCreating = false;

  @override
  void initState() {
    btDevice = widget.btDevice;
    SchedulerBinding.instance.addPostFrameCallback((_) async {
      initiateBytesProcessing();
    });
    _initiateConversationAdvisorTimer();
    super.initState();
  }

  @override
  void dispose() {
    _conversationAdvisorTimer?.cancel();
    _memoryCreationTimer?.cancel();
    debugPrint('TranscriptWidget disposed');
    super.dispose();
  }

  updateTranscript(Map<int, Map<String, dynamic>> current) {
    var previous = Map<int, String>.from(whispersDiarized.last);
    List<int> currentOrdered = current.keys.toList()
      ..sort((a, b) => current[a]!['starts'].compareTo(current[b]!['starts']));

    if (previous.length == 1 &&
        current.length == 1 &&
        previous.keys.toList()[0] == current.keys.toList()[0]) {
      // Last diarized, it's just 1, and here's just one, just add
      int speakerIdx = current.keys.toList()[0];
      previous[speakerIdx] = '${previous[speakerIdx]!} ' +
          current[current.keys.toList()[0]]!['transcript'];
      whispersDiarized[whispersDiarized.length - 1] = previous;
      // Same speaker, just add
    } else if (previous.length == 1 && current.length == 2 && previous.keys.toList()[0] == currentOrdered[0]) {
      // add that transcript fot the speakers, but append the remaining ones as new speakers
      // Last diarized it's just 1, and here's 2 but the previous speaker, is one that starts first here
      previous[currentOrdered[0]] = (previous[currentOrdered[0]] ?? '') +
          current[currentOrdered[0]]!['transcript'];
      whispersDiarized[whispersDiarized.length - 1] = previous;
      var newTranscription = <int, String>{};
      for (var speaker in currentOrdered) {
        if (speaker != currentOrdered[0])
          newTranscription[speaker] = current[speaker]!['transcript'];
      }
      whispersDiarized.add(newTranscription);
    } else if (previous.isEmpty) {
      // Different speakers, just add
      current.forEach((speaker, data) {
        whispersDiarized[whispersDiarized.length - 1][speaker] =
            data['transcript'];
      });
    } else {
      // Different speakers, just add
      whispersDiarized.add({});
      current.forEach((speaker, data) {
        whispersDiarized[whispersDiarized.length - 1][speaker] =
            data['transcript'];
      });
    }

    // iterate speakers by startTime first
    setState(() {});
  }

  Future<void> initiateBytesProcessing() async {
    if (btDevice == null) return;
    WavBytesUtil wavBytesUtil = WavBytesUtil();
    WavBytesUtil toProcessBytes = WavBytesUtil();
    // VadUtil vad = VadUtil();
    // await vad.init();

    StreamSubscription? stream = await getBleAudioBytesListener(btDevice!, onAudioBytesReceived: (List<int> value) {
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
        toProcessBytes.clearAudioBytesSegment(remainingSeconds: 1);
        WavBytesUtil.createWavFile(bytesCopy, filename: 'temp.wav').then((f) async {
          // var containsAudio = await vad.predict(f.readAsBytesSync());
          try {
            List<TranscriptSegment> segments = await transcribeAudioFile(f, SharedPreferencesUtil().uid);
            processCustomTranscript(segments);
          } catch (e) {
            toProcessBytes.insertAudioBytes(bytesCopy.sublist(0, 232000)); // remove last 1 sec to avoid duplicate
          }
        });
      }
    });

    audioBytesStream = stream;
    audioStorage = wavBytesUtil;
  }

  _manualTranscriptUpdate(int idx, String transcript, double starts, double ends) {
    updateTranscript({
      idx: {'transcript': transcript, 'starts': starts, 'ends': ends}
    });
  }

  void processCustomTranscript(List<TranscriptSegment> data) {
    if (data.isEmpty) return;

    int prevSpeakerId = -2;
    String currTranscript = '';
    int sameSpeakerFromIdx = 0;

    for (int i = 0; i < data.length; i++) {
      var segment = data[i];
      debugPrint(segment.toString());
      int currentSpeakerId = segment.isUser ? -1 : int.parse(segment.speaker.split('_')[1]);
      if (prevSpeakerId == currentSpeakerId) {
        currTranscript += ' ${segment.text}';
      } else if (prevSpeakerId != -2) {
        _manualTranscriptUpdate(prevSpeakerId, currTranscript, data[sameSpeakerFromIdx].start, data[i - 1].end);
        currTranscript = segment.text;
        sameSpeakerFromIdx = i;
      } else {
        currTranscript = segment.text;
        sameSpeakerFromIdx = i;
      }
      prevSpeakerId = currentSpeakerId;
    }

    if (currTranscript.isNotEmpty) {
      _manualTranscriptUpdate(prevSpeakerId, currTranscript, data[sameSpeakerFromIdx].start, data[data.length - 1].end);
    }
    _initiateMemoryCreationTimer();
  }

  void resetState({bool restartBytesProcessing = true, BTDeviceStruct? btDevice}) {
    debugPrint('transcript.dart resetState called');
    audioBytesStream?.cancel();
    _memoryCreationTimer?.cancel();

    setState(() {
      if (btDevice != null) this.btDevice = btDevice;
    });
    if (restartBytesProcessing) initiateBytesProcessing();
    if (restartBytesProcessing &&
        whispersDiarized.isNotEmpty &&
        (whispersDiarized.length > 1 || whispersDiarized[0].isNotEmpty))
      _initiateMemoryCreationTimer();
  }

  String _buildDiarizedTranscriptMessage() {
    int totalSpeakers = whispersDiarized
        .map((e) => e.keys.isEmpty ? 0 : ((e.keys).max + 1))
        .reduce((value, element) => value > element ? value : element);

    debugPrint('Speakers count: $totalSpeakers');

    String transcript = '';
    for (int partIdx = 0; partIdx < whispersDiarized.length; partIdx++) {
      var part = whispersDiarized[partIdx];
      if (part.isEmpty) continue;
      int totalSpeakers = part.keys.map((e) => e).reduce(max) + 1;
      String transcriptItem = '';
      for (int speaker = -1; speaker < totalSpeakers; speaker++) {
        if (part.containsKey(speaker)) {
          if (speaker == -1) {
            transcriptItem += 'You said: ${part[speaker]!} ';
          } else {
            transcriptItem += 'Speaker $speaker: ${part[speaker]!} ';
          }
        }
      }
      transcript += '$transcriptItem\n\n';
    }
    return transcript.trim();
  }

  _initiateConversationAdvisorTimer() {
    // TODO: improvements
    // - This triggers every 10 minutes when the app opens, but would be great if it triggered, every 10 min of conversation
    // - And if the conversation finishes at 6 min, and memory is created, it should grab that portion not advised from, and advise
    // - Each advice should be stored, and ideally mapped to a memory
    // - Advice should consider conversations in other languages
    // - Advice should have a tone, like a conversation purpose, chill with friends, networking, family, etc...
    _conversationAdvisorTimer =
        Timer.periodic(const Duration(seconds: 60 * 10), (timer) async {
      addEventToContext('Conversation Advisor Timer Triggered');
      var transcript = _buildDiarizedTranscriptMessage();
      debugPrint('_initiateConversationAdvisorTimer: $transcript');
      var advice = await adviseOnCurrentConversation(transcript);
      if (advice.isNotEmpty) {
        MixpanelManager().coachAdvisorFeedback(transcript, advice);
        clearNotification(3);
        createNotification(
            notificationId: 3,
            title: 'Your Conversation Coach Says',
            body: advice);
      }
    });
  }

  _initiateMemoryCreationTimer() {
    _memoryCreationTimer?.cancel();
    _memoryCreationTimer = Timer(const Duration(seconds: 120), () async {
      widget.refreshMemories();
      setState(() {
        memoryCreating = true;
      });
      debugPrint('Creating memory from whispers');
      String transcript = _buildDiarizedTranscriptMessage();
      debugPrint('Transcript: \n$transcript');
      File file = await WavBytesUtil.createWavFile(audioStorage!.audioBytes);
      String? fileName = await uploadFile(file);
      whispersDiarized = [{}];
      await processTranscriptContent(context, transcript, fileName);
      await widget.refreshMemories();
      addEventToContext('Memory Created');
      setState(() {
        memoryCreating = false;
      });
      audioStorage?.clearAudioBytes();
    });
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

    if (whispersDiarized[0].keys.isEmpty) {
      return Padding(
        padding: const EdgeInsets.only(top: 48.0),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            OtaUpdateButton(btDevice: btDevice),
            const InfoButton(),
            // const Text(
            //   'Transcriptions will start appearing\nafter 30 seconds',
            //   style: TextStyle(color: Colors.white, fontSize: 14),
            //   textAlign: TextAlign.center,
            // ),
            btDevice == null ? const SizedBox.shrink() : Lottie.asset('assets/lottie_animations/wave.json', width: 80),
          ],
        ),
      );
    }
    return _getDeepgramTranscriptUI();
  }

  _getDeepgramTranscriptUI() {
    return ListView.separated(
      padding: EdgeInsets.zero,
      shrinkWrap: true,
      scrollDirection: Axis.vertical,
      itemCount: whispersDiarized.length + 1,
      physics: const NeverScrollableScrollPhysics(),
      separatorBuilder: (_, __) => const SizedBox(height: 16.0),
      itemBuilder: (context, idx) {
        if (idx == whispersDiarized.length) {
          return Padding(
            padding: const EdgeInsets.symmetric(horizontal: 0),
            child: Lottie.asset('assets/lottie_animations/wave.json',
                width: 80, height: 60, alignment: Alignment.center, fit: BoxFit.contain),
          );
        }
        final data = whispersDiarized[idx];
        var keys = data.keys.map((e) => e);
        int totalSpeakers = keys.isNotEmpty ? (keys.reduce(max) + 1) : 0;
        String transcriptItem = '';
        for (int speaker = -1; speaker < totalSpeakers; speaker++) {
          if (data.containsKey(speaker)) {
            if (speaker == -1) {
              transcriptItem += 'You said: ${data[speaker]!} ';
            } else {
              transcriptItem += 'Speaker $speaker: ${data[speaker]!} ';
            }
          }
        }
        return Padding(
          padding: const EdgeInsetsDirectional.fromSTEB(16.0, 0.0, 16.0, 0.0),
          child: Text(
            transcriptItem,
            style: FlutterFlowTheme.of(context).bodyMedium.override(
                  fontFamily: FlutterFlowTheme.of(context).bodyMediumFamily,
                  letterSpacing: 0.0,
                  useGoogleFonts: GoogleFonts.asMap().containsKey(
                      FlutterFlowTheme.of(context).bodyMediumFamily),
                ),
          ),
        );
      },
    );
  }
}
