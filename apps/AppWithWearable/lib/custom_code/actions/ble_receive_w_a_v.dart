// Automatic FlutterFlow imports
import 'dart:async';
import 'dart:typed_data';

import 'package:flutter_blue_plus/flutter_blue_plus.dart';

import '/backend/schema/structs/index.dart';
import '/flutter_flow/flutter_flow_util.dart';
import 'dart:convert';
import 'package:web_socket_channel/io.dart';
import 'package:flutter/material.dart';

const serverUrl =
    'wss://api.deepgram.com/v1/listen?encoding=linear16&sample_rate=8000&language=en&model=nova-2-general&no_delay=true&endpointing=100&interim_results=true&smart_format=true&diarize=true';
const apiKey = 'DEEPGRAM_API_KEY';

late IOWebSocketChannel channel;

const int sampleRate = 8000;
const int channelCount = 1;
const int sampleWidth = 2; // 2 bytes for 16-bit samples
const int chunkSize = 200;

// UUIDs for the specific service and characteristics
const String audioServiceUuid = "19b10000-e8f2-537e-4f6c-d104768a1214";
const String audioCharacteristicUuid = "19b10001-e8f2-537e-4f6c-d104768a1214";
const String audioCharacteristicFormatUuid =
    "19b10002-e8f2-537e-4f6c-d104768a1214";

Future<void> _initStream(void Function(String) finalized_callback, void Function(String) interim_callback) async {
  print('Websocket Opening');
  channel = IOWebSocketChannel.connect(Uri.parse(serverUrl),
      headers: {'Authorization': 'Token $apiKey'});
   var is_finals = [];
   var is_finalized = false;
  channel.ready.then((_) {
    channel.stream.listen((event) {
      print('Event from Stream: $event');
      final parsedJson = jsonDecode(event);
      final transcript = parsedJson['channel']['alternatives'][0]['transcript'];
      final is_final = parsedJson['is_final'];
      final speech_final = parsedJson['is_final'];

      print('Transcript: ${transcript}');
      if(transcript.length > 0){
        if (speech_final) {
          interim_callback(is_finals.join(' ') + (is_finals.length > 0 ? ' ' : '') + transcript);
          finalized_callback('');
          is_finals = [];
        } else {
          if(is_final) {
            is_finals.add(transcript);
            interim_callback(transcript);
          } else {
            interim_callback(transcript);
          }
        }
      }
      // Re-instantiate the Completer for next use
      // completer = Completer<String>();
    },onError: (err){
      print('Websocket Error: ${err}');
    // handle stream error
    },
    onDone: (() {
     // stream on done callback... 
      print('Websocket Closed');
    }),
    cancelOnError: true
    );

  }).onError((error, stackTrace) {
    print("WebsocketChannel was unable to establishconnection");
  });

  try {
    await channel.ready;
  } catch (e) {
    // handle exception here
    print("Websocket was unable to establishconnection");

  }
}

Future<String> bleReceiveWAV(
    BTDeviceStruct btDevice, void Function(String) finalized_callback, void Function(String) interim_callback) async {
  final device = BluetoothDevice.fromId(btDevice.id);
  final completer = Completer<String>();

  try {
    _initStream(finalized_callback, interim_callback);
    await device.connect();
    print('Connected to device: ${device.id}');
    List<BluetoothService> services = await device.discoverServices();
    print('Discovered ${services.length} services');

    for (BluetoothService service in services) {
      if (service.uuid.str128.toLowerCase() == audioServiceUuid) {
        for (BluetoothCharacteristic characteristic
            in service.characteristics) {
          if (characteristic.uuid.str128.toLowerCase() ==
                  audioCharacteristicUuid ||
              characteristic.uuid.str128.toLowerCase() ==
                  audioCharacteristicFormatUuid) {
            final isNotify = characteristic.properties.notify;

            if (isNotify) {
              await characteristic.setNotifyValue(true);
              print(
                  'Subscribed to characteristic: ${characteristic.uuid.str128}');
              List<int> wavData = [];
              int samplesToRead = 150000;

              characteristic.value.listen((value) {
                if (value.isEmpty) return;
                value.removeRange(0, 3);
                channel.sink.add(value);
              });



              return completer.future;
            }
          }
        }
      }
    }

    print('Desired characteristic not found');
    if (!completer.isCompleted) {
      completer.complete(null);
    }
  } catch (e) {
    print('Error receiving data: $e');
    if (!completer.isCompleted) {
      completer.completeError(e);
    }
  } finally {}

  return completer.future;
}

FFUploadedFile createWavFile(List<int> audioData) {
  // audioData = filterAudioData(audioData);
  final byteData = ByteData(2 * audioData.length);
  for (int i = 0; i < audioData.length; i++) {
    byteData.setUint16(i * 2, audioData[i], Endian.little);
  }

  final wavHeader = buildWavHeader(audioData.length * 2);
  final wavBytes =
      Uint8List.fromList(wavHeader + byteData.buffer.asUint8List());
  final timestamp = DateFormat('yyyyMMdd_HHmmss').format(DateTime.now());
  final name = 'recording-$timestamp.wav';

  return FFUploadedFile(
    name: name,
    bytes: Uint8List.fromList(wavBytes),
  );
}

Uint8List buildWavHeader(int dataLength) {
  final byteData = ByteData(44);
  final size = dataLength + 36;

  // RIFF chunk
  byteData.setUint8(0, 0x52); // 'R'
  byteData.setUint8(1, 0x49); // 'I'
  byteData.setUint8(2, 0x46); // 'F'
  byteData.setUint8(3, 0x46); // 'F'
  byteData.setUint32(4, size, Endian.little);
  byteData.setUint8(8, 0x57); // 'W'
  byteData.setUint8(9, 0x41); // 'A'
  byteData.setUint8(10, 0x56); // 'V'
  byteData.setUint8(11, 0x45); // 'E'

  // fmt chunk
  byteData.setUint8(12, 0x66); // 'f'
  byteData.setUint8(13, 0x6D); // 'm'
  byteData.setUint8(14, 0x74); // 't'
  byteData.setUint8(15, 0x20); // ' '
  byteData.setUint32(16, 16, Endian.little);
  byteData.setUint16(20, 1, Endian.little); // Audio format (1 = PCM)
  byteData.setUint16(22, channelCount, Endian.little);
  byteData.setUint32(24, sampleRate, Endian.little);
  byteData.setUint32(
      28, sampleRate * channelCount * sampleWidth, Endian.little);
  byteData.setUint16(32, channelCount * sampleWidth, Endian.little);
  byteData.setUint16(34, sampleWidth * 8, Endian.little);

  // data chunk
  byteData.setUint8(36, 0x64); // 'd'
  byteData.setUint8(37, 0x61); // 'a'
  byteData.setUint8(38, 0x74); // 't'
  byteData.setUint8(39, 0x61); // 'a'
  byteData.setUint32(40, dataLength, Endian.little);

  return byteData.buffer.asUint8List();
}
