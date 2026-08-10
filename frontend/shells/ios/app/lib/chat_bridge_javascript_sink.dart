import 'dart:async';
import 'dart:convert';

import 'gen/bridge_http_contract.g.dart';

typedef JavaScriptRunner = Future<void> Function(String source);

class ChatBridgeJavaScriptSink {
  ChatBridgeJavaScriptSink(
    this._runJavaScript, {
    bool documentInitiallyActive = true,
  }) : _activation = Completer<void>() {
    if (documentInitiallyActive) _activation.complete();
  }

  final JavaScriptRunner _runJavaScript;
  static const String _generationSlot = '__omiNativeChatDocumentGeneration';
  int _generation = 0;
  bool _closed = false;
  Completer<void> _activation;

  int get generation => _generation;

  void resetForNavigation() {
    if (_closed) return;
    if (!_activation.isCompleted) _activation.complete();
    _generation += 1;
    _activation = Completer<void>();
  }

  Future<void> activateDocument() async {
    if (_closed) return;
    final generation = _generation;
    await _runJavaScript('globalThis.$_generationSlot=$generation;');
    if (_closed || generation != _generation) return;
    if (!_activation.isCompleted) _activation.complete();
  }

  void close() {
    if (_closed) return;
    _closed = true;
    _generation += 1;
    if (!_activation.isCompleted) _activation.complete();
  }

  Future<void> streamFrame(
    Map<String, Object> frame, {
    required int generation,
  }) {
    final raw = jsonEncode(frame);
    return _dispatch(
      '${BridgeStreamContract.sinkFunction}(${jsonEncode(raw)});',
      generation,
    );
  }

  Future<void> stagingReply(
    String id,
    Map<String, Object> reply, {
    required int generation,
  }) {
    final raw = jsonEncode(reply);
    return _dispatch(
      '${ChatAttachmentStagingContract.replyFunction}(${jsonEncode(id)},${jsonEncode(raw)});',
      generation,
    );
  }

  Future<void> _dispatch(String source, int generation) async {
    if (_closed || generation != _generation) return;
    final activation = _activation;
    await activation.future;
    if (_closed ||
        generation != _generation ||
        !identical(activation, _activation)) {
      return;
    }
    await _runJavaScript(
      'if(globalThis.$_generationSlot===$generation){$source}',
    );
  }
}
