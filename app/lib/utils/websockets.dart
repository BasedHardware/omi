import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/schema/message_event.dart';
import 'package:friend_private/backend/schema/transcript_segment.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/bt_device.dart';
import 'package:friend_private/env/env.dart';
import 'package:instabug_flutter/instabug_flutter.dart';
import 'package:web_socket_channel/io.dart';

enum WebsocketConnectionStatus { notConnected, connected, failed, closed, error }

Future<IOWebSocketChannel?> _initWebsocketStream(
  void Function(List<TranscriptSegment>) onMessageReceived,
  void Function(ServerMessageEvent)? onMessageEventReceived,
  VoidCallback onWebsocketConnectionSuccess,
  void Function(dynamic) onWebsocketConnectionFailed,
  void Function(int?, String?) onWebsocketConnectionClosed,
  void Function(dynamic) onWebsocketConnectionError,
  int sampleRate,
  String codec,
  bool includeSpeechProfile,
  bool newMemoryWatch,
) async {
  debugPrint('Websocket Opening');
  final recordingsLanguage = SharedPreferencesUtil().recordingsLanguage;
  var params =
      '?language=$recordingsLanguage&sample_rate=$sampleRate&codec=$codec&uid=${SharedPreferencesUtil().uid}&include_speech_profile=$includeSpeechProfile&new_memory_watch=$newMemoryWatch';

  IOWebSocketChannel channel = IOWebSocketChannel.connect(
    Uri.parse('${Env.apiBaseUrl!.replaceAll('https', 'wss')}listen$params'),
    // headers: {'Authorization': await getAuthHeader()},
  );

  await channel.ready.then((v) {
    channel.stream.listen(
      (event) {
        if (event == 'ping') return;

        final jsonEvent = jsonDecode(event);

        // segment
        if (jsonEvent is List) {
          var segments = jsonEvent;
          if (segments.isEmpty) return;
          onMessageReceived(segments.map((e) => TranscriptSegment.fromJson(e)).toList());
          return;
        }

        debugPrint(event);

        // object message event
        if (jsonEvent.containsKey("type")) {
          var messageEvent = ServerMessageEvent.fromJson(jsonEvent);
          if (onMessageEventReceived != null) {
            onMessageEventReceived(messageEvent);
            return;
          }
        }

        debugPrint(event.toString());
      },
      onError: (err, stackTrace) {
        onWebsocketConnectionError(err); // error during connection
        CrashReporting.reportHandledCrash(err!, stackTrace, level: NonFatalExceptionLevel.warning);
      },
      onDone: (() {
        // debugPrint('Websocket connection onDone ${channel}'); // FIXME
        onWebsocketConnectionClosed(channel.closeCode, channel.closeReason);
      }),
      cancelOnError: true, // TODO: is this correct?
    );
  }).onError((err, stackTrace) {
    // no closing reason or code
    print(err);
    CrashReporting.reportHandledCrash(err!, stackTrace, level: NonFatalExceptionLevel.warning);
    onWebsocketConnectionFailed(err); // initial connection failed
  });

  try {
    await channel.ready;
    debugPrint('Websocket Opened');
    onWebsocketConnectionSuccess();
  } catch (err) {
    print(err);
  }
  return channel;
}

Future<IOWebSocketChannel?> streamingTranscript({
  required VoidCallback onWebsocketConnectionSuccess,
  required void Function(dynamic) onWebsocketConnectionFailed,
  required void Function(int?, String?) onWebsocketConnectionClosed,
  required void Function(dynamic) onWebsocketConnectionError,
  required void Function(List<TranscriptSegment>) onMessageReceived,
  Function(ServerMessageEvent)? onMessageEventReceived,
  required BleAudioCodec codec,
  required int sampleRate,
  required bool includeSpeechProfile,
  required bool newMemoryWatch,
}) async {
  try {
    IOWebSocketChannel? channel = await _initWebsocketStream(
      onMessageReceived,
      onMessageEventReceived,
      onWebsocketConnectionSuccess,
      onWebsocketConnectionFailed,
      onWebsocketConnectionClosed,
      onWebsocketConnectionError,
      sampleRate,
      mapCodecToName(codec),
      includeSpeechProfile,
      newMemoryWatch,
    );

    return channel;
  } catch (e) {
    debugPrint('Error receiving data: $e');
  } finally {}

  return null;
}
