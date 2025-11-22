import 'dart:io';
import 'dart:typed_data';
import 'package:flutter/foundation.dart';
import 'package:just_audio/just_audio.dart' as ja;
import 'package:opus_dart/opus_dart.dart';
import 'package:path_provider/path_provider.dart';
import 'package:wav/wav.dart';

/// Converts MP3 audio to Omi frame format (.bin file)
class Mp3ToOmiConverter {
  /// Convert MP3 data to Omi .bin format
  /// Returns the path to the created .bin file
  static Future<String> convertMp3ToOmiBin({
    required Uint8List mp3Data,
    required String outputFilename,
  }) async {
    debugPrint('Converting MP3 to Omi format: $outputFilename');
    
    // Step 1: Save MP3 temporarily
    final tempDir = await getTemporaryDirectory();
    final tempMp3Path = '${tempDir.path}/temp_${DateTime.now().millisecondsSinceEpoch}.mp3';
    final tempMp3File = File(tempMp3Path);
    await tempMp3File.writeAsBytes(mp3Data);
    
    try {
      // Step 2: Decode MP3 to PCM
      final pcmData = await _decodeMp3ToPcm(tempMp3Path);
      
      // Step 3: Encode PCM to Opus frames
      final opusFrames = await _encodePcmToOpusFrames(pcmData);
      
      // Step 4: Write frames in Omi format
      final binPath = await _writeOmiBinFile(opusFrames, outputFilename);
      
      debugPrint('Conversion complete: $binPath (${opusFrames.length} frames)');
      
      return binPath;
    } finally {
      // Cleanup temp file
      if (await tempMp3File.exists()) {
        await tempMp3File.delete();
      }
    }
  }
  
  /// Decode MP3 to PCM (16-bit, 16kHz, mono) using flutter_sound
  static Future<Uint8List> _decodeMp3ToPcm(String mp3Path) async {
    final tempDir = await getTemporaryDirectory();
    final wavPath = '${tempDir.path}/temp_${DateTime.now().millisecondsSinceEpoch}.wav';
    
    final player = FlutterSoundPlayer();
    
    try {
      debugPrint('Converting MP3 to WAV using flutter_sound...');
      
      await player.openPlayer();
      
      // Use flutter_sound to convert MP3 to WAV
      await FlutterSoundHelper().convertFile(
        mp3Path,
        Codec.mp3,
        wavPath,
        Codec.pcm16WAV,
      );
      
      await player.closePlayer();
      
      // Read WAV file
      final wavFile = File(wavPath);
      if (!await wavFile.exists()) {
        throw Exception('WAV file not created');
      }
      
      final wavData = await wavFile.readAsBytes();
      
      // Skip WAV header (44 bytes) to get raw PCM
      final pcmData = wavData.sublist(44);
      
      debugPrint('PCM data size: ${pcmData.length} bytes');
      
      // Cleanup
      if (await wavFile.exists()) {
        await wavFile.delete();
      }
      
      return pcmData;
    } catch (e) {
      debugPrint('Error decoding MP3: $e');
      await player.closePlayer();
      // Cleanup on error
      final wavFile = File(wavPath);
      if (await wavFile.exists()) {
        await wavFile.delete();
      }
      rethrow;
    }
  }
  
  /// Encode PCM data to Opus frames
  static Future<List<Uint8List>> _encodePcmToOpusFrames(Uint8List pcmData) async {
    const sampleRate = 16000;
    const channels = 1;
    const frameSize = 160; // 10ms at 16kHz (160 samples)
    
    // Initialize Opus encoder
    final encoder = SimpleOpusEncoder(
      sampleRate: sampleRate,
      channels: channels,
      application: Application.audio,
    );
    
    final frames = <Uint8List>[];
    
    // Convert Uint8List (bytes) to Int16List (16-bit samples)
    final int16Data = Int16List.view(pcmData.buffer);
    
    // Process PCM data in chunks of 160 samples
    for (int i = 0; i < int16Data.length; i += frameSize) {
      final end = (i + frameSize).clamp(0, int16Data.length);
      final chunk = int16Data.sublist(i, end);
      
      // Pad last chunk if needed
      Int16List paddedChunk = chunk;
      if (chunk.length < frameSize) {
        paddedChunk = Int16List(frameSize);
        paddedChunk.setRange(0, chunk.length, chunk);
      }
      
      // Encode to Opus
      final encoded = encoder.encode(input: paddedChunk);
      frames.add(Uint8List.fromList(encoded));
    }
    
    encoder.destroy();
    
    return frames;
  }
  
  /// Write frames in Omi .bin format: [4-byte length][frame data]
  static Future<String> _writeOmiBinFile(
    List<Uint8List> frames,
    String filename,
  ) async {
    final directory = await getApplicationDocumentsDirectory();
    final binPath = '${directory.path}/$filename';
    final file = File(binPath);
    
    final buffer = BytesBuilder();
    
    for (final frame in frames) {
      // Write 4-byte length (little-endian)
      final lengthBytes = ByteData(4);
      lengthBytes.setInt32(0, frame.length, Endian.little);
      buffer.add(lengthBytes.buffer.asUint8List());
      
      // Write frame data
      buffer.add(frame);
    }
    
    await file.writeAsBytes(buffer.toBytes());
    
    return binPath;
  }
}
