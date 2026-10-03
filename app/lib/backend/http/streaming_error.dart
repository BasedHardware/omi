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
  if (error is SocketException || error is HandshakeException || error is http.ClientException) {
    return const ChatStreamException(ChatStreamFailureClass.offline);
  }
  return const ChatStreamException(ChatStreamFailureClass.unknown);
}
