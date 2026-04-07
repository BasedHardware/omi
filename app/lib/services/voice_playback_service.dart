import 'dart:convert';
import 'dart:math';
import 'dart:typed_data';

import 'package:http/http.dart' as http;
import 'package:just_audio/just_audio.dart';

import 'package:omi/backend/http/api/config.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/utils/logger.dart';

/// Service that speaks AI responses aloud using ElevenLabs TTS.
/// Mirrors the desktop FloatingBarVoicePlaybackService.
class VoicePlaybackService {
  static final VoicePlaybackService _instance = VoicePlaybackService._();
  static VoicePlaybackService get instance => _instance;

  VoicePlaybackService._();

  static const String _defaultVoiceId = 'BAMYoBHLZM7lJgJAmFz0'; // Sloane
  static const String _defaultModelId = 'eleven_turbo_v2_5';
  static const int _minimumChunkLength = 40;
  static const int _preferredChunkLength = 120;
  static const int _emergencyChunkLength = 200;
  static const double _playbackRate = 1.2;

  static const List<String> _fillerPhrases = [
    'Let me check.',
    'One moment.',
    'Looking into it.',
    'Let me see.',
    'Checking now.',
    'Hold on.',
    'One sec.',
    'Working on it.',
  ];

  String? _apiKey;
  bool _apiKeyFetched = false;

  final AudioPlayer _audioPlayer = AudioPlayer();
  final List<Uint8List> _audioQueue = [];
  bool _isPlaying = false;
  bool _hasStartedRealPlayback = false;

  String _streamedText = '';
  String _bufferedText = '';
  final List<String> _synthesisQueue = [];
  bool _isSynthesizing = false;

  bool _stopped = false;

  /// Initialize by fetching the ElevenLabs API key from the backend.
  Future<void> init() async {
    if (_apiKeyFetched) return;
    _apiKey = await getElevenLabsApiKey();
    _apiKeyFetched = true;
    if (_apiKey != null) {
      Logger.debug('VoicePlaybackService: ElevenLabs API key loaded');
    } else {
      Logger.debug('VoicePlaybackService: No ElevenLabs API key available');
    }
  }

  bool get isEnabled => SharedPreferencesUtil().voiceResponseEnabled;

  /// Play a random filler phrase while waiting for the AI response.
  Future<void> playFiller() async {
    if (!isEnabled) return;
    await init();
    if (_apiKey == null) return;

    _stopped = false;
    _hasStartedRealPlayback = false;
    final phrase = _fillerPhrases[Random().nextInt(_fillerPhrases.length)];

    try {
      final audioData = await _synthesizeSpeech(phrase);
      if (_stopped || _hasStartedRealPlayback) return;
      await _playAudioData(audioData);
    } catch (e) {
      Logger.debug('VoicePlaybackService: filler playback failed: $e');
    }
  }

  /// Feed streaming text from the AI response. Call with isFinal=true when done.
  Future<void> updateStreamingResponse(String text, {bool isFinal = false}) async {
    if (!isEnabled || _stopped) return;
    await init();
    if (_apiKey == null) return;

    if (!_shouldSpeak(text)) return;

    // Reset if text doesn't continue from previous
    if (!text.startsWith(_streamedText)) {
      _streamedText = '';
      _bufferedText = '';
      _synthesisQueue.clear();
      _audioQueue.clear();
    }

    // Stop filler when real content arrives
    if (!_hasStartedRealPlayback && text.isNotEmpty) {
      _hasStartedRealPlayback = true;
      await _audioPlayer.stop();
    }

    if (text.length > _streamedText.length) {
      final newText = text.substring(_streamedText.length);
      _streamedText = text;
      _bufferedText += newText;
      _drainBufferedText(isFinal: isFinal);
    } else if (isFinal) {
      _drainBufferedText(isFinal: true);
    }
  }

  void _drainBufferedText({required bool isFinal}) {
    while (true) {
      final boundary = _nextChunkBoundary(_bufferedText, isFinal: isFinal);
      if (boundary == null) break;

      final chunk = _bufferedText.substring(0, boundary).trim();
      _bufferedText = _bufferedText.substring(boundary).trim();

      if (chunk.isNotEmpty && _shouldSpeak(chunk)) {
        _synthesisQueue.add(chunk);
        _startSynthesisIfNeeded();
      }
    }
  }

  void _startSynthesisIfNeeded() {
    if (_isSynthesizing || _synthesisQueue.isEmpty || _stopped) return;

    final text = _synthesisQueue.removeAt(0);
    _isSynthesizing = true;

    _synthesizeSpeech(text).then((audioData) {
      _isSynthesizing = false;
      if (_stopped) return;
      _audioQueue.add(audioData);
      _playNextIfNeeded();
      _startSynthesisIfNeeded();
    }).catchError((e) {
      _isSynthesizing = false;
      Logger.debug('VoicePlaybackService: chunk synthesis failed: $e');
      _startSynthesisIfNeeded();
    });
  }

  void _playNextIfNeeded() {
    if (_isPlaying || _audioQueue.isEmpty || _stopped) return;
    _isPlaying = true;
    final data = _audioQueue.removeAt(0);
    _playAudioData(data).then((_) {
      _isPlaying = false;
      _playNextIfNeeded();
    }).catchError((e) {
      _isPlaying = false;
      Logger.debug('VoicePlaybackService: playback failed: $e');
      _playNextIfNeeded();
    });
  }

  Future<void> _playAudioData(Uint8List data) async {
    try {
      final source = _BytesAudioSource(data);
      await _audioPlayer.setAudioSource(source);
      await _audioPlayer.setSpeed(_playbackRate);
      await _audioPlayer.play();
      // Wait for playback to complete
      await _audioPlayer.processingStateStream.firstWhere((s) => s == ProcessingState.completed);
    } catch (e) {
      Logger.debug('VoicePlaybackService: _playAudioData error: $e');
    }
  }

  /// Stop all playback and reset state.
  void stop() {
    _stopped = true;
    _audioPlayer.stop();
    _streamedText = '';
    _bufferedText = '';
    _synthesisQueue.clear();
    _audioQueue.clear();
    _isSynthesizing = false;
    _isPlaying = false;
    _hasStartedRealPlayback = false;
  }

  Future<Uint8List> _synthesizeSpeech(String text) async {
    final uri = Uri.parse('https://api.elevenlabs.io/v1/text-to-speech/$_defaultVoiceId');
    final body = jsonEncode({
      'text': text,
      'model_id': _defaultModelId,
      'output_format': 'mp3_44100_128',
      'voice_settings': {
        'stability': 0.34,
        'similarity_boost': 0.88,
        'style': 0.12,
        'use_speaker_boost': true,
      },
    });

    final response = await http.post(
      uri,
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'audio/mpeg',
        'xi-api-key': _apiKey!,
      },
      body: body,
    );

    if (response.statusCode >= 200 && response.statusCode < 300) {
      return response.bodyBytes;
    } else {
      throw Exception(
          'ElevenLabs TTS failed (${response.statusCode}): ${response.body.substring(0, min(300, response.body.length))}');
    }
  }

  bool _shouldSpeak(String text) {
    final lowercased = text.toLowerCase();
    if (lowercased == 'failed to get a response. please try again.') return false;
    if (lowercased.startsWith('\u26a0\ufe0f') || lowercased.startsWith('warning:')) return false;
    return true;
  }

  int? _nextChunkBoundary(String text, {required bool isFinal}) {
    final trimmed = text.trim();
    if (trimmed.isEmpty) return null;

    if (isFinal) return text.length;
    if (text.length < _minimumChunkLength) return null;

    final preferredLimit = min(text.length, _preferredChunkLength);
    final preferredSlice = text.substring(0, preferredLimit);
    final punctIdx = _lastIndexOfAny(preferredSlice, '.!?\n');
    if (punctIdx != null) return punctIdx + 1;

    if (text.length < _preferredChunkLength) return null;

    final emergencyLimit = min(text.length, _emergencyChunkLength);
    final emergencySlice = text.substring(0, emergencyLimit);
    final emergPunctIdx = _lastIndexOfAny(emergencySlice, '.!?\n');
    if (emergPunctIdx != null) return emergPunctIdx + 1;

    if (text.length < _emergencyChunkLength) return null;

    final clauseIdx = _lastIndexOfAny(emergencySlice, ',;:\n');
    if (clauseIdx != null) return clauseIdx + 1;

    // Find last whitespace
    for (int i = emergencySlice.length - 1; i >= 0; i--) {
      if (emergencySlice[i] == ' ' || emergencySlice[i] == '\t') return i;
    }

    return emergencyLimit;
  }

  int? _lastIndexOfAny(String text, String chars) {
    for (int i = text.length - 1; i >= 0; i--) {
      if (chars.contains(text[i])) return i;
    }
    return null;
  }
}

/// StreamAudioSource that plays from in-memory bytes.
class _BytesAudioSource extends StreamAudioSource {
  final Uint8List _bytes;

  _BytesAudioSource(this._bytes);

  @override
  Future<StreamAudioResponse> request([int? start, int? end]) async {
    start ??= 0;
    end ??= _bytes.length;
    return StreamAudioResponse(
      sourceLength: _bytes.length,
      contentLength: end - start,
      offset: start,
      stream: Stream.value(List<int>.from(_bytes.sublist(start, end))),
      contentType: 'audio/mpeg',
    );
  }
}
