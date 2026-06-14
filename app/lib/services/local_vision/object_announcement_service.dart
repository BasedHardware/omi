import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter_tts/flutter_tts.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/utils/logger.dart';

class ObjectAnnouncementService extends ChangeNotifier {
  ObjectAnnouncementService._();

  static final ObjectAnnouncementService instance = ObjectAnnouncementService._();

  final FlutterTts _tts = FlutterTts();
  final List<String> _queue = [];
  static const int _maxQueuedAnnouncements = 1;

  bool _initialized = false;
  bool _speaking = false;
  DateTime? _lastAnnouncementAt;
  String? _lastSpokenText;

  bool get isSpeaking => _speaking;
  DateTime? get lastAnnouncementAt => _lastAnnouncementAt;
  String? get lastSpokenText => _lastSpokenText;

  Future<void> _ensureInitialized() async {
    if (_initialized) return;
    _initialized = true;

    try {
      await _tts.setLanguage('en-US');
      await _tts.setVolume(1.0);
      await _tts.setPitch(1.0);
      await _tts.setSpeechRate(SharedPreferencesUtil().localYoloeSpeechRate);
      await _tts.awaitSpeakCompletion(true);
      _tts.setCompletionHandler(() {
        _speaking = false;
        notifyListeners();
        _speakNextQueued();
      });
      _tts.setErrorHandler((message) {
        _speaking = false;
        Logger.debug('Local YOLOE TTS error: $message');
        notifyListeners();
        _speakNextQueued();
      });
    } catch (e) {
      Logger.debug('Local YOLOE TTS initialization failed: $e');
    }
  }

  String formatObjectsMessage(List<String> labels) {
    final cleaned = labels.map((label) => label.trim()).where((label) => label.isNotEmpty).toSet().toList();
    if (cleaned.isEmpty) return '';
    if (cleaned.length == 1) return 'I see a ${cleaned.first}.';
    if (cleaned.length == 2) return 'I see a ${cleaned[0]} and ${cleaned[1]}.';
    return 'I see a ${cleaned.sublist(0, cleaned.length - 1).join(', ')}, and ${cleaned.last}.';
  }

  Future<void> speakObjects(List<String> labels, {bool bypassQuietPeriod = false}) async {
    final message = formatObjectsMessage(labels);
    if (message.isEmpty) return;
    await speak(message, bypassQuietPeriod: bypassQuietPeriod);
  }

  Future<void> speak(String text, {bool force = false, bool bypassQuietPeriod = false}) async {
    final trimmed = text.trim();
    if (trimmed.isEmpty) return;

    final prefs = SharedPreferencesUtil();
    if (!force && !prefs.localYoloeVoiceEnabled) return;
    if (!Platform.isAndroid && !force) {
      Logger.debug('Local YOLOE TTS skipped: Android-only announcement mode');
      return;
    }

    final now = DateTime.now();
    final last = _lastAnnouncementAt;
    if (!force && !bypassQuietPeriod && last != null) {
      final elapsed = now.difference(last).inMilliseconds / 1000;
      if (elapsed < prefs.localYoloeMinSecondsBetweenAnnouncements) return;
    }

    await _ensureInitialized();
    await _tts.setSpeechRate(prefs.localYoloeSpeechRate);

    if (prefs.localYoloeInterruptSpeech) {
      await stop();
      await _speakNow(trimmed);
      return;
    }

    if (_speaking) {
      if (_queue.length >= _maxQueuedAnnouncements) {
        _queue.removeAt(0);
      }
      _queue.add(trimmed);
      notifyListeners();
      return;
    }

    await _speakNow(trimmed);
  }

  Future<void> stop() async {
    _queue.clear();
    _speaking = false;
    try {
      await _tts.stop();
    } catch (e) {
      Logger.debug('Local YOLOE TTS stop failed: $e');
    }
    notifyListeners();
  }

  Future<void> _speakNow(String text) async {
    _speaking = true;
    _lastAnnouncementAt = DateTime.now();
    _lastSpokenText = text;
    notifyListeners();
    Logger.debug('Local YOLOE TTS speaking: $text');
    try {
      await _tts.speak(text);
    } catch (e) {
      _speaking = false;
      Logger.debug('Local YOLOE TTS speak failed: $e');
      notifyListeners();
    }
  }

  void _speakNextQueued() {
    if (_queue.isEmpty) return;
    final next = _queue.removeAt(0);
    unawaited(_speakNow(next));
  }
}
