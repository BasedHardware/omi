import 'dart:convert';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/http/api_fallback.dart';
import 'package:omi/backend/schema/chat_session.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/env/env.dart';

/// Uses the existing session endpoints. Errors stay distinct from an empty history.
class ChatSessionsApi {
  ChatSessionsApi({this.send, String? baseUrl, this.fallback = recordFallback}) : _baseUrl = baseUrl;
  final void Function(ApiFallbackEvent) fallback;
  final ApiSend? send;
  final String? _baseUrl;

  String _url(String path, [Map<String, String> query = const {}]) =>
      Uri.parse('${_baseUrl ?? Env.apiBaseUrl}$path').replace(queryParameters: query.isEmpty ? null : query).toString();

  /// Decode rows independently so one malformed record does not hide valid history.
  /// Rejected rows stay observable to consumers and count toward the server offset.
  Future<ApiResult<List<T>>> _rows<T>(
      String path, Map<String, String> query, T Function(Map<String, dynamic>) decode) async {
    final response = await executeApi<String>(
      request: ApiRequest(url: _url(path, query), method: 'GET'),
      send: send,
      decode: (body) => body,
    );
    return switch (response) {
      ApiFailure(:final problem) => ApiFailure(problem),
      ApiSuccess(:final data, :final truncated) => switch (decodeApiRows(data, decode, fallback: fallback)) {
          ApiSuccess(:final data, :final rejectedRows) =>
            ApiSuccess(data, rejectedRows: rejectedRows, truncated: truncated),
          ApiFailure(:final problem) => ApiFailure(problem),
        },
    };
  }

  /// The backend orders default Omi sessions newest first. App conversations stay separate.
  Future<ApiResult<List<ChatSessionSummary>>> list({int offset = 0, int limit = 50}) =>
      _rows('v2/chat-sessions', {'offset': '$offset', 'limit': '$limit'}, ChatSessionSummary.fromJson);

  /// Returns only a validated server identity; callers must not send when this fails.
  Future<ApiResult<ChatSessionSummary>> create() => executeApi(
        request: ApiRequest(url: _url('v2/chat-sessions'), method: 'POST', body: '{}'),
        send: send,
        decode: (body) {
          final row = jsonDecode(body);
          if (row is! Map<String, dynamic>) throw const FormatException('Invalid new chat');
          return ChatSessionSummary.fromJson(row);
        },
      );

  Future<ApiResult<void>> delete(String id) => executeApi<void>(
        request: ApiRequest(url: _url('v2/chat-sessions/${Uri.encodeComponent(id)}'), method: 'DELETE'),
        send: send,
        decode: (_) {},
      );

  /// Reads the explicit session even when it is not the server-current conversation.
  Future<ApiResult<List<ServerMessage>>> messages(String id, {int offset = 0, int limit = 100}) => _rows('v2/messages',
      {'chat_session_id': id, 'offset': '$offset', 'limit': '$limit'}, ServerMessage.fromGeneratedWireJson);

  Future<ApiResult<String>> title(String id, List<ServerMessage> messages) => executeApi(
        request: ApiRequest(
          url: _url('v2/chat/generate-title'),
          method: 'POST',
          body: jsonEncode({
            'session_id': id,
            'messages': [
              for (final m in messages.where((m) => m.text.trim().isNotEmpty).take(10))
                {'text': m.text, 'sender': m.sender == MessageSender.ai ? 'ai' : 'human'},
            ]
          }),
        ),
        send: send,
        decode: (body) {
          final data = jsonDecode(body);
          if (data is! Map || data['title'] is! String) throw const FormatException('Invalid chat title');
          return data['title'] as String;
        },
      );
}
