import 'dart:convert';

import 'gen/bridge_http_contract.g.dart';

typedef JavaScriptRunner = Future<void> Function(String source);

class ChatBridgeJavaScriptSink {
  const ChatBridgeJavaScriptSink(this._runJavaScript);

  final JavaScriptRunner _runJavaScript;

  Future<void> streamFrame(Map<String, Object> frame) {
    final raw = jsonEncode(frame);
    return _runJavaScript(
      '${BridgeStreamContract.sinkFunction}(${jsonEncode(raw)});',
    );
  }

  Future<void> stagingReply(String id, Map<String, Object> reply) {
    final raw = jsonEncode(reply);
    return _runJavaScript(
      '${ChatAttachmentStagingContract.replyFunction}(${jsonEncode(id)},${jsonEncode(raw)});',
    );
  }
}
