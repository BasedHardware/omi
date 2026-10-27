import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

import 'package:omi/services/live_preview/live_preview_controller.dart';
import 'package:omi/services/live_preview/live_preview_telemetry.dart';

/// The outcome of one on-device notes attempt, as telemetry reports it (no text).
enum LivePreviewNotesResult { ok, unavailable, error, droppedBusy }

/// The throttled, bounded policy for drafting on-device live notes.
abstract final class LivePreviewNotesPolicy {
  /// Re-summarize at most this often.
  static const minRunInterval = Duration(seconds: 60);

  /// …and only after at least this many new preview words.
  static const minNewWords = 40;

  /// AFM's context budget is prompt plus completion: cap the prompt to the
  /// newest slice of the preview.
  static const maxInputWords = 1500;

  /// The bounded shape, shared with the native schema: at most 4 bullets of at
  /// most 12 words each.
  static const maxBullets = 4;
  static const maxBulletWords = 12;

  static int wordCount(String text) => text.split(RegExp(r'\s+')).where((word) => word.isNotEmpty).length;

  /// The newest [maxInputWords] words of [lines], in order, newest last.
  static String inputText(List<LivePreviewLine> lines) {
    final words = <String>[];
    for (final line in lines.reversed) {
      final text = line.text.trim();
      if (text.isEmpty) continue;
      final lineWords = text.split(RegExp(r'\s+')).where((word) => word.isNotEmpty).toList();
      final remaining = LivePreviewNotesPolicy.maxInputWords - words.length;
      if (lineWords.length >= remaining) {
        words.insertAll(0, lineWords.sublist(lineWords.length - remaining));
        break;
      }
      words.insertAll(0, lineWords);
    }
    return words.join(' ');
  }

  /// Belt to the native schema's bounds: at most [maxBullets] bullets of at
  /// most [maxBulletWords] words each, no empties.
  static List<String> clamp(List<String> bullets) => [
        for (final bullet in bullets.take(maxBullets))
          bullet.trim().split(RegExp(r'\s+')).where((word) => word.isNotEmpty).take(maxBulletWords).join(' '),
      ].where((bullet) => bullet.isNotEmpty).toList();
}

/// One notes engine invocation. Returns the drafted bullets, or null when the
/// engine is unavailable on this device (older OS, Apple Intelligence off, or a
/// platform that ships no engine in this release). Throws on engine errors.
typedef LivePreviewNotesEngine = Future<List<String>?> Function(String text, String language);

/// The engine for platforms with no on-device notes model in this release.
Future<List<String>?> noLivePreviewNotesEngine(String text, String language) async => null;

/// Apple Foundation Models (iOS 26+) over `com.omi/live_preview_notes`. The
/// text crosses to native and back and goes nowhere else; native never logs it.
/// Returns null when AFM is unavailable (older iOS, Apple Intelligence off).
Future<List<String>?> methodChannelLivePreviewNotes(String text, String language) async {
  const channel = MethodChannel('com.omi/live_preview_notes');
  try {
    final reply = await channel.invokeMethod<Object>('summarize', {'text': text, 'language': language});
    final bullets = ((reply as Map<Object?, Object?>?)?['bullets'] as List<Object?>?) ?? const [];
    return [for (final bullet in bullets) bullet as String];
  } on PlatformException catch (error) {
    if (error.code == 'UNAVAILABLE') return null;
    rethrow;
  }
}

/// The on-device notes of one live preview session: [LivePreviewController.notes].
///
/// Listens to the preview, drafts bullets on the throttled cadence and clears
/// with it (capture stop, account change and the controller's own
/// conversation-gap clear all empty the preview lines, which resets this).
/// The preview and the notes never leave the phone and are never logged.
class LivePreviewNotes extends ChangeNotifier {
  LivePreviewNotes({
    required this.engine,
    required LivePreviewTelemetry telemetry,
    required this.platform,
    DateTime Function()? now,
  })  : _telemetry = telemetry,
        _now = now ?? DateTime.now;

  final LivePreviewNotesEngine engine;
  final LivePreviewTelemetry _telemetry;
  final LivePreviewPlatform platform;
  final DateTime Function() _now;

  /// The wire name telemetry reports for this engine.
  String get engineName => platform == LivePreviewPlatform.ios ? 'apple_foundation_models' : 'none';

  List<String> _bullets = [];
  List<String> get bullets => _bullets;

  LivePreviewController? _preview;
  Timer? _cadence;
  DateTime? _lastRunAt;
  int _wordsAtLastRun = 0;
  int _generation = 0;
  int? _previewGeneration;
  bool _running = false;
  bool _busyReported = false;
  bool _disposed = false;

  void attach(LivePreviewController preview) {
    if (_preview != null) return;
    _preview = preview;
    _previewGeneration = preview.sessionGeneration;
    preview.addListener(_onPreviewChanged);
  }

  /// The once-a-minute re-check runs only while there are preview lines: a
  /// session with nothing to draft never wakes the cadence.
  void _startCadence() {
    _cadence ??= Timer.periodic(LivePreviewNotesPolicy.minRunInterval, (_) {
      final current = _preview;
      if (current != null && current.lines.isNotEmpty) _consider(current);
    });
  }

  void _stopCadence() {
    _cadence?.cancel();
    _cadence = null;
  }

  void detach() {
    _preview?.removeListener(_onPreviewChanged);
    _preview = null;
    _stopCadence();
    _reset();
  }

  void _onPreviewChanged() {
    final preview = _preview;
    if (preview == null) return;
    if (_previewGeneration != preview.sessionGeneration) {
      _previewGeneration = preview.sessionGeneration;
      _reset();
    }
    if (preview.lines.isEmpty) {
      _stopCadence();
      _reset();
      return;
    }
    _startCadence();
    _consider(preview);
  }

  void _reset() {
    _generation++;
    if (_bullets.isEmpty && _lastRunAt == null && _wordsAtLastRun == 0) return;
    _bullets = [];
    _lastRunAt = null;
    _wordsAtLastRun = 0;
    notifyListeners();
  }

  void _consider(LivePreviewController preview) {
    if (_disposed) return;
    final now = _now();
    final last = _lastRunAt;
    if (last != null && now.difference(last) < LivePreviewNotesPolicy.minRunInterval) return;
    final words = preview.totalWordsSeen;
    if (words - _wordsAtLastRun < LivePreviewNotesPolicy.minNewWords) return;
    if (_running) {
      // Drop the run; one report per busy stretch says so.
      if (!_busyReported) {
        _busyReported = true;
        _telemetry.notesRun(
            engine: engineName, outcome: LivePreviewNotesResult.droppedBusy, latencyMs: 0, bulletCount: 0);
      }
      return;
    }
    _run(preview, words, now);
  }

  Future<void> _run(LivePreviewController preview, int words, DateTime at) async {
    final generation = _generation;
    _running = true;
    _lastRunAt = at;
    final input = LivePreviewNotesPolicy.inputText(preview.lines);
    final started = _now();
    try {
      final drafted = await engine(input, preview.language);
      if (_disposed || generation != _generation || _preview != preview || preview.lines.isEmpty) return;
      _wordsAtLastRun = words;
      final bullets = LivePreviewNotesPolicy.clamp(drafted ?? const <String>[]);
      // Unavailable drafts nothing: the quiet line replaces the bullets.
      _bullets = bullets;
      _telemetry.notesRun(
        engine: engineName,
        outcome: drafted == null ? LivePreviewNotesResult.unavailable : LivePreviewNotesResult.ok,
        latencyMs: _now().difference(started).inMilliseconds,
        bulletCount: bullets.length,
      );
      notifyListeners();
    } catch (_) {
      if (_disposed || generation != _generation || _preview != preview) return;
      _wordsAtLastRun = words;
      // An error hides the bullets too: the quiet line, no cloud fallback.
      _bullets = [];
      _telemetry.notesRun(
        engine: engineName,
        outcome: LivePreviewNotesResult.error,
        latencyMs: _now().difference(started).inMilliseconds,
        bulletCount: 0,
      );
      notifyListeners();
    } finally {
      _running = false;
      _busyReported = false;
    }
  }

  @override
  void dispose() {
    _disposed = true;
    detach();
    super.dispose();
  }
}
