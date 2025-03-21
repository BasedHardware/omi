import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/foundation.dart';
import 'package:omi/utils/audio/wav_bytes.dart';
import 'package:path_provider/path_provider.dart';

class FileUtils {
  static Future<File> saveAudioBytesToTempFile(List<List<int>> chunk, int timerStart) async {
    final directory = await getTemporaryDirectory();
    String filePath = '${directory.path}/audio_${timerStart}.bin';
    List<int> data = [];
    for (int i = 0; i < chunk.length; i++) {
      var frame = chunk[i];

      // Format: <length>|<data> ; bytes: 4 | n
      final byteFrame = ByteData(frame.length);
      for (int i = 0; i < frame.length; i++) {
        byteFrame.setUint8(i, frame[i]);
      }
      data.addAll(Uint32List.fromList([frame.length]).buffer.asUint8List());
      data.addAll(byteFrame.buffer.asUint8List());
    }
    final file = File(filePath);
    await file.writeAsBytes(data);

    return file;
  }
  
  static Future<File> convertPcmToWavFile(Uint8List pcmBytes, int sampleRate, int channels) async {
    try {
      // Convert PCM to WAV bytes
      final wavBytes = WavBytes.fromPcm(
        pcmBytes,
        sampleRate: sampleRate,
        numChannels: channels,
      ).asBytes();
      
      // Create a temporary file
      final tempDir = await getTemporaryDirectory();
      final tempPath = '${tempDir.path}/recording_${DateTime.now().millisecondsSinceEpoch}.wav';
      final file = File(tempPath);
      
      // Write WAV bytes to file
      await file.writeAsBytes(wavBytes);
      return file;
    } catch (e) {
      debugPrint('Error converting PCM to WAV: $e');
      rethrow;
    }
  }
}
