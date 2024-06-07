import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:friend_private/backend/api_requests/api_calls.dart';
import 'package:friend_private/backend/mixpanel.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/bt_device.dart';
import 'package:friend_private/backend/storage/segment.dart';
import 'package:friend_private/pages/speaker_id/tabs/wave.dart';
import 'package:friend_private/utils/ble/communication.dart';
import 'package:friend_private/utils/memories.dart';
import 'package:friend_private/backend/api_requests/cloud_storage.dart';
import 'package:friend_private/utils/notifications.dart';
import 'package:friend_private/utils/sentry_log.dart';
import 'package:friend_private/utils/stt/wav_bytes.dart';
import 'package:lottie/lottie.dart';

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
  List<TranscriptSegment> segments = [];

  List<int> bucket = List.filled(40000, 0).toList(growable: true);
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
        // if (int16Value < 3000) bucket.add(int16Value);
        if (int16Value < 3000) bucket.add(int16Value);
        // TODO: first 2 seconds are highest points bytes sent, weird, handle that so graph doesn't look shitty
      }
      // if (bucket.length > 40000) {
      //   setState(() {
      //     bucket = bucket.sublist(bucket.length - 40000);
      //   });
      // }
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
    segments.addAll(joinedSimilarSegments);
    setState(() {});
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
    if (restartBytesProcessing && segments.isNotEmpty && (segments.length > 1 || segments[0].text.isNotEmpty)) {
      _initiateMemoryCreationTimer();
    }
  }

  String _buildDiarizedTranscriptMessage() {
    String transcript = '';
    for (var segment in segments) {
      if (segment.isUser) {
        transcript += 'You said: ${segment.text} ';
      } else {
        transcript += 'Speaker ${segment.speakerId}: ${segment.text} ';
      }
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
    _conversationAdvisorTimer = Timer.periodic(const Duration(seconds: 60 * 10), (timer) async {
      addEventToContext('Conversation Advisor Timer Triggered');
      var transcript = _buildDiarizedTranscriptMessage();
      debugPrint('_initiateConversationAdvisorTimer: $transcript');
      var advice = await adviseOnCurrentConversation(transcript);
      if (advice.isNotEmpty) {
        MixpanelManager().coachAdvisorFeedback(transcript, advice);
        clearNotification(3);
        createNotification(notificationId: 3, title: 'Your Conversation Coach Says', body: advice);
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
      await processTranscriptContent(context, transcript, fileName, file.path);
      await widget.refreshMemories();
      addEventToContext('Memory Created');
      setState(() {
        segments = [];
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

    if (segments.isEmpty) {
      return btDevice != null
          ? Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const SizedBox(height: 16),
                //
                Lottie.asset('assets/lottie_animations/wave.json', height: 80),
                const SizedBox(height: 32),
                const Align(
                  alignment: Alignment.center,
                  child: Padding(
                    padding: EdgeInsets.symmetric(horizontal: 32.0),
                    child: Text(
                      textAlign: TextAlign.center,
                      'Your transcripts will start appearing\nhere after 30 seconds.',
                      style: TextStyle(color: Colors.white, height: 1.5),
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
    return ListView.separated(
      padding: EdgeInsets.zero,
      shrinkWrap: true,
      scrollDirection: Axis.vertical,
      itemCount: segments.length + 1,
      physics: const NeverScrollableScrollPhysics(),
      separatorBuilder: (_, __) => const SizedBox(height: 16.0),
      itemBuilder: (context, idx) {
        if (idx == 0) {
          return Padding(
            padding: const EdgeInsets.only(top: 8.0, bottom: 32),
            child: Align(
              alignment: Alignment.center,
              child: Lottie.asset('assets/lottie_animations/wave.json', height: 80),
            ),
          );
        }
        final data = segments[idx - 1];
        String transcriptItem = '';
        if (data.isUser) {
          transcriptItem = 'You said: ${data.text}';
        } else {
          transcriptItem = 'Speaker ${data.speakerId}: ${data.text}';
        }
        return Padding(
          padding: const EdgeInsetsDirectional.fromSTEB(16.0, 0.0, 16.0, 0.0),
          child: SelectionArea(
            child: Text(
              transcriptItem,
              style: const TextStyle(letterSpacing: 0.0, color: Colors.white),
            ),
          ),
        );
      },
    );
  }
}
