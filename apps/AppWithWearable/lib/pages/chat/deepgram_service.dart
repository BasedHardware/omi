import 'dart:io';
import 'dart:typed_data';

import 'package:audioplayers/audioplayers.dart';
import 'package:deepgram_speech_to_text/deepgram_speech_to_text.dart';
import 'package:friend_private/backend/preferences.dart';
import 'dart:async';
import 'package:record/record.dart';
import 'package:path_provider/path_provider.dart';

class DeepgramService {
  final AudioRecorder _microphone = AudioRecorder();
  final AudioPlayer _audioPlayer = AudioPlayer();
  late Deepgram _deepgram;
  late DeepgramLiveTranscriber _transcriber;
  StreamSubscription? _playerCompleteSubscription;
  bool speaking = false;

  void init() {
    final String deepgramApiKey = getDeepgramApiKeyForUsage();
    _deepgram = Deepgram(deepgramApiKey, baseQueryParams: {});
  }

  Future<DeepgramLiveTranscriber> startTranscribing(model, endpointing) async {
    await _microphone.hasPermission();

    final audioStream = await _microphone.startStream(const RecordConfig(
      encoder: AudioEncoder.pcm16bits,
      sampleRate: 16000,
      numChannels: 1,
    ));

    print('Recording started...');

    final liveParams = {
      'language': 'en',
      'model': model,
      'endpointing': endpointing,
      'utterance_end_ms': 1000,
      'interim_results': true,
      'encoding': 'linear16',
      'sample_rate': 16000,
      'smart_format': true,
    };

    _transcriber = _deepgram.createLiveTranscriber(audioStream, queryParams: liveParams);

    _transcriber.start();

    return _transcriber;
  }

  Future<void> stopTranscribing() async {
    await _microphone.stop();
    if (_transcriber != null) {
      _transcriber.close();
    }
  }

  Future<void> pauseStream() async {
    _transcriber.pause();
  }

  Future<void> resumeStream() async {
    _transcriber.resume();
  }

  Future<String> getLocalFilePath(String filename) async {
    final appDocDir = await getApplicationDocumentsDirectory();
    String appDocPath = appDocDir.path;
    return '$appDocPath/$filename';
  }

  Future<String> saveDataToFile(String filename, Uint8List data) async {
    final path = await getLocalFilePath(filename);
    await File(path).writeAsBytes(data);
    return path;
  }

  Future<String> _saveAudioToFile(Uint8List audioBytes) async {
    final Directory tempDir = await getTemporaryDirectory();
    final String tempPath = tempDir.path;
    final String filePath = '$tempPath/${DateTime.now().millisecondsSinceEpoch}.mp3';
    final File file = File(filePath);
    await file.writeAsBytes(audioBytes);
    return filePath;
  }

  Future<void> playTTS(text, model) async {
    final response = await _deepgram.speakFromText(
      text,
      queryParams: {
        'model': model,
        'encoding': 'mp3'
      });

    final Uint8List audioBytes = response.data;
    final String filePath = await _saveAudioToFile(audioBytes);

    // Cancel any existing player complete subscription
    await _playerCompleteSubscription?.cancel();

    // Create a completer to block until the audio has completed playing
    final Completer<void> completer = Completer<void>();

    // Listen for the completion event
    _playerCompleteSubscription = _audioPlayer.onPlayerComplete.listen((event) {
      if (!completer.isCompleted) {
        completer.complete();
      }
    });

    await _audioPlayer.play(DeviceFileSource(filePath));

    // Await the completer's completion
    await completer.future;
  }
}
