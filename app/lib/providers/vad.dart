import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/services.dart';
import 'package:flutter_silero_vad/flutter_silero_vad.dart';
import 'package:friend_private/utils/audio/wav_bytes.dart';
import 'package:opus_dart/opus_dart.dart';
import 'package:path_provider/path_provider.dart';

/// A service that processes audio data and performs Voice Activity Detection (VAD) using the Silero VAD model.
/// It can handle audio data from any source and operates independently of any specific audio session or recorder library.
class AudioProcessorService {
  /// The Silero VAD instance used for voice activity detection.
  final vad = FlutterSileroVad();

  /// The sample rate of the audio data (e.g., 8000 or 16000 Hz).
  int sampleRate;

  /// The frame size for VAD processing in milliseconds.
  int frameSize; // in milliseconds

  /// Number of bits per sample (usually 16 for PCM data).
  final int bitsPerSample = 16;

  /// Number of audio channels (1 for mono, 2 for stereo).
  final int numChannels = 1;

  /// Indicates whether the service has been initialized.
  bool isInited = false;

  /// Buffer to hold previous audio data for padding before detected speech.
  final lastAudioData = <int>[];

  /// Timestamp of the last detected voice activity.
  DateTime? lastActiveTime;

  /// A stream controller that broadcasts processed audio data segments containing speech.
  final processedAudioStreamController = StreamController<List<int>>.broadcast();

  /// Subscription to the processed audio stream.
  StreamSubscription<List<int>>? processedAudioSubscription;

  /// Buffer to accumulate audio frames for processing.
  final frameBuffer = <int>[];

  /// The duration in milliseconds to wait after silence is detected before processing the buffered audio.
  static const bufferTimeInMilliseconds = 700;

  /// Buffer to accumulate audio data that contains detected speech.
  final audioDataBuffer = <int>[];

  /// Creates an instance of [AudioProcessorService] with the specified sample rate and frame size.
  ///
  /// [sampleRate]: The sample rate of the audio data (default is 16000 Hz).
  /// [frameSize]: The frame size for VAD processing in milliseconds (default is 40 ms).
  /// model was trained with 30ms? but if 40ms set, doesn't do shit
  AudioProcessorService({this.sampleRate = 16000, this.frameSize = 40});


  /// Gets the file path where the VAD model is stored.
  Future<String> get modelPath async => '${(await getApplicationSupportDirectory()).path}/silero_vad.onnx';

  /// Opus decoder instance
  late SimpleOpusDecoder opusDecoder;
  WavBytesUtil wavBytesUtil = WavBytesUtil();
  final validFrames = <int>[];

  /// Initializes the VAD model and prepares the service for processing audio data.
  Future<void> init() async {
    await onnxModelToLocal();
    await vad.initialize(
      modelPath: await modelPath,
      sampleRate: sampleRate,
      frameSize: frameSize,
      threshold: 0.2,
      minSilenceDurationMs: 100,
      speechPadMs: 0,
    );
    opusDecoder = SimpleOpusDecoder(sampleRate: sampleRate, channels: 1);
    isInited = true;

    // processedAudioSubscription = processedAudioStreamController.stream.listen((buffer) async {
    //   final outputPath = '${(await getApplicationDocumentsDirectory()).path}/output.wav';
    //   saveAsWav(buffer, outputPath);
    //   print('saved');
    // });
    Timer(const Duration(seconds: 30), () async {
      print('Timer started');
      Uint8List wavBytes = wavBytesUtil.getUInt8ListBytes(validFrames, sampleRate);
      final file = File('${(await getApplicationDocumentsDirectory()).path}/output.wav');
      await file.writeAsBytes(wavBytes);
    });
  }

  /// Processes incoming audio data chunks and performs VAD on them.
  ///
  /// [buffer]: A list of bytes representing the audio data to process.
  void processAudioData(List<int> buffer) async {
    assert(isInited);
    if (buffer.isEmpty) return;

    // print('Opus Buffer Size: ${buffer.length} bytes');
    buffer = opusDecoder.decode(input: Uint8List.fromList(buffer.sublist(3))); // decode opus
    frameBuffer.addAll(buffer);

    // int frameByteSize = frameSize * 2 * sampleRate ~/ 1000; // frameSize in bytes
    int frameByteSize = frameSize * sampleRate * numChannels * (bitsPerSample ~/ 8) ~/ 1000;
    // print('Frame Byte Size: $frameByteSize vs ${frameBuffer.length}');
    while (frameBuffer.length >= frameByteSize) {
      final frame = frameBuffer.sublist(0, frameByteSize);
      frameBuffer.removeRange(0, frameByteSize);
      await _handleProcessedAudio(frame);
    }
    // trigger code in 20 seconds with timer
  }

  /// Handles the processed audio frames, applies VAD, and buffers the audio data accordingly.
  ///
  /// [buffer]: A list of bytes representing a single frame of audio data.
  Future<void> _handleProcessedAudio(List<int> buffer) async {
    final transformedBuffer = _transformBuffer(buffer);
    final transformedBufferFloat = transformedBuffer.map((e) => e / 32768).toList();
    // print('First 10 decoded samples: ${transformedBuffer.take(10).toList()}');
    // print('First 5 samples: ${transformedBuffer.take(5).toList()}');
    // print('First 5 normalized samples: ${transformedBufferFloat.take(5)}');

    final isActivated = await vad.predict(Float32List.fromList(transformedBufferFloat));
    // print('VAD Activation: $isActivated');

    if (isActivated == true) {
      lastActiveTime = DateTime.now();
      audioDataBuffer.addAll(lastAudioData);
      lastAudioData.clear();
      audioDataBuffer.addAll(buffer);
    } else if (lastActiveTime != null) {
      audioDataBuffer.addAll(buffer);
      // print('Silence Duration: ${DateTime.now().difference(lastActiveTime!)}');
      // After a certain period of silence, process the buffered audio
      if (DateTime.now().difference(lastActiveTime!) > const Duration(milliseconds: bufferTimeInMilliseconds)) {
        processedAudioStreamController.add([...audioDataBuffer]);
        print(
            'Processing Valid Frames: ${audioDataBuffer.length}, seconds: ${audioDataBuffer.length / sampleRate / numChannels / bitsPerSample * 8}');
        validFrames.addAll(audioDataBuffer);
        audioDataBuffer.clear();
        lastActiveTime = null;
      }
    } else {
      lastAudioData.addAll(buffer);
      // Keep 2 seconds worth of data
      final threshold = sampleRate * 2 * numChannels * bitsPerSample ~/ 8;
      if (lastAudioData.length > threshold) {
        lastAudioData.removeRange(0, lastAudioData.length - threshold);
      }
    }
  }

  /// Saves the provided audio buffer as a WAV file at the specified file path.
  ///
  /// [buffer]: A list of bytes representing the audio data to save.
  /// [filePath]: The file path where the WAV file will be saved.
  void saveAsWav(List<int> buffer, String filePath) {
    // Convert PCM data
    final bytes = Uint8List.fromList(buffer);
    final pcmData = Int16List.view(bytes.buffer);
    final byteBuffer = ByteData(pcmData.length * 2);

    for (var i = 0; i < pcmData.length; i++) {
      byteBuffer.setInt16(i * 2, pcmData[i], Endian.little);
    }

    final wavHeader = ByteData(44);
    final pcmBytes = byteBuffer.buffer.asUint8List();

    // RIFF chunk
    wavHeader
      ..setUint8(0x00, 0x52) // 'R'
      ..setUint8(0x01, 0x49) // 'I'
      ..setUint8(0x02, 0x46) // 'F'
      ..setUint8(0x03, 0x46) // 'F'
      ..setUint32(4, 36 + pcmBytes.length, Endian.little) // ChunkSize
      ..setUint8(0x08, 0x57) // 'W'
      ..setUint8(0x09, 0x41) // 'A'
      ..setUint8(0x0A, 0x56) // 'V'
      ..setUint8(0x0B, 0x45) // 'E'
      ..setUint8(0x0C, 0x66) // 'f'
      ..setUint8(0x0D, 0x6D) // 'm'
      ..setUint8(0x0E, 0x74) // 't'
      ..setUint8(0x0F, 0x20) // ' '
      ..setUint32(16, 16, Endian.little) // Subchunk1Size
      ..setUint16(20, 1, Endian.little) // AudioFormat
      ..setUint16(22, numChannels, Endian.little) // NumChannels
      ..setUint32(24, sampleRate, Endian.little) // SampleRate
      ..setUint32(
        28,
        sampleRate * numChannels * bitsPerSample ~/ 8,
        Endian.little,
      ) // ByteRate
      ..setUint16(
        32,
        numChannels * bitsPerSample ~/ 8,
        Endian.little,
      ) // BlockAlign
      ..setUint16(34, bitsPerSample, Endian.little) // BitsPerSample

      // data chunk
      ..setUint8(0x24, 0x64) // 'd'
      ..setUint8(0x25, 0x61) // 'a'
      ..setUint8(0x26, 0x74) // 't'
      ..setUint8(0x27, 0x61) // 'a'
      ..setUint32(40, pcmBytes.length, Endian.little); // Subchunk2Size

    File(filePath).writeAsBytesSync(wavHeader.buffer.asUint8List() + pcmBytes);
  }

  /// Transforms a list of bytes into an [Int16List] for processing.
  ///
  /// [buffer]: A list of bytes representing audio data.
  ///
  /// Returns an [Int16List] view of the byte buffer.
  Int16List _transformBuffer(List<int> buffer) {
    final bytes = Uint8List.fromList(buffer);
    return Int16List.view(bytes.buffer);
  }

  /// Copies the ONNX VAD model from the assets to the local application directory.
  Future<void> onnxModelToLocal() async {
    final data = await rootBundle.load('assets/silero_vad.v5.onnx');
    final bytes = data.buffer.asUint8List(data.offsetInBytes, data.lengthInBytes);
    File(await modelPath).writeAsBytesSync(bytes);
  }
}
