import 'dart:async';
import 'package:friend_private/utils/sentry_log.dart';
import 'package:friend_private/utils/stt/wav_bytes.dart';

import 'package:flutter/material.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:sentry_flutter/sentry_flutter.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:tuple/tuple.dart';

import '/backend/schema/structs/index.dart';
import '/flutter_flow/flutter_flow_util.dart';
import 'package:web_socket_channel/io.dart';

// UUIDs for the specific service and characteristics
const String audioServiceUuid = "19b10000-e8f2-537e-4f6c-d104768a1214";
const String audioCharacteristicUuid = "19b10001-e8f2-537e-4f6c-d104768a1214";
const String audioCharacteristicFormatUuid = "19b10002-e8f2-537e-4f6c-d104768a1214";

Future<IOWebSocketChannel?> _initCustomStream({
  void Function(String)? onCustomWebSocketCallback,
}) async {
  final prefs = await SharedPreferences.getInstance();
  final serverUrl = prefs.getString('customWebsocketUrl');
  final recordingsLanguage = prefs.getString('recordingsLanguage') ?? 'en';
  if (serverUrl == null) {
    debugPrint('Custom Websocket URL not set');
    return null;
  }
  debugPrint('Websocket Opening');
  IOWebSocketChannel channel = IOWebSocketChannel.connect(Uri.parse('$serverUrl?language=$recordingsLanguage'));
  channel.ready.then((_) {
    channel.stream.listen(
      (event) {
        // debugPrint('Event from Stream: $event');
        if (event == 'ping') return;
        final parsedJson = jsonDecode(event);
        debugPrint('parsedJson: ${parsedJson.toString()}');
        if (parsedJson.length > 0) {
          String transcript = '';
          parsedJson.forEach((item) {
            transcript += item['speaker'] + ':' + item['text'] + '\n';
          });
          onCustomWebSocketCallback!(transcript);
        }
      },
      onError: (err) {
        debugPrint('Custom Websocket Error: $err');
      },
      onDone: (() {
        debugPrint('Custom Websocket Closed');
      }),
      cancelOnError: true,
    );
  });
  try {
    await channel.ready;
    debugPrint('Custom Websocket Opened');
  } catch (err) {
    debugPrint("Custom Websocket was unable to establish connection");
    debugPrint(err.toString());
  }
  return channel;
}

Future<IOWebSocketChannel> _initStream(
    void Function(String) speechFinalCallback,
    void Function(String, Map<int, String>) interimCallback,
    VoidCallback onWebsocketConnectionSuccess,
    VoidCallback onWebsocketConnectionFailed,
    VoidCallback onWebsocketConnectionClosed,
    void Function(dynamic) onWebsocketConnectionError) async {
  final prefs = await SharedPreferences.getInstance();
  final apiKey = prefs.getString('deepgramApiKey') ?? '';
  // final apiKey = '123';
  final recordingsLanguage = prefs.getString('recordingsLanguage') ?? 'en';

  var serverUrl =
      'wss://api.deepgram.com/v1/listen?encoding=linear16&sample_rate=8000&language=$recordingsLanguage&model=nova-2-general&no_delay=true&endpointing=100&interim_results=true&smart_format=true&diarize=true';

  debugPrint('Websocket Opening');
  IOWebSocketChannel channel =
      IOWebSocketChannel.connect(Uri.parse(serverUrl), headers: {'Authorization': 'Token $apiKey'});

  channel.ready.then((_) {
    channel.stream.listen(
      (event) {
        // debugPrint('Event from Stream: $event');
        final parsedJson = jsonDecode(event);
        // FIXME Receiver: null ~ Tried calling: []("alternatives")
        final data = parsedJson['channel']['alternatives'][0];
        final transcript = data['transcript'];
        final speechFinal = parsedJson['is_final'];

        if (transcript.length > 0) {
          debugPrint('~~Transcript: $transcript ~ speechFinal: $speechFinal');
          Map<int, String> bySpeaker = {};
          data['words'].forEach((word) {
            int speaker = word['speaker'];
            bySpeaker[speaker] ??= '';
            bySpeaker[speaker] = '${(bySpeaker[speaker] ?? '') + word['punctuated_word']} ';
          });
          // This is step 1 for diarization, but, sometimes "Speaker 1: Hello how"
          //   but it says it's the previous speaker (e.g. speaker 0), but in the next stream it fixes the transcript, and says it's speaker 1.
          debugPrint(bySpeaker.toString());
          if (speechFinal) {
            interimCallback(transcript, bySpeaker);
            speechFinalCallback('');
          } else {
            interimCallback(transcript, bySpeaker);
          }
        }
      },
      onError: (err) {
        debugPrint('Websocket Error: $err');
        addDeepgramEventContext('Websocket Error');
        Sentry.captureException(err, stackTrace: err.stackTrace);
        onWebsocketConnectionError(err);
      },
      onDone: (() {
        debugPrint('Websocket Closed');
        addDeepgramEventContext('Websocket Closed');
        onWebsocketConnectionClosed();
      }),
      cancelOnError: true,
    );
  }).onError((error, stackTrace) {
    addDeepgramEventContext('Websocket Unable To Connect');
    debugPrint("WebsocketChannel was unable to establish connection");
    onWebsocketConnectionFailed();
  });

  try {
    await channel.ready;
    debugPrint('Websocket Opened');
    addDeepgramEventContext('Websocket Opened');
    onWebsocketConnectionSuccess();
  } catch (err) {
    debugPrint("Websocket was unable to establish connection");
    addDeepgramEventContext('Websocket Unable To Connect 2');
    onWebsocketConnectionFailed();
    Sentry.captureException(err);
  }
  return channel;
}

Future<Tuple3<IOWebSocketChannel?, StreamSubscription?, WavBytesUtil>> bleReceiveWAV({
  BTDeviceStruct? btDevice,
  void Function(String)? speechFinalCallback,
  void Function(String, Map<int, String>)? interimCallback,
  VoidCallback? onWebsocketConnectionSuccess,
  VoidCallback? onWebsocketConnectionFailed,
  VoidCallback? onWebsocketConnectionClosed,
  void Function(dynamic)? onWebsocketConnectionError,
  void Function(String)? onCustomWebSocketCallback,
}) async {
  final device = BluetoothDevice.fromId(btDevice!.id);
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

    IOWebSocketChannel? channel2 = await _initCustomStream(onCustomWebSocketCallback: onCustomWebSocketCallback);
    await device.connect();
    debugPrint('Connected to device: ${device.remoteId}');
    List<BluetoothService> services = await device.discoverServices();
    debugPrint('Discovered ${services.length} services');

    for (BluetoothService service in services) {
      if (service.uuid.str128.toLowerCase() == audioServiceUuid) {
        for (BluetoothCharacteristic characteristic in service.characteristics) {
          if (characteristic.uuid.str128.toLowerCase() == audioCharacteristicUuid ||
              characteristic.uuid.str128.toLowerCase() == audioCharacteristicFormatUuid) {
            final isNotify = characteristic.properties.notify;

            if (isNotify) {
              await characteristic.setNotifyValue(true);
              debugPrint('Subscribed to characteristic: ${characteristic.uuid.str128}');

              StreamSubscription stream = characteristic.value.listen((List<int> value) {
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

              // return completer.future;
              return Tuple3<IOWebSocketChannel?, StreamSubscription?, WavBytesUtil>(channel, stream, wavBytesUtil);
            }
          }
        }
      }
    }

    debugPrint('Desired characteristic not found');
  } catch (e) {
    debugPrint('Error receiving data: $e');
  } finally {}

  // return completer.future;
  return Tuple3<IOWebSocketChannel?, StreamSubscription?, WavBytesUtil>(null, null, wavBytesUtil);
}
