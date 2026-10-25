import 'dart:async';
import 'dart:typed_data';

import 'package:omi/services/live_preview/live_preview_engine.dart';

/// Scripted on-device preview engine: no platform channel, no audio leaves.
class FakeLivePreviewEngine implements LivePreviewEngine {
  LivePreviewStart nextStart = const LivePreviewStart(LivePreviewEngineKind.speechTranscriber, LivePreviewReason.ok);
  Completer<LivePreviewStart>? startGate;
  Future<bool> Function()? feedResult;
  final List<String> startedLanguages = [];
  final List<Uint8List> fed = [];
  int stops = 0;
  final StreamController<LivePreviewResult> _results = StreamController.broadcast(sync: true);

  @override
  Stream<LivePreviewResult> get results => _results.stream;

  void emit(String id, String text, bool isFinal) =>
      _results.add(LivePreviewResult(segmentId: id, text: text, isFinal: isFinal));

  @override
  Future<LivePreviewStart> start(String language) async {
    startedLanguages.add(language);
    final gate = startGate;
    if (gate != null) return gate.future;
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
