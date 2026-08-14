import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi_webview_proto/chat_bridge_javascript_sink.dart';

class _DelayedDocumentRunner {
  int? documentGeneration;
  bool holdFrames = false;
  final List<String> executed = <String>[];
  final List<({String source, Completer<void> release})> pending = <({String source, Completer<void> release})>[];

  Future<void> call(String source) async {
    final assignment = RegExp(r'__omiNativeChatDocumentGeneration=(\d+);').firstMatch(source);
    if (assignment != null) {
      documentGeneration = int.parse(assignment.group(1)!);
      return;
    }
    if (!holdFrames) {
      _execute(source);
      return;
    }
    final release = Completer<void>();
    pending.add((source: source, release: release));
    await release.future;
    _execute(source);
  }

  void replaceDocument() => documentGeneration = null;

  void releaseAll() {
    for (final item in pending.toList(growable: false)) {
      if (!item.release.isCompleted) item.release.complete();
    }
    pending.clear();
  }

  void _execute(String source) {
    final guard = RegExp(r'__omiNativeChatDocumentGeneration===(\d+)').firstMatch(source);
    if (guard == null || int.parse(guard.group(1)!) == documentGeneration) {
      executed.add(source);
    }
  }
}

void main() {
  test('pending stream frame cannot execute after reset and reused s1', () async {
    // red-proof: remove the execution-time generation guard; releasing the old
    // Future records two s1 frames in the replacement document.
    final runner = _DelayedDocumentRunner();
    final sink = ChatBridgeJavaScriptSink(runner.call, documentInitiallyActive: false);
    await sink.activateDocument();
    final oldGeneration = sink.generation;
    runner.holdFrames = true;
    final old = sink.streamFrame(const <String, Object>{
      't': 'data',
      'id': 's1',
      'channel': 'chat-generation-events',
      'payload': 'old',
    }, generation: oldGeneration);
    await Future<void>.delayed(Duration.zero);
    expect(runner.pending, hasLength(1));

    sink.resetForNavigation();
    runner.replaceDocument();
    await sink.activateDocument();
    runner.releaseAll();
    await old;
    expect(runner.executed, isEmpty);

    runner.holdFrames = false;
    await sink.streamFrame(const <String, Object>{
      't': 'data',
      'id': 's1',
      'channel': 'chat-generation-events',
      'payload': 'new',
    }, generation: sink.generation);
    expect(runner.executed, hasLength(1));
    expect(runner.executed.single, contains('new'));
  });

  test('pending staging reply cannot execute after close and reused a1', () async {
    final runner = _DelayedDocumentRunner();
    final sink = ChatBridgeJavaScriptSink(runner.call, documentInitiallyActive: false);
    await sink.activateDocument();
    runner.holdFrames = true;
    final pending = sink.stagingReply('a1', const <String, Object>{
      'ok': false,
      'id': 'a1',
      'reason': 'cancelled',
    }, generation: sink.generation);
    await Future<void>.delayed(Duration.zero);
    expect(runner.pending, hasLength(1));

    sink.close();
    runner.replaceDocument();
    runner.releaseAll();
    await pending;
    expect(runner.executed, isEmpty);
  });
}
