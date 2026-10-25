import 'dart:async';
import 'dart:typed_data';

import 'package:omi/services/live_preview/live_preview_engine.dart';

/// Scripted on-device preview engine: no platform channel, no audio leaves.
class FakeLivePreviewEngine implements LivePreviewEngine {
  LivePreviewStart nextStart = const LivePreviewStart(LivePreviewEngineKind.speechTranscriber, LivePreviewReason.ok);
  Completer<LivePreviewStart>? startGate;
  Future<bool> Function()? feedResult;
  final List<String> startedLanguages = [];
  final List<Set<LivePreviewEngineKind>> startExclusions = [];

  /// Starts after the first, in order; falls back to [nextStart] when empty.
  final List<LivePreviewStart> laterStarts = [];
  final List<Uint8List> fed = [];
  int stops = 0;
  final StreamController<LivePreviewResult> _results = StreamController.broadcast(sync: true);

  @override
  Stream<LivePreviewResult> get results => _results.stream;

  void emit(String id, String text, bool isFinal) =>
      _results.add(LivePreviewResult(segmentId: id, text: text, isFinal: isFinal));

  /// The running engine dies (what the native side reports as `failure`).
  void fail(LivePreviewEngineKind engine) => _results.addError(LivePreviewRuntimeFailure(engine));

  @override
  Future<LivePreviewStart> start(String language, {Set<LivePreviewEngineKind> exclude = const {}}) async {
    startedLanguages.add(language);
    startExclusions.add(exclude);
    final gate = startGate;
    if (gate != null) return gate.future;
    if (startedLanguages.length > 1 && laterStarts.isNotEmpty) return laterStarts.removeAt(0);
    return nextStart;
  }

  @override
  Future<bool> feedPcm16(Uint8List pcm) {
    fed.add(pcm);
    return feedResult?.call() ?? Future.value(true);
  }

  @override
  Future<void> stop() async => stops++;
}
