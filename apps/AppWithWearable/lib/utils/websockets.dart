import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/database/transcript_segment.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/bt_device.dart';
import 'package:friend_private/env/env.dart';
import 'package:friend_private/utils/audio/wav_bytes.dart';
import 'package:friend_private/utils/ble/communication.dart';
import 'package:instabug_flutter/instabug_flutter.dart';
import 'package:tuple/tuple.dart';
import 'package:web_socket_channel/io.dart';

enum WebsocketConnectionStatus { notConnected, connected, failed, closed, error }

Future<IOWebSocketChannel?> _initWebsocketStream(
  void Function(List<TranscriptSegment>) onMessageReceived,
  VoidCallback onWebsocketConnectionSuccess,
  void Function(dynamic) onWebsocketConnectionFailed,
  void Function(int?, String?) onWebsocketConnectionClosed,
  void Function(dynamic) onWebsocketConnectionError,
  int sampleRate,
) async {
  debugPrint('Websocket Opening');
  final recordingsLanguage = SharedPreferencesUtil().recordingsLanguage;
  // https://38aa-190-25-123-167.ngrok-free.app
  IOWebSocketChannel channel = IOWebSocketChannel.connect(
    Uri.parse(
        '${Env.apiBaseUrl!.replaceAll('https', 'wss')}listen?language=$recordingsLanguage&uid=${SharedPreferencesUtil().uid}&sample_rate=$sampleRate'),
  );
  channel.ready.then((_) {
    channel.stream.listen(
      (event) {
        if (event == 'ping') return;
        final segments = jsonDecode(event);
        if (segments is List) {
          if (segments.isEmpty) return;
          onMessageReceived(segments.map((e) => TranscriptSegment.fromJson(e)).toList());
        } else {
          debugPrint('pong');
        }
      },
      onError: (err, stackTrace) {
        onWebsocketConnectionError(err); // error during connection
        CrashReporting.reportHandledCrash(err!, stackTrace, level: NonFatalExceptionLevel.warning);
      },
      onDone: (() {
        onWebsocketConnectionClosed(channel.closeCode, channel.closeReason);
      }),
      cancelOnError: true,
    );
  }).onError((err, stackTrace) {
    // no closing reason or code
    CrashReporting.reportHandledCrash(err!, stackTrace, level: NonFatalExceptionLevel.warning);
    onWebsocketConnectionFailed(err); // initial connection failed
  });

  try {
    await channel.ready;
    debugPrint('Websocket Opened');
    onWebsocketConnectionSuccess();
  } catch (err) {}
  return channel;
}

Future<Tuple3<IOWebSocketChannel?, StreamSubscription?, WavBytesUtil>> streamingTranscript({
  required BTDeviceStruct btDevice,
  required VoidCallback onWebsocketConnectionSuccess,
  required void Function(dynamic) onWebsocketConnectionFailed,
  required void Function(int?, String?) onWebsocketConnectionClosed,
  required void Function(dynamic) onWebsocketConnectionError,
  required void Function(List<TranscriptSegment>) onMessageReceived,
}) async {
  BleAudioCodec codec = await getAudioCodec(btDevice.id);
  WavBytesUtil wavBytesUtil = WavBytesUtil(codec: codec);

  try {
    IOWebSocketChannel? channel = await _initWebsocketStream(
      onMessageReceived,
      onWebsocketConnectionSuccess,
      onWebsocketConnectionFailed,
      onWebsocketConnectionClosed,
      onWebsocketConnectionError,
      codec == BleAudioCodec.pcm8 ? 8000 : 16000,
    );

    StreamSubscription? stream = await getBleAudioBytesListener(
      btDevice.id,
      onAudioBytesReceived: (List<int> value) {
        if (value.isEmpty) return;
        wavBytesUtil.storeFramePacket(value);
        value.removeRange(0, 3);
        channel!.sink.add(value);
      },
    );
    return Tuple3<IOWebSocketChannel?, StreamSubscription?, WavBytesUtil>(channel, stream, wavBytesUtil);
  } catch (e) {
    debugPrint('Error receiving data: $e');
  } finally {}

  // return completer.future;
  return Tuple3<IOWebSocketChannel?, StreamSubscription?, WavBytesUtil>(null, null, wavBytesUtil);
}
