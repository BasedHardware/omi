import 'dart:async';
import 'dart:io';

import 'package:collection/collection.dart';
import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:friend_private/backend/api_requests/api_calls.dart';
import 'package:friend_private/utils/memories.dart';
import 'package:friend_private/backend/api_requests/cloud_storage.dart';
import 'package:friend_private/utils/notifications.dart';
import 'package:friend_private/utils/sentry_log.dart';
import 'package:friend_private/utils/stt/deepgram.dart';
import 'package:friend_private/utils/stt/wav_bytes.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:instabug_flutter/instabug_flutter.dart';
import 'package:tuple/tuple.dart';
import 'package:web_socket_channel/io.dart';

import '/backend/schema/structs/index.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import 'info_button.dart';

enum WebsocketConnectionStatus { notConnected, connected, failed, closed, error }

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
  WebsocketConnectionStatus wsConnectionState = WebsocketConnectionStatus.notConnected;
  BTDeviceStruct? btDevice;
  bool websocketReconnecting = false;
  List<Map<int, String>> whispersDiarized = [{}];

  IOWebSocketChannel? channel;
  StreamSubscription? streamSubscription;
  WavBytesUtil? audioStorage;

  Timer? _memoryCreationTimer;

  String customWebsocketTranscript = '';
  IOWebSocketChannel? channelCustomWebsocket;

  Timer? _conversationAdvisorTimer;

  @override
  void initState() {
    btDevice = widget.btDevice;
    SchedulerBinding.instance.addPostFrameCallback((_) async {
      initBleConnection();
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

    if (previous.length == 1 && current.length == 1 && previous.keys.toList()[0] == current.keys.toList()[0]) {
      // Last diarized, it's just 1, and here's just one, just add
      int speakerIdx = current.keys.toList()[0];
      previous[speakerIdx] = '${previous[speakerIdx]!} ' + current[current.keys.toList()[0]]!['transcript'];
      whispersDiarized[whispersDiarized.length - 1] = previous;
      // Same speaker, just add
    } else if (previous.length == 1 && current.length == 2 && previous.keys.toList()[0] == currentOrdered[0]) {
      // TODO: verify this is happening
      // add that transcript fot the speakers, but append the remaining ones as new speakers
      // Last diarized it's just 1, and here's 2 but the previous speaker, is one that starts first here
      previous[currentOrdered[0]] = (previous[currentOrdered[0]] ?? '') + current[currentOrdered[0]]!['transcript'];
      whispersDiarized[whispersDiarized.length - 1] = previous;
      var newTranscription = <int, String>{};
      for (var speaker in currentOrdered) {
        if (speaker != currentOrdered[0]) newTranscription[speaker] = current[speaker]!['transcript'];
      }
      whispersDiarized.add(newTranscription);
    } else if (previous.isEmpty) {
      // Different speakers, just add
      current.forEach((speaker, data) {
        whispersDiarized[whispersDiarized.length - 1][speaker] = data['transcript'];
      });
    } else {
      // Different speakers, just add
      whispersDiarized.add({});
      current.forEach((speaker, data) {
        whispersDiarized[whispersDiarized.length - 1][speaker] = data['transcript'];
      });
    }

    // iterate speakers by startTime first
    setState(() {});
  }

  Future<void> initBleConnection() async {
    debugPrint('initBleConnection: $btDevice');
    if (btDevice == null) return;
    Tuple4<IOWebSocketChannel?, StreamSubscription?, WavBytesUtil, IOWebSocketChannel?> data = await bleReceiveWAV(
        btDevice: btDevice!,
        speechFinalCallback: (List<dynamic> words, String transcriptItem) {
          Map<int, Map<String, dynamic>> bySpeaker = {};
          for (var word in words) {
            // LATER: get words for speaker 0, idx 0 to 5, then next speaker 1 on 6-7, then again speaker 0, do not just append
            // debugPrint('Word: ${word.toString()}');
            int speaker = word['speaker'];
            if (bySpeaker[speaker] == null) bySpeaker[speaker] = <String, dynamic>{};
            String currentSpeakerTranscript = bySpeaker[speaker]!['transcript'] ?? '';
            bySpeaker[speaker]!['transcript'] = '${currentSpeakerTranscript + word['punctuated_word']} ';
            bySpeaker[speaker]!['starts'] = min<double>(bySpeaker[speaker]!['starts'] ?? 999999999999.0, word['start']);
            bySpeaker[speaker]!['ends'] = max<double>(bySpeaker[speaker]!['ends'] ?? -1, word['end']);
          }
          debugPrint(bySpeaker.toString());
          updateTranscript(bySpeaker);
          _initiateMemoryCreationTimer();
        },
        interimCallback: (Map<int, String> transcriptBySpeaker, String transcriptItem) {
          // debugPrint('interimCallback called');
          // _memoryCreationTimer?.cancel();
          // updateTranscript(transcriptBySpeaker); // interim causes makes a bit more complex the
        },
        onWebsocketConnectionSuccess: () {
          addEventToContext('Websocket Opened');
          setState(() {
            wsConnectionState = WebsocketConnectionStatus.connected;
            websocketReconnecting = false;
            _reconnectionAttempts = 0; // Reset counter on successful connection
          });
        },
        onWebsocketConnectionFailed: (err) {
          addEventToContext('Websocket Unable To Connect');
          // connection couldn't be initiated for some reason.
          setState(() {
            wsConnectionState = WebsocketConnectionStatus.failed;
            websocketReconnecting = false;
          });
          _reconnectWebSocket();
        },
        onWebsocketConnectionClosed: (int? closeCode, String? closeReason) {
          // connection was closed, either on resetState, or by deepgram, or by some other reason.
          addEventToContext('Websocket Closed');
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
          addEventToContext('Websocket Error');
          CrashReporting.reportHandledCrash(err, err.stackTrace);
          setState(() {
            wsConnectionState = WebsocketConnectionStatus.error;
            websocketReconnecting = false;
          });
          _reconnectWebSocket();
        },
        onCustomWebSocketCallback: (String transcript) async {
          // debugPrint('Custom Websocket Callback: $transcript');
          for (var word in transcript.split(' ')) {
            setState(() {
              customWebsocketTranscript += '$word ';
            });
            await Future.delayed(const Duration(milliseconds: 100));
          }
          setState(() {
            customWebsocketTranscript += '\n';
          });
        });

    channel = data.item1;
    streamSubscription = data.item2;
    audioStorage = data.item3;
    channelCustomWebsocket = data.item4;
  }

  void resetState({bool resetBLEConnection = true, BTDeviceStruct? btDevice}) {
    debugPrint('transcript.dart resetState called');
    streamSubscription?.cancel();
    channel?.sink.close(1000); // when closed from here, don't try to reconnect
    channelCustomWebsocket?.sink.close(1000);
    _memoryCreationTimer?.cancel();

    setState(() {
      // whispersDiarized = [{}];
      if (btDevice != null) this.btDevice = btDevice;
      if (resetBLEConnection) websocketReconnecting = true;
    });
    if (resetBLEConnection) initBleConnection();
    if (resetBLEConnection &&
        whispersDiarized.isNotEmpty &&
        (whispersDiarized.length > 1 || whispersDiarized[0].isNotEmpty)) _initiateMemoryCreationTimer();
  }

  int _reconnectionAttempts = 0;

  Future<void> _reconnectWebSocket() async {
    if (_reconnectionAttempts >= 3) {
      setState(() {
        websocketReconnecting = false;
      });
      // TODO: reset here to 0? or not, this could cause infinite loop if it's called in parallel from 2 distinct places
      debugPrint('Max reconnection attempts reached');
      clearNotification(2);
      createNotification(
          notificationId: 2,
          title: 'Deepgram Connection Error',
          body: 'There was an error with the Deepgram connection, please restart the app and check your credentials.');
      addEventToContext('Max reconnection attempts reached');
      return;
    }
    setState(() {
      websocketReconnecting = true;
    });
    _reconnectionAttempts++;
    addEventToContext('Attempting to reconnect Websocket $_reconnectionAttempts');
    await Future.delayed(const Duration(seconds: 3)); // Reconnect delay
    debugPrint('Attempting to reconnect $_reconnectionAttempts time');
    await initBleConnection();
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
      for (int speaker = 0; speaker < totalSpeakers; speaker++) {
        if (part.containsKey(speaker)) transcriptItem += 'Speaker $speaker: ${part[speaker]!} ';
      }
      transcript += '$transcriptItem\n\n';
    }
    return transcript.trim();
  }

  bool memoryCreating = false;

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
        clearNotification(3);
        createNotification(notificationId: 3, title: 'Your Conversation Coach Says', body: advice);
      }
    });
  }

  _initiateMemoryCreationTimer() {
    debugPrint('_initiateMemoryCreationTimer');
    _memoryCreationTimer?.cancel();
    _memoryCreationTimer = Timer(const Duration(seconds: 120), () async {
      widget.refreshMemories();
      setState(() {
        memoryCreating = true;
      });
      debugPrint('Creating memory from whispers');
      String transcript = '';
      if (customWebsocketTranscript.trim().isNotEmpty) {
        transcript = customWebsocketTranscript.trim();
      } else {
        transcript = _buildDiarizedTranscriptMessage();
      }
      debugPrint('Transcript: \n$transcript');
      File file = await audioStorage!.createWavFile();
      String? fileName = await uploadFile(file);
      await processTranscriptContent(context, transcript, fileName);
      await widget.refreshMemories();
      addEventToContext('Memory Created');
      setState(() {
        whispersDiarized = [{}];
        customWebsocketTranscript = '';
        memoryCreating = false;
      });
      audioStorage?.clearAudioBytes();
    });
  }

  @override
  Widget build(BuildContext context) {
    if (wsConnectionState == WebsocketConnectionStatus.failed ||
        wsConnectionState == WebsocketConnectionStatus.closed ||
        wsConnectionState == WebsocketConnectionStatus.error) {
      return _websocketConnectionIssueUI();
    }

    if (customWebsocketTranscript != '') {
      return Row(
        mainAxisAlignment: MainAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: Padding(
              padding: const EdgeInsetsDirectional.fromSTEB(16.0, 0.0, 16.0, 0.0),
              child: Text(
                customWebsocketTranscript,
                style: FlutterFlowTheme.of(context).bodyMedium.override(
                      fontFamily: FlutterFlowTheme.of(context).bodyMediumFamily,
                      letterSpacing: 0.0,
                      useGoogleFonts: GoogleFonts.asMap().containsKey(FlutterFlowTheme.of(context).bodyMediumFamily),
                    ),
              ),
            ),
          ),
          // Expanded(child: _getDeepgramUI()),
        ],
      );
    }

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
      return const Padding(
        padding: EdgeInsets.only(top: 48.0),
        child: InfoButton(),
      );
    }
    return _getDeepgramTranscriptUI();
  }

  _getDeepgramTranscriptUI() {
    return ListView.separated(
      padding: EdgeInsets.zero,
      shrinkWrap: true,
      scrollDirection: Axis.vertical,
      itemCount: whispersDiarized.length,
      physics: const NeverScrollableScrollPhysics(),
      separatorBuilder: (_, __) => const SizedBox(height: 16.0),
      itemBuilder: (context, idx) {
        final data = whispersDiarized[idx];
        var keys = data.keys.map((e) => e);
        int totalSpeakers = keys.isNotEmpty ? (keys.reduce(max) + 1) : 0;
        String transcriptItem = '';
        for (int speaker = 0; speaker < totalSpeakers; speaker++) {
          if (data.containsKey(speaker)) {
            transcriptItem += 'Speaker $speaker: ${data[speaker]!} ';
          }
        }
        return Padding(
          padding: const EdgeInsetsDirectional.fromSTEB(16.0, 0.0, 16.0, 0.0),
          child: Text(
            transcriptItem,
            style: FlutterFlowTheme.of(context).bodyMedium.override(
                  fontFamily: FlutterFlowTheme.of(context).bodyMediumFamily,
                  letterSpacing: 0.0,
                  useGoogleFonts: GoogleFonts.asMap().containsKey(FlutterFlowTheme.of(context).bodyMediumFamily),
                ),
          ),
        );
      },
    );
  }

  _websocketConnectionIssueUI() {
    return Column(
      children: [
        // Text(
        //   wsConnectionState == WebsocketConnectionStatus.failed
        //       ? '🚨 Deepgram connection failed'
        //       : (wsConnectionState == WebsocketConnectionStatus.closed)
        //           ? 'Deepgram connection closed'
        //           : wsConnectionState == WebsocketConnectionStatus.error
        //               ? 'Deepgram connection error'
        //               : 'Deepgram connection failed',
        //   style: const TextStyle(color: Colors.white, fontSize: 16),
        // ),
        // SizedBox(height: websocketReconnecting ? 20 : 12),
        websocketReconnecting
            ? CircularProgressIndicator(
                color: FlutterFlowTheme.of(context).primary,
              )
            : const SizedBox.shrink()
        // : TextButton(
        //     onPressed: () {
        //       if (websocketReconnecting) return;
        //       addEventToContext('Retry Websocket Connection Clicked');
        //       resetState();
        //     },
        //     style: ButtonStyle(
        //       shape: MaterialStateProperty.all<RoundedRectangleBorder>(
        //         RoundedRectangleBorder(
        //           borderRadius: BorderRadius.circular(12.0),
        //           side: const BorderSide(color: Colors.white, width: 0.2),
        //         ),
        //       ),
        //     ),
        //     child: const Padding(
        //       padding: EdgeInsets.symmetric(horizontal: 16.0),
        //       child: Text(
        //         'Retry',
        //         style: TextStyle(color: Colors.white, fontSize: 18),
        //       ),
        //     )),
      ],
    );
  }
}
