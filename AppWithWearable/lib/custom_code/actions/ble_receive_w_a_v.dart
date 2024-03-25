// Automatic FlutterFlow imports
import '/backend/backend.dart';
import '/backend/schema/structs/index.dart';
import '/backend/schema/enums/enums.dart';
import '/backend/supabase/supabase.dart';
import '/actions/actions.dart' as action_blocks;
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/custom_code/actions/index.dart'; // Imports other custom actions
import '/flutter_flow/custom_functions.dart'; // Imports custom functions
import 'package:flutter/material.dart';
// Begin custom action code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

import 'index.dart'; // Imports other custom actions

import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'dart:typed_data';
import 'dart:async';

const int sampleRate = 4000;
const int channelCount = 1;
const int sampleWidth = 2; // 2 bytes for 16-bit samples
const int chunkSize = 200;

/*List<int> filterAudioData(List<int> audioData) {
  // Calculate the scaling factor

  //

  //int maxVal = audioData.reduce((curr, next) => curr > next ? curr : next);
  //int minVal = audioData.reduce((curr, next) => curr < next ? curr : next);
  //double scalingFactor = 2 * 32768 / (max(0, maxVal) - min(0, minVal));

  // for each item in the list subtract 32

  double afterSubtraction =

  // Apply the scaling factor
  List<int> scaledAudioData =
      audioData.map((e) => (e * scalingFactor).toInt()).toList();

  return scaledAudioData;
  }
*/

Future<FFUploadedFile?> bleReceiveWAV(
    BTDeviceStruct btDevice, int recordDuration) async {
  final device = BluetoothDevice.fromId(btDevice.id);
  final completer = Completer<FFUploadedFile?>();

  try {
    await device.connect();
    print('Connected to device: ${device.id}');
    List<BluetoothService> services = await device.discoverServices();
    print('Discovered ${services.length} services');

    for (BluetoothService service in services) {
      for (BluetoothCharacteristic characteristic in service.characteristics) {
        final isNotify = characteristic.properties.notify;

        if (isNotify) {
          await characteristic.setNotifyValue(true);
          print('Subscribed to characteristic: ${characteristic.uuid}');
          List<int> wavData = [];
          int samplesToRead = 40000;

          characteristic.value.listen((value) {
            print('values -- ${value[0]}, ${value[1]}');
            // Interpret bytes as Uint16 directly
            for (int i = 0; i < value.length; i += 2) {
              int byte1 = value[i];
              int byte2 = value[i + 1];
              int uint16Value = (byte1 << 8) | byte2;
              wavData.add(uint16Value);

              print('$uint16Value');
            }

            print(
                'Received ------ ${value.length ~/ 2} samples, total: ${wavData.length}/$samplesToRead');
            if (wavData.length >= samplesToRead && !completer.isCompleted) {
              print('Received desired amount of data');
              characteristic.setNotifyValue(false);
              completer.complete(createWavFile(wavData));
            } else {
              print('Still need ${samplesToRead - wavData.length} samples');
            }
          });

          // Wait for the desired duration
          final waitSeconds = recordDuration + 20;
          await Future.delayed(Duration(seconds: waitSeconds));

          // If the desired amount of data is not received within the duration,
          // return null if the completer is not already completed
          if (!completer.isCompleted) {
            print('Recording duration reached without receiving enough data');
            await characteristic.setNotifyValue(false);
            completer.complete(null);
          }

          return completer.future;
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
