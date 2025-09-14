import 'dart:typed_data';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:omi/src/flutter_communicator.g.dart';
import 'package:path_provider/path_provider.dart';

class WatchHome extends StatefulWidget {
  const WatchHome({super.key});

  @override
  State<WatchHome> createState() => _WatchHomeState();
}

class _WatchHomeState extends State<WatchHome> implements WatchCounterFlutterAPI {
  final WatchCounterHostAPI _hostAPI = WatchCounterHostAPI();
  int _count = 0;
  bool _isRecording = false;
  Uint8List? _audioData;
  String? _audioFilePath;
  final Map<int, (Uint8List, double)> _audioChunks = {}; // (audioData, sampleRate)
  int _nextExpectedChunkIndex = 0;
  double _sampleRate = 16000.0; // Now consistently 16kHz from watch resampling

  @override
  void initState() {
    WatchCounterFlutterAPI.setUp(this);
    _hostAPI.increment();
    super.initState();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Text('Watch Home $_count'),
            const SizedBox(height: 20),
            if (_isRecording)
              const Text(
                'Recording Audio...',
                style: TextStyle(color: Colors.red, fontSize: 18),
              ),
            const SizedBox(height: 20),
            ElevatedButton(
              onPressed: _toggleRecording,
              child: Text(_isRecording ? 'Stop Recording' : 'Start Recording'),
            ),
            const SizedBox(height: 10),
            if (_audioChunks.isNotEmpty) Text('Receiving chunks: ${_audioChunks.length}'),
            if (_audioData != null) Text('Audio file received: ${_audioData!.length} bytes'),
            if (_audioFilePath != null) Text('Saved to: ${_audioFilePath!.split('/').last}'),
          ],
        ),
      ),
    );
  }

  void _toggleRecording() {
    if (_isRecording) {
      _hostAPI.stopRecording();
    } else {
      _hostAPI.startRecording();
    }
  }

  @override
  void decrement() {
    setState(() {
      _count--;
    });
  }

  @override
  void increment() {
    setState(() {
      _count++;
    });
  }

  @override
  void onRecordingStarted() {
    setState(() {
      _isRecording = true;
      _audioChunks.clear();
      _audioData = null;
      _audioFilePath = null;
      _nextExpectedChunkIndex = 0;
      _sampleRate = 16000.0; // Reset to 16kHz (consistent from watch)
    });
    print('Recording started from watch');
  }

  @override
  void onRecordingStopped() {
    setState(() {
      _isRecording = false;
    });
    print('Recording stopped from watch');

    // Process the complete audio data if we have it
    print('Audio data: $_audioData');
    if (_audioData != null) {
      _saveAudioFile();
    }
  }

  @override
  void onAudioData(Uint8List audioData) {
    print('Flutter: onAudioData callback called with ${audioData.length} bytes');
    setState(() {
      _audioData = audioData;
    });
    print('Received complete WAV audio file: ${audioData.length} bytes');
  }

  @override
  void onAudioChunk(Uint8List audioChunk, int chunkIndex, bool isLast, double sampleRate) {
    print(
        'Flutter: onAudioChunk callback called with ${audioChunk.length} bytes, chunk: $chunkIndex, isLast: $isLast, rate: ${sampleRate}Hz');

    // Store the chunk with sample rate
    _audioChunks[chunkIndex] = (audioChunk, sampleRate);
    _sampleRate = sampleRate; // Update the current sample rate

    if (isLast) {
      // All chunks received, reassemble the complete audio data
      _reassembleAudioData();
    } else {
      if (chunkIndex % 10 == 0) {
        // Only log every 10th chunk
        print('Received audio chunk $chunkIndex with ${audioChunk.length} bytes');
      }
    }
  }

  void _reassembleAudioData() {
    print('Reassembling audio data from ${_audioChunks.length} chunks at ${_sampleRate}Hz');

    // Sort chunks by index and combine them
    final sortedChunks = _audioChunks.entries.toList()..sort((a, b) => a.key.compareTo(b.key));

    final bytesBuilder = BytesBuilder();
    for (final entry in sortedChunks) {
      final (chunkData, _) = entry.value;
      bytesBuilder.add(chunkData);
    }

    final combinedData = bytesBuilder.toBytes();
    print('Combined audio data size: ${combinedData.length} bytes');

    setState(() {
      _audioData = combinedData;
      _audioChunks.clear();
      _nextExpectedChunkIndex = 0;
    });

    // Save the complete audio file
    _saveAudioFile();
  }

  Future<void> _saveAudioFile() async {
    if (_audioData == null) return;

    try {
      final directory = await getApplicationDocumentsDirectory();
      final timestamp = DateTime.now().millisecondsSinceEpoch;
      final fileName = 'watch_recording_$timestamp.wav';
      final filePath = '${directory.path}/$fileName';

      final file = File(filePath);
      final wavData = _createWavFile(_audioData!);
      await file.writeAsBytes(wavData);

      print('Created WAV file with sample rate: ${_sampleRate}Hz');
      print('PCM data size: ${_audioData!.length} bytes');
      print('WAV file size: ${wavData.length} bytes (header: ${wavData.length - _audioData!.length} bytes)');

      setState(() {
        _audioFilePath = filePath;
      });

      print('WAV file saved to: $filePath');
      print('File size: ${await file.length()} bytes');
      print('Original PCM size: ${_audioData!.length} bytes');
      print('WAV file size: ${wavData.length} bytes');
    } catch (e) {
      print('Error saving WAV file: $e');
    }
  }

  Uint8List _createWavFile(Uint8List pcmData) {
    // WAV file format constants - use the actual sample rate from the watch
    final int sampleRate = _sampleRate.toInt(); // Use actual sample rate
    const int bitsPerSample = 16;
    const int numChannels = 1; // Mono
    final int byteRate = sampleRate * numChannels * bitsPerSample ~/ 8;
    final int blockAlign = numChannels * bitsPerSample ~/ 8;

    final int dataSize = pcmData.length;
    final int fileSize = 36 + dataSize; // 36 is header size

    final BytesBuilder builder = BytesBuilder();

    // RIFF header
    builder.add('RIFF'.codeUnits); // ChunkID
    builder.add(_int32ToBytes(fileSize)); // ChunkSize
    builder.add('WAVE'.codeUnits); // Format

    // Format chunk
    builder.add('fmt '.codeUnits); // Subchunk1ID
    builder.add(_int32ToBytes(16)); // Subchunk1Size (16 for PCM)
    builder.add(_int16ToBytes(1)); // AudioFormat (1 for PCM)
    builder.add(_int16ToBytes(numChannels)); // NumChannels
    builder.add(_int32ToBytes(sampleRate)); // SampleRate
    builder.add(_int32ToBytes(byteRate)); // ByteRate
    builder.add(_int16ToBytes(blockAlign)); // BlockAlign
    builder.add(_int16ToBytes(bitsPerSample)); // BitsPerSample

    // Data chunk
    builder.add('data'.codeUnits); // Subchunk2ID
    builder.add(_int32ToBytes(dataSize)); // Subchunk2Size
    builder.add(pcmData); // PCM data

    return builder.toBytes();
  }

  Uint8List _int16ToBytes(int value) {
    return Uint8List(2)..buffer.asByteData().setInt16(0, value, Endian.little);
  }

  Uint8List _int32ToBytes(int value) {
    return Uint8List(4)..buffer.asByteData().setInt32(0, value, Endian.little);
  }
}
