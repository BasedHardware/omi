// Plays Omi's spoken response when the user talks to the device via the
// hardware button. Ports the chunking + pipelined-playback architecture from
// `desktop/Desktop/Sources/FloatingControlBar/FloatingBarVoicePlaybackService.swift`.

import 'dart:async';

import 'package:audio_session/audio_session.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:just_audio/just_audio.dart';

import 'package:omi/backend/http/api/tts.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/utils/logger.dart';

// Chunk-size heuristics ported verbatim from the desktop Swift service.
// First sentence should feel snappy, later sentences can batch more text to
// reduce round trips.
const int _firstChunkMinChars = 40;
const int _firstChunkIdealChars = 120;
const int _firstChunkMaxChars = 200;
const int _chunkMinChars = 320;
const int _chunkIdealChars = 520;
const int _chunkMaxChars = 800;

class OmiVoicePlaybackService {
  OmiVoicePlaybackService._();
  static final OmiVoicePlaybackService instance = OmiVoicePlaybackService._();

  final AudioPlayer _player = AudioPlayer();
  final FlutterTts _fallbackTts = FlutterTts();

  bool _initialized = false;
  String? _activeMessageId;

  // What the client already sent to synthesize, measured against the cumulative
  // streamed text. We always use `_spoken` as the slice boundary.
  int _spoken = 0;

  final List<_PendingSynthesis> _synthesisQueue = [];
  final List<Uint8List> _audioQueue = [];
  bool _synthesizing = false;
  bool _isPlayingQueue = false;
  bool _sessionActive = false;

  bool get isSpeaking => _sessionActive && (_isPlayingQueue || _audioQueue.isNotEmpty || _synthesizing);

  Future<void> _ensureInitialized() async {
    if (_initialized) return;
    _initialized = true;

    try {
      final session = await AudioSession.instance;
      await session.configure(const AudioSessionConfiguration.speech());
      session.interruptionEventStream.listen((event) {
        if (event.begin) {
          _player.pause();
        } else {
          // Don't auto-resume — the reply is stale after an interruption.
          interrupt();
        }
      });
      // Stop immediately when headphones are unplugged mid-playback so the
      // reply doesn't suddenly blast out of the phone speaker in public.
      session.becomingNoisyEventStream.listen((_) {
        debugPrint('OmiVoicePlayback: headphones disconnected — interrupting');
        interrupt();
      });
    } catch (e) {
      Logger.debug('OmiVoicePlaybackService: audio_session configure failed: $e');
    }

    _player.playerStateStream.listen((state) {
      if (state.processingState == ProcessingState.completed) {
        _playNextFromQueue();
      }
    });

    try {
      await _fallbackTts.setSpeechRate(0.5);
      await _fallbackTts.setVolume(1.0);
      await _fallbackTts.setPitch(1.0);
    } catch (_) {}
  }

  /// Start a new response lifecycle. Cancels any prior in-flight playback.
  Future<void> beginResponse({required String messageId}) async {
    final mode = SharedPreferencesUtil().voiceResponseMode;
    debugPrint('OmiVoicePlayback: beginResponse messageId=$messageId mode=$mode');
    if (mode == 0) return; // Off

    await _ensureInitialized();

    // Mode 1 (headphones only): skip if no private-listening output is
    // connected so Omi never blasts a private answer out of the phone
    // speaker in public. Mode 2 (always) bypasses this gate.
    if (mode == 1) {
      final headphones = await _hasHeadphonesConnected();
      if (!headphones) {
        debugPrint('OmiVoicePlayback: no headphones — skipping playback (mode=headphones)');
        return;
      }
    }

    if (_activeMessageId == messageId) {
      // Same response already in-flight; no-op.
      return;
    }

    await _clearInFlightState();
    _activeMessageId = messageId;
    _spoken = 0;

    await _activateSession();
  }

  /// True if at least one "private-listening" output is connected — AirPods
  /// (Bluetooth A2DP/LE/SCO), wired 3.5mm / Lightning headphones, USB headset,
  /// or AirPlay. False for the built-in speaker / earpiece alone.
  Future<bool> _hasHeadphonesConnected() async {
    try {
      final session = await AudioSession.instance;
      final devices = await session.getDevices(includeInputs: false);
      const headphoneTypes = <AudioDeviceType>{
        AudioDeviceType.bluetoothA2dp,
        AudioDeviceType.bluetoothLe,
        AudioDeviceType.bluetoothSco,
        AudioDeviceType.wiredHeadphones,
        AudioDeviceType.wiredHeadset,
        AudioDeviceType.usbAudio,
        AudioDeviceType.airPlay,
        AudioDeviceType.lineAnalog,
        AudioDeviceType.lineDigital,
      };
      final hit = devices.any((d) => headphoneTypes.contains(d.type));
      debugPrint('OmiVoicePlayback: headphones=$hit (devices=${devices.map((d) => d.type).toList()})');
      return hit;
    } catch (e) {
      debugPrint('OmiVoicePlayback: headphone check failed: $e — skipping playback');
      // Fail closed: if we can't tell whether headphones are connected,
      // we'd rather stay silent than blast audio from the speaker.
      return false;
    }
  }

  /// Called on every streamed text update. [fullText] is the cumulative AI
  /// response so far. [isFinal] means this is the last chunk.
  void updateStreamingResponse({
    required String messageId,
    required String fullText,
    required bool isFinal,
  }) {
    if (SharedPreferencesUtil().voiceResponseMode == 0) return;
    if (_activeMessageId != messageId) {
      Logger.log(
          'OmiVoicePlayback: updateStreamingResponse skipped — activeId=$_activeMessageId != incoming=$messageId');
      return;
    }
    Logger.log('OmiVoicePlayback: updateStreamingResponse len=${fullText.length} isFinal=$isFinal spoken=$_spoken');

    final cleaned = _cleanedPlaybackText(fullText);
    if (_spoken >= cleaned.length && !isFinal) return;

    while (_spoken < cleaned.length) {
      final boundary = _nextChunkBoundary(
        cleaned,
        start: _spoken,
        isFirstChunk: _synthesisQueue.isEmpty && _audioQueue.isEmpty && !_isPlayingQueue,
        isFinal: isFinal,
      );
      if (boundary == null) {
        break; // Not enough text yet — wait for more.
      }
      final sentence = cleaned.substring(_spoken, boundary).trim();
      _spoken = boundary;
      if (sentence.isEmpty) continue;
      _synthesisQueue.add(_PendingSynthesis(sentence));
    }

    if (isFinal && _spoken < cleaned.length) {
      // Flush any trailing text as one final chunk regardless of thresholds.
      final tail = cleaned.substring(_spoken).trim();
      _spoken = cleaned.length;
      if (tail.isNotEmpty) _synthesisQueue.add(_PendingSynthesis(tail));
    }

    _drainSynthesis();
  }

  /// Immediately cancel all synthesis + playback.
  Future<void> interrupt() async {
    _activeMessageId = null;
    _spoken = 0;
    _synthesisQueue.clear();
    _audioQueue.clear();
    _synthesizing = false;
    _isPlayingQueue = false;
    try {
      await _player.stop();
    } catch (_) {}
    try {
      await _fallbackTts.stop();
    } catch (_) {}
    await _deactivateSession();
  }

  // ---------------------------------------------------------------------------
  // Internals
  // ---------------------------------------------------------------------------

  Future<void> _clearInFlightState() async {
    _synthesisQueue.clear();
    _audioQueue.clear();
    _synthesizing = false;
    _isPlayingQueue = false;
    try {
      await _player.stop();
    } catch (_) {}
  }

  Future<void> _drainSynthesis() async {
    if (_synthesizing) return;
    if (_synthesisQueue.isEmpty) return;
    _synthesizing = true;

    while (_synthesisQueue.isNotEmpty) {
      if (SharedPreferencesUtil().voiceResponseMode == 0) {
        await interrupt();
        break;
      }
      final pending = _synthesisQueue.removeAt(0);
      debugPrint('OmiVoicePlayback: synthesizing "${pending.text}"');
      try {
        final bytes = await synthesizeSpeech(text: pending.text);
        debugPrint('OmiVoicePlayback: got ${bytes?.length ?? 0} MP3 bytes');
        if (bytes != null && bytes.isNotEmpty) {
          _audioQueue.add(bytes);
          _tryStartPlayback();
        }
      } on TtsUnavailableException catch (e) {
        Logger.log('TTS unavailable (${e.statusCode}) — falling back to system voice');
        // Fallback: speak the remaining sentence and any queued ones on-device.
        await _speakFallback(pending.text);
        for (final rest in _synthesisQueue) {
          await _speakFallback(rest.text);
        }
        _synthesisQueue.clear();
        break;
      } catch (e) {
        Logger.debug('synthesizeSpeech failed: $e');
        // Skip this sentence; keep the pipeline moving.
      }
    }

    _synthesizing = false;
    _maybeFinish();
  }

  Future<void> _speakFallback(String text) async {
    try {
      await _fallbackTts.speak(text);
    } catch (e) {
      Logger.debug('flutter_tts fallback failed: $e');
    }
  }

  void _tryStartPlayback() {
    if (_isPlayingQueue) return;
    _playNextFromQueue();
  }

  Future<void> _playNextFromQueue() async {
    if (_audioQueue.isEmpty) {
      _isPlayingQueue = false;
      _maybeFinish();
      return;
    }
    _isPlayingQueue = true;
    final bytes = _audioQueue.removeAt(0);
    try {
      await _player.setAudioSource(_BytesAudioSource(bytes));
      await _player.play();
    } catch (e) {
      Logger.debug('just_audio play failed: $e');
      _isPlayingQueue = false;
      // Skip this chunk and try the next one.
      _playNextFromQueue();
    }
  }

  void _maybeFinish() {
    if (_synthesisQueue.isEmpty && _audioQueue.isEmpty && !_isPlayingQueue && !_synthesizing) {
      // Small grace window so tail chunks from the SSE stream don't flap the
      // foreground service on/off rapidly.
      Future.delayed(const Duration(milliseconds: 500), () async {
        if (_synthesisQueue.isEmpty && _audioQueue.isEmpty && !_isPlayingQueue && !_synthesizing) {
          await _deactivateSession();
        }
      });
    }
  }

  Future<void> _activateSession() async {
    if (_sessionActive) return;
    _sessionActive = true;
    try {
      final session = await AudioSession.instance;
      await session.setActive(true);
    } catch (e) {
      _sessionActive = false;
      Logger.debug('OmiVoicePlaybackService: setActive(true) failed: $e');
    }
  }

  Future<void> _deactivateSession() async {
    if (!_sessionActive) return;
    _sessionActive = false;
    try {
      final session = await AudioSession.instance;
      await session.setActive(false);
    } catch (_) {}
  }

  // ---------------------------------------------------------------------------
  // Text cleaning + chunking — ports desktop's Swift helpers
  // ---------------------------------------------------------------------------

  String _cleanedPlaybackText(String input) {
    var text = input;

    // Strip code fences entirely
    text = text.replaceAll(RegExp(r'```[\s\S]*?```'), ' ');
    // Strip inline code
    text = text.replaceAll(RegExp(r'`[^`]*`'), ' ');
    // Bold / italic markers
    text = text.replaceAll(RegExp(r'\*\*|__'), '');
    text = text.replaceAll(RegExp(r'(?<!\*)\*(?!\*)'), '');
    text = text.replaceAll(RegExp(r'(?<!_)_(?!_)'), '');
    // Markdown links: [label](url) → label
    text = text.replaceAllMapped(RegExp(r'\[([^\]]+)\]\([^)]+\)'), (m) => m.group(1) ?? '');
    // Bare URLs
    text = text.replaceAll(RegExp(r'https?://\S+'), ' ');
    // Collapse whitespace
    text = text.replaceAll(RegExp(r'\s+'), ' ').trim();
    return text;
  }

  /// Returns the index at which to cut the next chunk, or null if we should
  /// wait for more text. Mirrors `FloatingBarVoicePlaybackService.nextChunkBoundary`.
  int? _nextChunkBoundary(
    String text, {
    required int start,
    required bool isFirstChunk,
    required bool isFinal,
  }) {
    final remaining = text.length - start;
    final minChars = isFirstChunk ? _firstChunkMinChars : _chunkMinChars;
    final idealChars = isFirstChunk ? _firstChunkIdealChars : _chunkIdealChars;
    final maxChars = isFirstChunk ? _firstChunkMaxChars : _chunkMaxChars;

    if (remaining < minChars && !isFinal) return null;

    // If we're at or past the max, we must cut here.
    if (remaining >= maxChars) {
      final hardCut = start + maxChars;
      return _lastBoundaryAtOrBefore(text, start, hardCut) ?? hardCut;
    }

    // Look for a sentence terminator between minChars and idealChars.
    final idealCut = start + idealChars.clamp(0, remaining);
    final boundary = _lastBoundaryAtOrBefore(text, start + minChars, idealCut);
    if (boundary != null) return boundary;

    // On final chunk, emit whatever we have.
    if (isFinal) return text.length;

    return null;
  }

  int? _lastBoundaryAtOrBefore(String text, int lowerInclusive, int upperExclusive) {
    if (upperExclusive > text.length) upperExclusive = text.length;
    if (lowerInclusive >= upperExclusive) return null;
    for (var i = upperExclusive - 1; i >= lowerInclusive; i--) {
      final c = text[i];
      if (c == '.' || c == '!' || c == '?' || c == '\n') {
        return i + 1; // include the terminator
      }
    }
    for (var i = upperExclusive - 1; i >= lowerInclusive; i--) {
      if (text[i] == ',' || text[i] == ';' || text[i] == ':') {
        return i + 1;
      }
    }
    for (var i = upperExclusive - 1; i >= lowerInclusive; i--) {
      if (text[i] == ' ') {
        return i + 1;
      }
    }
    return null;
  }
}

class _PendingSynthesis {
  final String text;
  _PendingSynthesis(this.text);
}

/// In-memory `just_audio` source for a single MP3 chunk.
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
      stream: Stream.value(_bytes.sublist(start, end)),
      contentType: 'audio/mpeg',
    );
  }
}
