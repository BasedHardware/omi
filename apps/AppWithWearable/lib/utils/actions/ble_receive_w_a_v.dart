import 'dart:async';
import 'dart:io';
import 'dart:typed_data';
import 'package:path_provider/path_provider.dart';

import 'package:flutter/material.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:tuple/tuple.dart';

import '/backend/schema/structs/index.dart';
import '/flutter_flow/flutter_flow_util.dart';
import 'package:web_socket_channel/io.dart';

const int sampleRate = 8000;
const int channelCount = 1;
const int sampleWidth = 2; // 2 bytes for 16-bit samples

// UUIDs for the specific service and characteristics
const String audioServiceUuid = "19b10000-e8f2-537e-4f6c-d104768a1214";
const String audioCharacteristicUuid = "19b10001-e8f2-537e-4f6c-d104768a1214";
const String audioCharacteristicFormatUuid = "19b10002-e8f2-537e-4f6c-d104768a1214";

Future<IOWebSocketChannel> _initStream(
    void Function(String) speechFinalCallback, void Function(String, Map<int, String>) interimCallback) async {
  final prefs = await SharedPreferences.getInstance();
  final apiKey = prefs.getString('deepgramApiKey') ?? '';
  final recordingsLanguage = prefs.getString('recordingsLanguage') ?? 'en';

  var serverUrl =
      'wss://api.deepgram.com/v1/listen?encoding=linear16&sample_rate=8000&language=$recordingsLanguage&model=nova-2-general&no_delay=true&endpointing=100&interim_results=true&smart_format=true&diarize=true';

  debugPrint('Websocket Opening');
  IOWebSocketChannel channel =
      IOWebSocketChannel.connect(Uri.parse(serverUrl), headers: {'Authorization': 'Token $apiKey'});

  channel.ready.then((_) {
    channel.stream.listen((event) {
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
    }, onError: (err) {
      debugPrint('Websocket Error: $err');
      // handle stream error
    }, onDone: (() {
      // stream on done callback...
      debugPrint('Websocket Closed');
    }), cancelOnError: true);
  }).onError((error, stackTrace) {
    debugPrint("WebsocketChannel was unable to establishconnection");
  });

  try {
    await channel.ready;
    debugPrint('Channel is ready, websocket opened');
  } catch (e) {
    // handle exception here
    debugPrint("Websocket was unable to establishconnection");
  }
  return channel;
}

Future<Tuple3<IOWebSocketChannel?, StreamSubscription?, AudioStorage>> bleReceiveWAV(BTDeviceStruct btDevice,
    void Function(String) speechFinalCallback, void Function(String, Map<int, String>) interimCallback) async {
  final device = BluetoothDevice.fromId(btDevice.id);
  AudioStorage audioStorage = AudioStorage();

  try {
    IOWebSocketChannel channel = await _initStream(speechFinalCallback, interimCallback);
    await device.connect();
    debugPrint('Connected to device: ${device.id}');
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
                  audioStorage.addAudioBytes([int16Value]);
                }
                channel.sink.add(value);
              });

              // return completer.future;
              return Tuple3<IOWebSocketChannel?, StreamSubscription?, AudioStorage>(channel, stream, audioStorage);
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
  return Tuple3<IOWebSocketChannel?, StreamSubscription?, AudioStorage>(null, null, audioStorage);
}

class AudioStorage {
  // List to hold audio data in bytes
  final List<int> _audioBytes = [];

  get audioBytes => _audioBytes;

  // Method to add audio bytes (now accepts List<int> instead of Uint8List)
  void addAudioBytes(List<int> bytes) {
    _audioBytes.addAll(bytes);
  }

  // Method to clear audio bytes
  void clearAudioBytes() {
    _audioBytes.clear();
    debugPrint('Cleared audio bytes');
  }

  void cleanAudioBytes() {
    // Assuming empty audio bytes mean zeros
    _audioBytes.removeWhere((byte) => byte == 0);
  }

  // Method to clean out the silent parts based on a given threshold
  // void removeSilentSegments({int silenceThreshold = 10}) {
  //   // Identify segments with sound (above the silenceThreshold)
  //   List<int> cleanedBytes = [];
  //   for (int byte in _audioBytes) {
  //     if (byte.abs() > silenceThreshold) {
  //       cleanedBytes.add(byte);
  //     }
  //   }
  //   _audioBytes
  //     ..clear()
  //     ..addAll(cleanedBytes);
  //   debugPrint('Cleaned silent segments');
  // }

  // Method to create a WAV file from the stored audio bytes
  Future<File> createWavFile() async {
    // TODO: remove empty sounds without words
    // removeSilentSegments();
    final timestamp = DateFormat('yyyyMMdd_HHmmss').format(DateTime.now());
    final wavHeader = buildWavHeader(_audioBytes.length * 2);
    final wavBytes = Uint8List.fromList(wavHeader + convertToLittleEndianBytes(_audioBytes));
    final filename = 'recording-$timestamp.wav';

    final directory = await getApplicationDocumentsDirectory();
    final file = File('${directory.path}/$filename');
    await file.writeAsBytes(wavBytes);
    debugPrint('WAV file created: ${file.path}');
    return file;
  }

  // Utility to convert audio data to little-endian format
  Uint8List convertToLittleEndianBytes(List<int> audioData) {
    final byteData = ByteData(2 * audioData.length);
    for (int i = 0; i < audioData.length; i++) {
      byteData.setUint16(i * 2, audioData[i], Endian.little);
    }
    return byteData.buffer.asUint8List();
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
    byteData.setUint32(28, sampleRate * channelCount * sampleWidth, Endian.little);
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
}
