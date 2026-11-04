import 'dart:async';
import 'dart:typed_data';

import 'package:omi/services/live_preview/live_preview_engine.dart';
import 'package:omi/utils/audio/wav_bytes.dart';

/// Transcribes one canonical 16 kHz mono PCM16 WAV; null/empty when nothing
/// usable was heard.
typedef WhisperWindowTranscriber = Future<String?> Function(Uint8List wav, String language);

/// Omi's downloaded Whisper model as a windowed pseudo-stream: PCM collects in
/// a bounded rolling buffer and each full window is transcribed once, one at a
/// time, as a settled line. Display only; the audio is a preview copy.
///
/// A window boundary can split a word, and Whisper runs on the phone's CPU, so
/// this is the fallback after the OS on-device recognizer.
class WhisperWindowPreviewEngine implements LivePreviewEngine {
  WhisperWindowPreviewEngine({
    required this.transcribe,
    this.windowBytes = 4 * 32000,
    this.maxBufferedBytes = 30 * 32000,
    DateTime Function()? now,
  }) : _now = now ?? DateTime.now;

  final WhisperWindowTranscriber transcribe;
  final DateTime Function() _now;
  DateTime? _audioOrigin;
  int _bufferOffset = 0;

  /// Four seconds of 16 kHz PCM16 per transcription.
  final int windowBytes;

  /// The rolling buffer never holds more than this; older audio is dropped
  /// while a slow transcription is running.
  final int maxBufferedBytes;

  final StreamController<LivePreviewResult> _results = StreamController.broadcast();
  final BytesBuilder _buffer = BytesBuilder(copy: false);
  String _language = 'multi';
  bool _running = false;
  bool _busy = false;
  int _window = 0;
  int _generation = 0;

  @override
  Stream<LivePreviewResult> get results => _results.stream;

  @override
  Future<LivePreviewStart> start(String language, {Set<LivePreviewEngineKind> exclude = const {}}) async {
    if (exclude.contains(LivePreviewEngineKind.whisper)) {
      return const LivePreviewStart(LivePreviewEngineKind.none, LivePreviewReason.engineError, bundledInstalled: true);
    }
    _language = language;
    _running = true;
    _generation++;
    _buffer.clear();
    _audioOrigin = null;
    _bufferOffset = 0;
    return const LivePreviewStart(LivePreviewEngineKind.whisper, LivePreviewReason.ok, bundledInstalled: true);
  }

  @override
  Future<bool> feedPcm16(Uint8List pcm, {DateTime? startedAt}) async {
    if (!_running) return false;
    var accepted = true;
    if (_buffer.isEmpty) {
      _audioOrigin = startedAt ?? _now().subtract(Duration(microseconds: pcm.length * 1000000 ~/ 32000));
      _bufferOffset = 0;
    }
    _buffer.add(pcm);
    if (_buffer.length > maxBufferedBytes) {
      final kept = _buffer.takeBytes();
      _bufferOffset += kept.length - maxBufferedBytes;
      _buffer.add(Uint8List.sublistView(kept, kept.length - maxBufferedBytes));
      accepted = false;
    }
    _pump();
    return accepted;
  }

  void _pump() {
    if (_busy || !_running || _buffer.length < windowBytes) return;
    final all = _buffer.takeBytes();
    final window = Uint8List.sublistView(all, 0, windowBytes);
    if (all.length > windowBytes) _buffer.add(Uint8List.sublistView(all, windowBytes));
    final generation = _generation;
    final startedAt = _audioOrigin?.add(Duration(microseconds: _bufferOffset * 1000000 ~/ 32000));
    final endedAt = startedAt?.add(Duration(microseconds: windowBytes * 1000000 ~/ 32000));
    _bufferOffset += windowBytes;
    final id = 'w${_window++}';
    _busy = true;
    unawaited(() async {
      try {
        final text = await transcribe(WavBytes.fromPcm(window, sampleRate: 16000, numChannels: 1).asBytes(), _language);
        final trimmed = text?.trim() ?? '';
        if (generation == _generation && _running && trimmed.isNotEmpty && !_results.isClosed) {
          _results.add(
              LivePreviewResult(segmentId: id, text: trimmed, isFinal: true, startedAt: startedAt, endedAt: endedAt));
        }
      } catch (_) {
        // The model failed to run: the engine is dead for this session.
        if (generation == _generation && _running && !_results.isClosed) {
          _results.addError(const LivePreviewRuntimeFailure(LivePreviewEngineKind.whisper));
        }
      } finally {
        _busy = false;
        if (generation == _generation) _pump();
      }
    }());
  }

  @override
  Future<void> stop() async {
    _running = false;
    _generation++;
    _buffer.clear();
  }
}

/// The OS engine first; if it has none, Omi's downloaded model when present;
/// otherwise none with the OS engine's reason. Never a cloud recognizer.
class FallbackLivePreviewEngine implements LivePreviewEngine {
  FallbackLivePreviewEngine({required this.primary, required this.fallback});

  final LivePreviewEngine primary;

  /// Null when the downloadable model is not on this phone.
  final Future<LivePreviewEngine?> Function() fallback;

  final StreamController<LivePreviewResult> _results = StreamController.broadcast();
  LivePreviewEngine? _active;
  StreamSubscription<LivePreviewResult>? _forward;

  @override
  Stream<LivePreviewResult> get results => _results.stream;

  @override
  Future<LivePreviewStart> start(String language, {Set<LivePreviewEngineKind> exclude = const {}}) async {
    await _detach();
    final native = await primary.start(language, exclude: exclude);
    if (native.running) return _attach(primary, native);
    LivePreviewEngine? bundled;
    try {
      bundled = exclude.contains(LivePreviewEngineKind.whisper) ? null : await fallback();
    } catch (_) {
      bundled = null;
    }
    if (bundled == null) return LivePreviewStart(LivePreviewEngineKind.none, native.reason);
    final started = await bundled.start(language, exclude: exclude);
    if (!started.running) return LivePreviewStart(LivePreviewEngineKind.none, native.reason, bundledInstalled: true);
    return _attach(bundled, started);
  }

  LivePreviewStart _attach(LivePreviewEngine engine, LivePreviewStart start) {
    _active = engine;
    _forward = engine.results.listen(_results.add, onError: _results.addError);
    return start;
  }

  Future<void> _detach() async {
    final active = _active;
    _active = null;
    await _forward?.cancel();
    _forward = null;
    if (active != null) await active.stop();
  }

  @override
  Future<bool> feedPcm16(Uint8List pcm, {DateTime? startedAt}) =>
      _active?.feedPcm16(pcm, startedAt: startedAt) ?? Future.value(false);

  @override
  Future<void> stop() => _detach();
}
