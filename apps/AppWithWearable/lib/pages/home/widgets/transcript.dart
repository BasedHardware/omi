import 'dart:async';
import 'dart:io';

import 'package:collection/collection.dart';
import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
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
  const TranscriptWidget({
    super.key,
    required this.btDevice,
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

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    SchedulerBinding.instance.addPostFrameCallback((_) async {
      initBleConnection();
    });
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
    super.dispose();
  }

  _pingWsKeepAlive() {
    // TODO: try later
    Timer.periodic(const Duration(seconds: 30), (timer) {
      if (channelCustomWebsocket != null) {
        channelCustomWebsocket!.sink.add('ping');
      }
    });
  }

  Future<void> initBleConnection() async {
    Tuple4<IOWebSocketChannel?, StreamSubscription?, WavBytesUtil, IOWebSocketChannel?> data = await bleReceiveWAV(
        btDevice: widget.btDevice!,
        speechFinalCallback: (_) {
          debugPrint("Deepgram Finalized Callback received");
          setState(() {
            whispersDiarized.add({});
          });
          _initiateTimer();
        },
        interimCallback: (String transcript, Map<int, String> transcriptBySpeaker) {
          _memoryCreationTimer?.cancel();
          var copy = whispersDiarized[whispersDiarized.length - 1];
          transcriptBySpeaker.forEach((speaker, transcript) {
            copy[speaker] = transcript;
          });
          setState(() {
            whispersDiarized[whispersDiarized.length - 1] = copy;
          });
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
    channelCustomWebsocket?.sink.close();
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

  _initiateTimer() {
    _memoryCreationTimer?.cancel();
    _memoryCreationTimer = Timer(const Duration(seconds: 120), () async {
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
      processTranscriptContent(transcript, fileName);
      addEventToContext('Memory Created');
      setState(() {
        whispersDiarized = [{}];
        customWebsocketTranscript = '';
      });
      audioStorage?.clearAudioBytes();
      // TODO: proactive audio, and sends notifications telling like "Dude, don't say x like this, how frequently?
      // TODO: when memory created, do a vanishing effect, and put `memory creating ...` for 2 seconds
    });
  }

  @override
  Widget build(BuildContext context) {
    context.watch<FFAppState>();
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

    var filteredNotEmptyWhispers = whispersDiarized.where((e) => e.isNotEmpty).toList();
    if (filteredNotEmptyWhispers.isEmpty) {
      return const Padding(
        padding: EdgeInsets.only(top: 48.0),
        child: InfoButton(),
      );
    }
    return ListView.separated(
      padding: EdgeInsets.zero,
      shrinkWrap: true,
      scrollDirection: Axis.vertical,
      itemCount: filteredNotEmptyWhispers.length,
      physics: const NeverScrollableScrollPhysics(),
      separatorBuilder: (_, __) => const SizedBox(height: 16.0),
      itemBuilder: (context, idx) {
        final data = filteredNotEmptyWhispers[idx];
        String transcriptItem = '';
        for (int speaker = 0; speaker < data.length; speaker++) {
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
