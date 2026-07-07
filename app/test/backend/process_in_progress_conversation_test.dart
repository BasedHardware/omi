import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:omi/backend/http/api/conversations.dart';

void main() {
  group('interpretProcessInProgressConversationResponse', () {
    test('HTTP 200 parses CreateConversationResponse', () {
      const body = '''
{
  "messages": [],
  "conversation": {
    "id": "conv-123",
    "created_at": "2025-01-15T10:30:00.000Z",
    "started_at": "2025-01-15T10:30:00.000Z",
    "finished_at": null,
    "summary": "Overview",
    "structured": {"title": "Test", "overview": "Overview"}
  }
}
''';

      final result = interpretProcessInProgressConversationResponse(
        http.Response(body, 200),
        reportUnexpectedFailure: (_) => fail('unexpected failure callback'),
      );

      expect(result, isNotNull);
      expect(result!.conversation?.id, 'conv-123');
      expect(result.messages, isEmpty);
    });

    test('HTTP 404 returns null without reporting crash', () {
      var reported = false;

      final result = interpretProcessInProgressConversationResponse(
        http.Response('{"detail":"Conversation in progress not found"}', 404),
        reportUnexpectedFailure: (_) => reported = true,
      );

      expect(result, isNull);
      expect(reported, isFalse);
    });

    test('HTTP 500 reports unexpected failure and returns null', () {
      var reportedBody = '';

      final result = interpretProcessInProgressConversationResponse(
        http.Response('{"detail":"Internal Server Error"}', 500),
        reportUnexpectedFailure: (body) => reportedBody = body,
      );

      expect(result, isNull);
      expect(reportedBody, '{"detail":"Internal Server Error"}');
    });
  });
}
