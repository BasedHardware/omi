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
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';
import 'package:omi/utils/logger.dart';

/// Registry ints cannot be omitted. Lifecycles that never start audio report this.
const int _noAudioLatencyMs = -1;

/// Output snapshot taken once at the start of a playback attempt.
@visibleForTesting
class VoicePlaybackOutputSnapshot {
  final bool headphonesConnected;
  final bool checkFailed;
  final VoiceReplyPlaybackOutputRoute route;

  const VoicePlaybackOutputSnapshot({
    required this.headphonesConnected,
    required this.checkFailed,
    required this.route,
  });
}

/// Test seam for the process-wide playback singleton. Production leaves this null.
@visibleForTesting
class VoicePlaybackDebugHooks {
  final Future<Uint8List?> Function({required String text})? synthesize;
  final Future<void> Function(Uint8List bytes)? play;
  final Future<void> Function()? stopPlayback;
  final Future<void> Function(String text)? speak;
  final Future<void> Function()? stopSpeak;
  final Future<VoicePlaybackOutputSnapshot> Function()? probeOutput;
  final DateTime Function()? now;
  final Future<void> Function(Duration duration)? delay;

  const VoicePlaybackDebugHooks({
    this.synthesize,
    this.play,
    this.stopPlayback,
    this.speak,
    this.stopSpeak,
    this.probeOutput,
    this.now,
    this.delay,
  });
}

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

  AudioPlayer? _playerField;
  FlutterTts? _fallbackTtsField;
  AudioPlayer get _player => _playerField ??= AudioPlayer(handleInterruptions: false);
  FlutterTts get _fallbackTts => _fallbackTtsField ??= FlutterTts();

  @visibleForTesting
  VoicePlaybackDebugHooks? debugHooks;

  bool _initialized = false;
  String? _activeMessageId;

  bool _lifecycleOpen = false;
  int _lifecycleToken = 0;
  DateTime? _lifecycleStartedAt;
  VoiceReplyPlaybackMode _lifecycleMode = VoiceReplyPlaybackMode.off;
  VoiceReplyPlaybackOutputRoute _lifecycleRoute = VoiceReplyPlaybackOutputRoute.unknown;
  int _chunksRequested = 0;
  int _chunksPlayed = 0;
  int _chunksDropped = 0;
  bool _usedFallback = false;
  VoiceReplyPlaybackFallbackReason _fallbackReason = VoiceReplyPlaybackFallbackReason.none;
  DateTime? _firstAudioAt;

  // What the client already sent to synthesize, measured against the cumulative
  // streamed text. We always use `_spoken` as the slice boundary.
  int _spoken = 0;

  final List<_PendingSynthesis> _synthesisQueue = [];
  final List<Uint8List> _audioQueue = [];
  bool _synthesizing = false;
  bool _isPlayingQueue = false;
  bool _sessionActive = false;
  bool _pausedByInterruption = false;

  bool get isSpeaking => _sessionActive && (_isPlayingQueue || _audioQueue.isNotEmpty || _synthesizing);

  Future<void> _ensureInitialized() async {
    if (_initialized) return;
    if (debugHooks != null) {
      _initialized = true;
      return;
    }
    _initialized = true;

    try {
      final session = await AudioSession.instance;
      await session.configure(
        const AudioSessionConfiguration(
          avAudioSessionCategory: AVAudioSessionCategory.playback,
          avAudioSessionMode: AVAudioSessionMode.voicePrompt,
          androidAudioAttributes: AndroidAudioAttributes(
            contentType: AndroidAudioContentType.speech,
            usage: AndroidAudioUsage.assistant,
          ),
          androidAudioFocusGainType: AndroidAudioFocusGainType.gain,
          androidWillPauseWhenDucked: false,
        ),
      );
      session.interruptionEventStream.listen(_onInterruption);
      // Stop immediately when headphones are unplugged mid-playback so the
      // reply doesn't suddenly blast out of the phone speaker in public.
      session.becomingNoisyEventStream.listen((_) {
        debugPrint('OmiVoicePlayback: headphones disconnected — interrupting');
        interrupt(source: VoiceReplyPlaybackInterruptSource.headphonesUnplugged);
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
    final startedAt = _now();
    final mode = SharedPreferencesUtil().voiceResponseMode;
    debugPrint('OmiVoicePlayback: beginResponse messageId=$messageId mode=$mode');
    if (mode == 0) {
      _emitSkip(
        mode: VoiceReplyPlaybackMode.off,
        skipReason: VoiceReplyPlaybackSkipReason.modeOff,
        outputRoute: VoiceReplyPlaybackOutputRoute.unknown,
      );
      return; // Off
    }

    await _ensureInitialized();

    final output = await _probeOutput();
    // Mode 1 (headphones only): skip if no private-listening output is
    // connected so Omi never blasts a private answer out of the phone
    // speaker in public. Mode 2 (always) bypasses this gate.
    if (mode == 1 && !output.headphonesConnected) {
      debugPrint('OmiVoicePlayback: no headphones — skipping playback (mode=headphones)');
      _emitSkip(
        mode: VoiceReplyPlaybackMode.headphonesOnly,
        skipReason: output.checkFailed
            ? VoiceReplyPlaybackSkipReason.headphoneCheckFailed
            : VoiceReplyPlaybackSkipReason.noHeadphones,
        outputRoute: output.route,
      );
      return;
    }

    if (_activeMessageId == messageId && isSpeaking) {
      // Same response actively in-flight; no-op (rapid-double-call guard).
      return;
    }

    if (_lifecycleOpen && _activeMessageId != null && _activeMessageId != messageId) {
      _lifecycleToken++;
      _emit(
        outcome: VoiceReplyPlaybackOutcome.interrupted,
        interruptSource: VoiceReplyPlaybackInterruptSource.newVoiceQuery,
      );
    }

    await _clearInFlightState();
    final continuing = _lifecycleOpen && _activeMessageId == messageId;
    _activeMessageId = messageId;
    _spoken = 0;
    if (!continuing) {
      _openLifecycle(startedAt: startedAt, mode: _modeFromInt(mode), route: output.route);
    }

    await _activateSession();
  }

  /// True if at least one "private-listening" output is connected — AirPods
  /// (Bluetooth A2DP/LE/SCO), wired 3.5mm / Lightning headphones, USB headset,
  /// or AirPlay. False for the built-in speaker / earpiece alone.
  Future<VoicePlaybackOutputSnapshot> _probeOutput() async {
    final probe = debugHooks?.probeOutput;
    if (probe != null) return probe();
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
      return VoicePlaybackOutputSnapshot(
        headphonesConnected: hit,
        checkFailed: false,
        route: _coarsenRoute(devices),
      );
    } catch (e) {
      debugPrint('OmiVoicePlayback: headphone check failed: $e — skipping playback');
      // Fail closed: if we can't tell whether headphones are connected,
      // we'd rather stay silent than blast audio from the speaker.
      return const VoicePlaybackOutputSnapshot(
        headphonesConnected: false,
        checkFailed: true,
        route: VoiceReplyPlaybackOutputRoute.unknown,
      );
    }
  }

  /// Called on every streamed text update. [fullText] is the cumulative AI
  /// response so far. [isFinal] means this is the last chunk.
  void updateStreamingResponse({required String messageId, required String fullText, required bool isFinal}) {
    if (SharedPreferencesUtil().voiceResponseMode == 0) return;
    if (_activeMessageId != messageId) {
      Logger.log(
        'OmiVoicePlayback: updateStreamingResponse skipped — activeId=$_activeMessageId != incoming=$messageId',
      );
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
    if (isFinal && _lifecycleOpen && _isIdle) {
      _emit(outcome: _naturalOutcome());
    }
  }

  /// Immediately cancel all synthesis + playback.
  Future<void> interrupt({
    VoiceReplyPlaybackInterruptSource source = VoiceReplyPlaybackInterruptSource.none,
  }) async {
    if (_lifecycleOpen) {
      _lifecycleToken++;
      _emit(outcome: VoiceReplyPlaybackOutcome.interrupted, interruptSource: source);
    }
    _activeMessageId = null;
    _spoken = 0;
    _synthesisQueue.clear();
    _audioQueue.clear();
    _synthesizing = false;
    _isPlayingQueue = false;
    _pausedByInterruption = false;
    await _stopPlayback();
    await _stopFallback();
    await _deactivateSession();
  }

  void _onInterruption(AudioInterruptionEvent event) {
    debugPrint(
      'OmiVoicePlayback: interruption begin=${event.begin} type=${event.type} '
      'activeId=$_activeMessageId isSpeaking=$isSpeaking pausedByInt=$_pausedByInterruption',
    );
    if (event.begin) {
      switch (event.type) {
        case AudioInterruptionType.duck:
          break;
        case AudioInterruptionType.pause:
          if (_player.playing) {
            _pausedByInterruption = true;
            _player.pause();
          }
          break;
        case AudioInterruptionType.unknown:
          interrupt(source: VoiceReplyPlaybackInterruptSource.audioInterruption);
          break;
      }
    } else {
      switch (event.type) {
        case AudioInterruptionType.duck:
          break;
        case AudioInterruptionType.pause:
          if (_pausedByInterruption) {
            _pausedByInterruption = false;
            _player.play();
          }
          break;
        case AudioInterruptionType.unknown:
          break;
      }
    }
  }

  // ---------------------------------------------------------------------------
  // Internals
  // ---------------------------------------------------------------------------

  Future<void> _clearInFlightState() async {
    _synthesisQueue.clear();
    _audioQueue.clear();
    _synthesizing = false;
    _isPlayingQueue = false;
    _pausedByInterruption = false;
    await _stopPlayback();
  }

  Future<void> _drainSynthesis() async {
    if (_synthesizing) return;
    if (_synthesisQueue.isEmpty) return;
    _synthesizing = true;

    while (_synthesisQueue.isNotEmpty) {
      if (SharedPreferencesUtil().voiceResponseMode == 0) {
        await interrupt(source: VoiceReplyPlaybackInterruptSource.modeOff);
        break;
      }
      final pending = _synthesisQueue.removeAt(0);
      debugPrint('OmiVoicePlayback: synthesizing "${pending.text}"');
      _chunksRequested++;
      final token = _lifecycleToken;
      try {
        final bytes = await _synthesize(pending.text);
        debugPrint('OmiVoicePlayback: got ${bytes?.length ?? 0} MP3 bytes');
        if (bytes != null && bytes.isNotEmpty) {
          _audioQueue.add(bytes);
          _tryStartPlayback();
        } else if (token == _lifecycleToken && _lifecycleOpen) {
          _chunksDropped++;
        }
      } on TtsUnavailableException catch (e) {
        Logger.log('TTS unavailable (${e.statusCode}) — falling back to system voice');
        if (token == _lifecycleToken && _lifecycleOpen) {
          _fallbackReason = _fallbackReasonFromStatus(e.statusCode);
        }
        // Fallback: speak the remaining sentence and any queued ones on-device.
        await _speakFallback(pending.text);
        for (final rest in _synthesisQueue) {
          await _speakFallback(rest.text);
        }
        _synthesisQueue.clear();
        break;
      } catch (e) {
        Logger.debug('synthesizeSpeech failed: $e');
        if (token == _lifecycleToken && _lifecycleOpen) _chunksDropped++;
        // Skip this sentence; keep the pipeline moving.
      }
    }

    _synthesizing = false;
    _maybeFinish();
  }

  Future<void> _speakFallback(String text) async {
    final token = _lifecycleToken;
    final startedAt = _now();
    try {
      if (debugHooks != null) {
        final speak = debugHooks!.speak;
        if (speak == null) {
          throw StateError('Voice playback test hooks are installed without a speak function');
        }
        await speak(text);
      } else {
        await _fallbackTts.speak(text);
      }
      if (token == _lifecycleToken && _lifecycleOpen) {
        _usedFallback = true;
        _noteFirstAudio(startedAt);
      }
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
      final token = _lifecycleToken;
      final startedAt = _now();
      await _playCloudChunk(bytes);
      if (token == _lifecycleToken && _lifecycleOpen) {
        _chunksPlayed++;
        _noteFirstAudio(startedAt);
      }
    } catch (e) {
      Logger.debug('just_audio play failed: $e');
      _isPlayingQueue = false;
      // Skip this chunk and try the next one.
      _playNextFromQueue();
    }
  }

  void _maybeFinish() {
    if (!_isIdle) return;
    // Small grace window so tail chunks from the SSE stream don't flap the
    // foreground service on/off rapidly.
    final token = _lifecycleToken;
    _delay(const Duration(milliseconds: 500)).then((_) async {
      if (token != _lifecycleToken || !_isIdle) return;
      await _deactivateSession();
      if (token != _lifecycleToken || !_lifecycleOpen || !_isIdle) return;
      _emit(outcome: _naturalOutcome());
    });
  }

  Future<void> _activateSession() async {
    if (_sessionActive) return;
    _sessionActive = true;
    if (debugHooks != null) return;
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
    if (debugHooks != null) return;
    try {
      final session = await AudioSession.instance;
      await session.setActive(false);
    } catch (_) {}
  }

  bool get _isIdle => _synthesisQueue.isEmpty && _audioQueue.isEmpty && !_isPlayingQueue && !_synthesizing;

  DateTime _now() => debugHooks?.now?.call() ?? DateTime.now();

  Future<void> _delay(Duration duration) {
    final delay = debugHooks?.delay;
    if (delay != null) return delay(duration);
    return Future<void>.delayed(duration);
  }

  VoiceReplyPlaybackMode _modeFromInt(int mode) => switch (mode) {
        0 => VoiceReplyPlaybackMode.off,
        1 => VoiceReplyPlaybackMode.headphonesOnly,
        2 => VoiceReplyPlaybackMode.always,
        _ => VoiceReplyPlaybackMode.unknown,
      };

  void _openLifecycle({
    required DateTime startedAt,
    required VoiceReplyPlaybackMode mode,
    required VoiceReplyPlaybackOutputRoute route,
  }) {
    _lifecycleToken++;
    _lifecycleOpen = true;
    _lifecycleStartedAt = startedAt;
    _lifecycleMode = mode;
    _lifecycleRoute = route;
    _chunksRequested = 0;
    _chunksPlayed = 0;
    _chunksDropped = 0;
    _usedFallback = false;
    _fallbackReason = VoiceReplyPlaybackFallbackReason.none;
    _firstAudioAt = null;
  }

  void _noteFirstAudio(DateTime startedAt) {
    _firstAudioAt ??= startedAt;
  }

  VoiceReplyPlaybackOutcome _naturalOutcome() {
    if (_chunksPlayed > 0 && _usedFallback) return VoiceReplyPlaybackOutcome.playedWithFallback;
    if (_chunksPlayed > 0) return VoiceReplyPlaybackOutcome.played;
    if (_usedFallback) return VoiceReplyPlaybackOutcome.fallbackOnly;
    return VoiceReplyPlaybackOutcome.failed;
  }

  VoiceReplyPlaybackFallbackReason _fallbackReasonFromStatus(int statusCode) => switch (statusCode) {
        429 => VoiceReplyPlaybackFallbackReason.rateLimited429,
        503 => VoiceReplyPlaybackFallbackReason.unavailable503,
        _ => VoiceReplyPlaybackFallbackReason.noResponse,
      };

  void _emitSkip({
    required VoiceReplyPlaybackMode mode,
    required VoiceReplyPlaybackSkipReason skipReason,
    required VoiceReplyPlaybackOutputRoute outputRoute,
  }) {
    AnalyticsManager().voiceReplyPlayback(
      outcome: VoiceReplyPlaybackOutcome.skipped,
      skipReason: skipReason,
      mode: mode,
      outputRoute: outputRoute,
      chunksRequested: 0,
      chunksPlayed: 0,
      chunksDropped: 0,
      fallbackReason: VoiceReplyPlaybackFallbackReason.none,
      firstAudioLatencyMs: _noAudioLatencyMs,
      interruptSource: VoiceReplyPlaybackInterruptSource.none,
    );
  }

  void _emit({
    required VoiceReplyPlaybackOutcome outcome,
    VoiceReplyPlaybackSkipReason skipReason = VoiceReplyPlaybackSkipReason.none,
    VoiceReplyPlaybackInterruptSource interruptSource = VoiceReplyPlaybackInterruptSource.none,
  }) {
    if (!_lifecycleOpen) return;
    _lifecycleOpen = false;
    final latency = _lifecycleStartedAt != null && _firstAudioAt != null
        ? _firstAudioAt!.difference(_lifecycleStartedAt!).inMilliseconds
        : _noAudioLatencyMs;
    AnalyticsManager().voiceReplyPlayback(
      outcome: outcome,
      skipReason: skipReason,
      mode: _lifecycleMode,
      outputRoute: _lifecycleRoute,
      chunksRequested: _chunksRequested,
      chunksPlayed: _chunksPlayed,
      chunksDropped: _chunksDropped,
      fallbackReason: _fallbackReason,
      firstAudioLatencyMs: latency < 0 ? _noAudioLatencyMs : latency,
      interruptSource: interruptSource,
    );
  }

  Future<Uint8List?> _synthesize(String text) {
    if (debugHooks != null) {
      final synthesize = debugHooks!.synthesize;
      if (synthesize == null) {
        throw StateError('Voice playback test hooks are installed without a synthesize function');
      }
      return synthesize(text: text);
    }
    return synthesizeSpeech(text: text);
  }

  Future<void> _playCloudChunk(Uint8List bytes) async {
    if (debugHooks != null) {
      final play = debugHooks!.play;
      if (play == null) {
        throw StateError('Voice playback test hooks are installed without a play function');
      }
      await play(bytes);
      return;
    }
    await _player.setAudioSource(_BytesAudioSource(bytes));
    await _player.play();
  }

  Future<void> _stopPlayback() async {
    if (debugHooks != null) {
      final stop = debugHooks!.stopPlayback;
      if (stop != null) {
        try {
          await stop();
        } catch (_) {}
      }
      return;
    }
    try {
      await _player.stop();
    } catch (_) {}
  }

  Future<void> _stopFallback() async {
    if (debugHooks != null) {
      final stop = debugHooks!.stopSpeak;
      if (stop != null) {
        try {
          await stop();
        } catch (_) {}
      }
      return;
    }
    try {
      await _fallbackTts.stop();
    } catch (_) {}
  }

  VoiceReplyPlaybackOutputRoute _coarsenRoute(Iterable<AudioDevice> devices) {
    var best = VoiceReplyPlaybackOutputRoute.unknown;
    var bestRank = _routeRank(VoiceReplyPlaybackOutputRoute.unknown);
    for (final device in devices) {
      final route = _routeForType(device.type);
      final rank = _routeRank(route);
      if (rank < bestRank) {
        best = route;
        bestRank = rank;
      }
    }
    return best;
  }

  int _routeRank(VoiceReplyPlaybackOutputRoute route) => switch (route) {
        VoiceReplyPlaybackOutputRoute.bluetooth => 0,
        VoiceReplyPlaybackOutputRoute.wired => 1,
        VoiceReplyPlaybackOutputRoute.airplay => 2,
        VoiceReplyPlaybackOutputRoute.usb => 3,
        VoiceReplyPlaybackOutputRoute.speaker => 4,
        VoiceReplyPlaybackOutputRoute.unknown => 5,
      };

  // ignore: experimental_member_use
  VoiceReplyPlaybackOutputRoute _routeForType(AudioDeviceType type) {
    switch (type.name) {
      case 'bluetoothA2dp':
      case 'bluetoothLe':
      case 'bluetoothSco':
        return VoiceReplyPlaybackOutputRoute.bluetooth;
      case 'wiredHeadphones':
      case 'wiredHeadset':
      case 'lineAnalog':
      case 'lineDigital':
        return VoiceReplyPlaybackOutputRoute.wired;
      case 'airPlay':
        return VoiceReplyPlaybackOutputRoute.airplay;
      case 'usbAudio':
        return VoiceReplyPlaybackOutputRoute.usb;
      case 'builtInSpeaker':
      case 'builtInEarpiece':
        return VoiceReplyPlaybackOutputRoute.speaker;
      default:
        return VoiceReplyPlaybackOutputRoute.unknown;
    }
  }

  @visibleForTesting
  void debugNotifyPlaybackCompleted() {
    _playNextFromQueue();
  }

  @visibleForTesting
  void debugReset() {
    debugHooks = null;
    _initialized = false;
    _activeMessageId = null;
    _spoken = 0;
    _synthesisQueue.clear();
    _audioQueue.clear();
    _synthesizing = false;
    _isPlayingQueue = false;
    _sessionActive = false;
    _pausedByInterruption = false;
    _lifecycleOpen = false;
    _lifecycleToken++;
    _lifecycleStartedAt = null;
    _lifecycleMode = VoiceReplyPlaybackMode.off;
    _lifecycleRoute = VoiceReplyPlaybackOutputRoute.unknown;
    _chunksRequested = 0;
    _chunksPlayed = 0;
    _chunksDropped = 0;
    _usedFallback = false;
    _fallbackReason = VoiceReplyPlaybackFallbackReason.none;
    _firstAudioAt = null;
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
  int? _nextChunkBoundary(String text, {required int start, required bool isFirstChunk, required bool isFinal}) {
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
