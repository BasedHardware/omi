import 'dart:async';
import 'dart:io';

import 'package:http/http.dart' as http;

enum ChatStreamFailureClass {
  offline,
  server,
  timeout,
  quota,
  notSignedIn,
  unknown,
}

class ChatStreamException implements Exception {
  const ChatStreamException(this.kind, {this.statusCode});

  final ChatStreamFailureClass kind;
  final int? statusCode;

  @override
  String toString() => 'ChatStreamException($kind, statusCode: $statusCode)';
}

ChatStreamException classifyChatStreamFailure(Object error) {
  if (error is ChatStreamException) return error;
  if (error is TimeoutException) return const ChatStreamException(ChatStreamFailureClass.timeout);
  if (error is SocketException || error is HandshakeException) {
    return const ChatStreamException(ChatStreamFailureClass.offline);
  }
  // Mirror isTransientNetworkError (shared.dart) for the generic path: only
  // connectivity-looking http.ClientExceptions are offline; other client
  // exceptions (aborted or malformed requests) stay `unknown` instead of
  // masquerading as connectivity failures the user cannot fix. The
  // ClientException message is the only signal available here.
  if (error is http.ClientException) {
    final text = error.message.toLowerCase();
    final transient = text.contains('connection closed') ||
        text.contains('connection reset') ||
        text.contains('failed host lookup') ||
        text.contains('network is unreachable') ||
        text.contains('bad file descriptor') ||
        text.contains('software caused connection abort');
    if (transient) return const ChatStreamException(ChatStreamFailureClass.offline);
  }
  return const ChatStreamException(ChatStreamFailureClass.unknown);
}
