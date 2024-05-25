import 'dart:async';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/utils/ble/communication.dart';
import 'package:friend_private/utils/stt/wav_bytes.dart';
import 'package:flutter/material.dart';
import 'package:tuple/tuple.dart';

import '/backend/schema/structs/index.dart';
import '/flutter_flow/flutter_flow_util.dart';
import 'package:web_socket_channel/io.dart';

// UUIDs for the specific service and characteristics
const String audioServiceUuid = "19b10000-e8f2-537e-4f6c-d104768a1214";
const String audioCharacteristicUuid = "19b10001-e8f2-537e-4f6c-d104768a1214";
const String audioCharacteristicFormatUuid = "19b10002-e8f2-537e-4f6c-d104768a1214";

Future<IOWebSocketChannel?> _initCustomStream(
    void Function(String)? onCustomWebSocketCallback,
    VoidCallback onWebsocketConnectionSuccess,
    void Function(dynamic) onWebsocketConnectionFailed,
    void Function(int?, String?) onWebsocketConnectionClosed,
    void Function(dynamic) onWebsocketConnectionError) async {
  debugPrint('Websocket Opening');
  final recordingsLanguage = SharedPreferencesUtil().recordingsLanguage;
  // https://38aa-190-25-123-167.ngrok-free.app
  IOWebSocketChannel channel = IOWebSocketChannel.connect(
      Uri.parse('ws://38aa-190-25-123-167.ngrok-free.app/transcribe-ws?language=$recordingsLanguage'));
  channel.ready.then((_) {
    channel.stream.listen(
      (event) {
        // debugPrint('Event from Stream: $event');
        if (event == 'ping') return;
        final segments = jsonDecode(event);
        debugPrint('segments: ${segments.toString()}');
        if (segments.length > 0) {
          String transcript = '';
          segments.forEach((item) {
            transcript += (item['speaker'] ?? '') + ':' + item['text'] + '\n';
          });
          onCustomWebSocketCallback!(transcript);
        }
      },
      onError: (err) {
        onWebsocketConnectionError(err); // error during connection
      },
      onDone: (() {
        onWebsocketConnectionClosed(channel.closeCode, channel.closeReason);
      }),
      cancelOnError: true,
    );
  }).onError((err, stackTrace) {
    // no closing reason or code
    onWebsocketConnectionFailed(err); // initial connection failed
  });

  try {
    await channel.ready;
    debugPrint('Custom Websocket Opened');
    onWebsocketConnectionSuccess();
  } catch (err) {}
  return channel;
}

Future<IOWebSocketChannel> _initStream(
    void Function(List<dynamic>, String) speechFinalCallback,
    void Function(Map<int, String>, String) interimCallback,
    VoidCallback onWebsocketConnectionSuccess,
    void Function(dynamic) onWebsocketConnectionFailed,
    void Function(int?, String?) onWebsocketConnectionClosed,
    void Function(dynamic) onWebsocketConnectionError) async {
  final recordingsLanguage = SharedPreferencesUtil().recordingsLanguage;
  // final recordingsLanguage = 'en';

  var serverUrl =
      'wss://api.deepgram.com/v1/listen?encoding=linear16&sample_rate=8000&language=$recordingsLanguage&model=nova-2-general&no_delay=true&endpointing=100&interim_results=false&smart_format=true&diarize=true';

  debugPrint('Websocket Opening');
  IOWebSocketChannel channel = IOWebSocketChannel.connect(Uri.parse(serverUrl),
      headers: {'Authorization': 'Token ${getDeepgramApiKeyForUsage()}'});

  channel.ready.then((_) {
    channel.stream.listen(
      (event) {
        // debugPrint('Event from Stream: $event');
        final parsedJson = jsonDecode(event);
        if (parsedJson['channel'] == null || parsedJson['channel']['alternatives'] == null) return;

        final data = parsedJson['channel']['alternatives'][0];
        // debugPrint('parsedJson: ${data.toString()}');
        final transcript = data['transcript'];
        final speechFinal = parsedJson['is_final'];
        if (transcript.length > 0) {
          debugPrint('Transcript: ${data['words']}');
          if (speechFinal) {
            speechFinalCallback(data['words'], '');
          } else {
            interimCallback({}, '');
          }
        }
      },
      onError: (err) {
        // no closing reason or code
        onWebsocketConnectionError(err); // error during connection
      },
      onDone: (() {
        onWebsocketConnectionClosed(channel.closeCode, channel.closeReason);
      }),
      cancelOnError: true,
    );
  }).onError((err, stackTrace) {
    // no closing reason or code
    onWebsocketConnectionFailed(err); // initial connection failed
  });

  try {
    await channel.ready;
    onWebsocketConnectionSuccess();
  } catch (err) {
    // no closing reason or code (triggers onError anyways)
    // onWebsocketConnectionFailed(err);
  }
  return channel;
}

Future<Tuple4<IOWebSocketChannel?, StreamSubscription?, WavBytesUtil, IOWebSocketChannel?>> bleReceiveWAV({
  required BTDeviceStruct? btDevice,
  void Function(List<dynamic>, String)? speechFinalCallback,
  void Function(Map<int, String>, String)? interimCallback,
  VoidCallback? onWebsocketConnectionSuccess,
  void Function(dynamic)? onWebsocketConnectionFailed,
  void Function(int?, String?)? onWebsocketConnectionClosed,
  void Function(dynamic)? onWebsocketConnectionError,
  void Function(String)? onCustomWebSocketCallback,
}) async {
  WavBytesUtil wavBytesUtil = WavBytesUtil();

  try {
    IOWebSocketChannel channel = await _initStream(
      speechFinalCallback!,
      interimCallback!,
      onWebsocketConnectionSuccess!,
      onWebsocketConnectionFailed!,
      onWebsocketConnectionClosed!,
      onWebsocketConnectionError!,
    );

    // IOWebSocketChannel? channel2 = await _initCustomStream(
    //   onCustomWebSocketCallback,
    //   onWebsocketConnectionSuccess,
    //   onWebsocketConnectionFailed,
    //   onWebsocketConnectionClosed,
    //   onWebsocketConnectionError,
    // );
    IOWebSocketChannel? channel2;

    StreamSubscription? stream = await getBleAudioBytesListener(btDevice!, onAudioBytesReceived: (List<int> value) {
      if (value.isEmpty) return;
      value.removeRange(0, 3);
      for (int i = 0; i < value.length; i += 2) {
        int byte1 = value[i];
        int byte2 = value[i + 1];
        int int16Value = (byte2 << 8) | byte1;
        wavBytesUtil.addAudioBytes([int16Value]);
      }
      channel.sink.add(value);
      channel2?.sink.add(value);
    });
    return Tuple4<IOWebSocketChannel?, StreamSubscription?, WavBytesUtil, IOWebSocketChannel?>(
        channel, stream, wavBytesUtil, channel2);
  } catch (e) {
    debugPrint('Error receiving data: $e');
  } finally {}

  // return completer.future;
  return Tuple4<IOWebSocketChannel?, StreamSubscription?, WavBytesUtil, IOWebSocketChannel?>(
      null, null, wavBytesUtil, null);
}
