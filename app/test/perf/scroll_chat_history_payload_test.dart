import 'dart:convert';
import 'dart:isolate';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:omi/backend/http/api/chat_sessions.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/utils/off_ui_isolate.dart';

// Rejects (so decodeApiRows counts the row as bad) when it runs on the UI isolate.
ServerMessage _rowOffUiOnly(Map<String, dynamic> json) {
  if (Isolate.current.debugName != 'chat_session_parse') throw StateError('session history decoded on the UI isolate');
  return ServerMessage.fromGeneratedWireJson(json);
}

void main() {
  test('explicit-session history above the threshold decodes off the UI isolate', () async {
    final previous = chatSessionMessageRowDecoder;
    addTearDown(() => chatSessionMessageRowDecoder = previous);
    chatSessionMessageRowDecoder = _rowOffUiOnly;
    offUiIsolateFallbacks = 0;
    final text = List.filled(
      12,
      '**Project update**\n\n- Review the plan and send feedback.\n- Follow up tomorrow.',
    ).join('\n\n');
    final body = jsonEncode([
      for (var i = 0; i < 100; i++)
        ServerMessage(
                'm$i', DateTime.utc(2026, 10, 23), text, MessageSender.ai, MessageType.text, null, false, [], [], [])
            .toJson(),
    ]);
    final api = ChatSessionsApi(
      baseUrl: 'http://127.0.0.1:1/',
      send: (_) async => http.Response(body, 200),
    );
    final result = await api.messages('synthetic-session') as ApiSuccess<List<ServerMessage>>;
    final bytes = utf8.encode(body).length;
    // ignore: avoid_print
    print('SCROLL_ACTIVE_CHAT_HISTORY bytes=$bytes rows=${result.data.length}');
    expect(bytes, greaterThan(64 * 1024));
    expect(result.data.map((m) => m.id), [for (var i = 0; i < 100; i++) 'm$i']);
    expect(result.data.first.text, text);
    expect(result.rejectedRows, 0);
    expect(offUiIsolateFallbacks, 0);
  });
}
