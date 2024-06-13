import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:friend_private/backend/api_requests/api_calls.dart';
import 'package:friend_private/backend/api_requests/cloud_storage.dart';
import 'package:friend_private/backend/mixpanel.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/bt_device.dart';
import 'package:friend_private/backend/storage/segment.dart';
import 'package:friend_private/utils/ble/communication.dart';
import 'package:friend_private/utils/memories.dart';
import 'package:friend_private/utils/notifications.dart';
import 'package:friend_private/utils/sentry_log.dart';
import 'package:friend_private/utils/stt/wav_bytes.dart';

class TranscriptWidget extends StatefulWidget {
  final Function refreshMemories;
  final Function(bool) setHasTranscripts;

  const TranscriptWidget({
    super.key,
    required this.btDevice,
    required this.refreshMemories,
    required this.setHasTranscripts,
  });

  final BTDeviceStruct? btDevice;

  @override
  State<TranscriptWidget> createState() => TranscriptWidgetState();
}

class TranscriptWidgetState extends State<TranscriptWidget> {
  BTDeviceStruct? btDevice;
  List<TranscriptSegment> segments = [];

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
    if (SharedPreferencesUtil().coachIsChecked) {
      _initiateConversationAdvisorTimer();
    }
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
    processTranscriptContent(context, transcript, null, null, retrievedFromCache: true);
    SharedPreferencesUtil().transcriptSegments = [];
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
            List<TranscriptSegment> segments = await transcribeAudioFile(f, SharedPreferencesUtil().uid);
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
    var hallucinations = ['Thank you.', 'I don\'t know what to do,', 'I\'m', 'It was the worst case.'];
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
  }

  void resetState({bool restartBytesProcessing = true, BTDeviceStruct? btDevice}) {
    debugPrint('transcript.dart resetState called');
    audioBytesStream?.cancel();
    _memoryCreationTimer?.cancel();

    if (!restartBytesProcessing && segments.isNotEmpty) {
      _createMemory();
    }

    setState(() {
      if (btDevice != null) this.btDevice = btDevice;
    });
    if (restartBytesProcessing) initiateBytesProcessing();
    // if (restartBytesProcessing && segments.isNotEmpty && (segments.length > 1 || segments[0].text.isNotEmpty)) {
    //   _initiateMemoryCreationTimer();
    // }
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

  _initiateConversationAdvisorTimer() {
    // TODO: improvements
    // - This triggers every 10 minutes when the app opens, but would be great if it triggered, every 10 min of conversation
    // - And if the conversation finishes at 6 min, and memory is created, it should grab that portion not advised from, and advise
    // - Each advice should be stored, and ideally mapped to a memory
    // - Advice should consider conversations in other languages
    // - Advice should have a tone, like a conversation purpose, chill with friends, networking, family, etc...
    _conversationAdvisorTimer = Timer.periodic(const Duration(seconds: 60 * 10), (timer) async {
      addEventToContext('Conversation Advisor Timer Triggered');
      var transcript = _buildDiarizedTranscriptMessage(segments);
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
    _memoryCreationTimer = Timer(const Duration(seconds: 120), () => _createMemory());
  }

  _createMemory() async {
    setState(() => memoryCreating = true);
    debugPrint('Creating memory from whispers');
    String transcript = _buildDiarizedTranscriptMessage(segments);
    debugPrint('Transcript: \n$transcript');
    File file = await WavBytesUtil.createWavFile(audioStorage!.audioBytes);
    String? fileName = await uploadFile(file);
    await processTranscriptContent(context, transcript, fileName, file.path);
    await widget.refreshMemories();
    // SharedPreferencesUtil().temporalAudioBytes = [];
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
