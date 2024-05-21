import 'dart:async';
import 'dart:io';

import 'package:collection/collection.dart';
import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:friend_private/backend/api_requests/api_calls.dart';
import 'package:friend_private/backend/storage/memories.dart';
import 'package:friend_private/utils/memories.dart';
import 'package:friend_private/backend/api_requests/cloud_storage.dart';
import 'package:friend_private/utils/notifications.dart';
import 'package:friend_private/utils/sentry_log.dart';
import 'package:friend_private/utils/stt/deepgram.dart';
import 'package:friend_private/utils/stt/wav_bytes.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:provider/provider.dart';
import 'package:sentry_flutter/sentry_flutter.dart';
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

class TranscriptWidgetState extends State<TranscriptWidget> with WidgetsBindingObserver {
  WebsocketConnectionStatus wsConnectionState = WebsocketConnectionStatus.notConnected;
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
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    SchedulerBinding.instance.addPostFrameCallback((_) async {
      initBleConnection();
    });
    _initiateConversationAdvisorTimer();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    super.didChangeAppLifecycleState(state);
    if (state == AppLifecycleState.paused) {
      addEventToContext('App is paused');
    } else if (state == AppLifecycleState.resumed) {
      addEventToContext('App is resumed');
    } else if (state == AppLifecycleState.hidden) {
      addEventToContext('App is hidden');
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _conversationAdvisorTimer?.cancel();
    _memoryCreationTimer?.cancel();
    debugPrint('TranscriptWidget disposed');
    super.dispose();
  }

  updateTranscript(Map<int, String> transcriptBySpeaker) {
    if (transcriptBySpeaker.isEmpty) return;
    var copy = Map<int, String>.from(whispersDiarized.last);
    transcriptBySpeaker.forEach((speaker, transcript) => copy[speaker] = transcript);
    whispersDiarized[whispersDiarized.length - 1] = copy;
    setState(() {});
  }

  Future<void> initBleConnection() async {
    Tuple4<IOWebSocketChannel?, StreamSubscription?, WavBytesUtil, IOWebSocketChannel?> data = await bleReceiveWAV(
        btDevice: widget.btDevice!,
        speechFinalCallback: (Map<int, String> transcriptBySpeaker, String transcriptItem) {
          debugPrint("Deepgram Finalized Callback received");
          updateTranscript(transcriptBySpeaker);
          if (whispersDiarized.last.isNotEmpty) {
            whispersDiarized.add({});
          }
          _initiateMemoryCreationTimer();
        },
        interimCallback: (Map<int, String> transcriptBySpeaker, String transcriptItem) {
          _memoryCreationTimer?.cancel();
          updateTranscript(transcriptBySpeaker);
          // _initiateTimer(); // FIXME sometimes final speech callback is not made, thus memory timer not started
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
          Sentry.captureException(err);
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
          Sentry.captureMessage('Websocket Closed', level: SentryLevel.warning);
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
          Sentry.captureException(err, stackTrace: err.stackTrace);
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

  void resetState({bool resetBLEConnection = true}) {
    streamSubscription?.cancel();
    channel?.sink.close(1000); // when closed from here, don't try to reconnect
    channelCustomWebsocket?.sink.close(1000);
    _memoryCreationTimer?.cancel();

    setState(() {
      // whispersDiarized = [{}];
      // customWebsocketTranscript = '';
      if (resetBLEConnection) websocketReconnecting = true;
    });
    if (resetBLEConnection) initBleConnection();
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
      for (int speaker = 0; speaker < totalSpeakers; speaker++) {
        if (part.containsKey(speaker)) {
          // This part and previous have only 1 speaker, and is the same
          if (partIdx > 0 &&
              whispersDiarized[partIdx - 1].containsKey(speaker) &&
              whispersDiarized[partIdx - 1].length == 1 &&
              part.length == 1) {
            transcript += '${part[speaker]!} ';
          } else {
            transcript += 'Speaker $speaker: ${part[speaker]!} ';
          }
        }
      }
      transcript += '\n';
    }
    return transcript;
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
      if (transcript.isEmpty || transcript.split(' ').length < 20) return;
      var advice = await adviseOnCurrentConversation(transcript);
      if (advice.isNotEmpty) {
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
      return Column(
        mainAxisAlignment: MainAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
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
        Text(
          wsConnectionState == WebsocketConnectionStatus.failed
              ? '🚨 Deepgram connection failed'
              : (wsConnectionState == WebsocketConnectionStatus.closed)
                  ? 'Deepgram connection closed'
                  : wsConnectionState == WebsocketConnectionStatus.error
                      ? 'Deepgram connection error'
                      : 'Deepgram connection failed',
          style: const TextStyle(color: Colors.white, fontSize: 16),
        ),
        SizedBox(height: websocketReconnecting ? 20 : 12),
        websocketReconnecting
            ? CircularProgressIndicator(
                color: FlutterFlowTheme.of(context).primary,
              )
            : TextButton(
                onPressed: () {
                  if (websocketReconnecting) return;
                  addEventToContext('Retry Websocket Connection Clicked');
                  resetState();
                },
                style: ButtonStyle(
                  shape: MaterialStateProperty.all<RoundedRectangleBorder>(
                    RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(12.0),
                      side: const BorderSide(color: Colors.white, width: 0.2),
                    ),
                  ),
                ),
                child: const Padding(
                  padding: EdgeInsets.symmetric(horizontal: 16.0),
                  child: Text(
                    'Retry',
                    style: TextStyle(color: Colors.white, fontSize: 18),
                  ),
                )),
      ],
    );
  }
}
