import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/env/env.dart';
import 'package:omi/services/capture/empty_recording_notice.dart';

class _TestEnv implements EnvFields {
  @override
  String? get apiBaseUrl => 'https://api.example.test/';

  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

http.Response retryableProcessingFailure({String retryAfter = '2'}) => http.Response(
      jsonEncode({
        'detail': {'code': 'conversation_processing_retryable', 'message': 'retry'},
      }),
      503,
      headers: {'retry-after': retryAfter},
    );

/// Regression test for #9241: processInProgressConversation() used to
/// crash-report every non-200 response from POST /v1/conversations. A benign
/// 404 — raised when the WS auto-finalize path already consumed the
/// in-progress conversation and cleared its Redis pointer before this
/// client-initiated create ran — flooded crash reporting for a race with no
/// user-visible impact (the conversation was already finalized).
///
/// The production code branches on isBenignInProgressConversationCreateStatus,
/// so exercising that predicate covers the crash-vs-skip decision without the
/// non-injectable makeApiCall / crashReporter singletons.
void main() {
  setUpAll(() => Env.init(_TestEnv()));

  group('isBenignInProgressConversationCreateStatus', () {
    test('404 is benign (WS already finalized the conversation) — no crash', () {
      expect(isBenignInProgressConversationCreateStatus(404), isTrue);
    });

    test('genuine failures still report a crash', () {
      for (final status in [304, 400, 401, 409, 429, 500, 502, 503]) {
        expect(
          isBenignInProgressConversationCreateStatus(status),
          isFalse,
          reason: 'status $status should not be treated as benign',
        );
      }
    });
  });

  group('processInProgressConversationOutcome', () {
    test('sends the known live window ID and preserves a benign 404 answer', () async {
      final outcome = await processInProgressConversationOutcome(
        liveConversationId: 'live-1',
        sendRequest: (request) async {
          expect(request.method, 'POST');
          expect(jsonDecode(request.body), {'live_conversation_id': 'live-1'});
          return http.Response('', 404);
        },
      );

      expect(outcome.absence, ProcessAbsence.notFound);
      expect(outcome.response, isNull);
    });

    test('retries the identical in-progress request after the typed 503 and returns its summary', () async {
      final requests = <ApiRequest>[];
      final waits = <Duration>[];
      final row = ServerConversation(
        id: 'conv-retry',
        createdAt: DateTime.utc(2026, 11, 16),
        structured: Structured('Budget Review', 'The team agreed on the Q2 budget.'),
      );

      final outcome = await processInProgressConversationOutcome(
        sendRequest: (request) async {
          requests.add(request);
          if (requests.length == 1) return retryableProcessingFailure();
          return http.Response(
            jsonEncode({'conversation': row.toJson(), 'messages': []}),
            200,
            headers: {'content-type': 'application/json'},
          );
        },
        waitBeforeRetry: (delay) async => waits.add(delay),
      );

      expect(requests, hasLength(2));
      expect(requests[1].url, requests[0].url);
      expect(requests[1].method, requests[0].method);
      expect(requests[1].headers, requests[0].headers);
      expect(requests[1].body, requests[0].body);
      expect(requests[0].method, 'POST');
      expect(requests[0].body, '{}');
      expect(waits, [const Duration(seconds: 2)]);
      expect(outcome.response?.conversation?.id, 'conv-retry');
      expect(outcome.response?.conversation?.structured.title, 'Budget Review');
      expect(outcome.absence, isNull);
    });

    test('stops after one retry when the typed failure repeats', () async {
      final requests = <ApiRequest>[];
      final waits = <Duration>[];

      final outcome = await processInProgressConversationOutcome(
        sendRequest: (request) async {
          requests.add(request);
          return retryableProcessingFailure(retryAfter: '3');
        },
        waitBeforeRetry: (delay) async => waits.add(delay),
      );

      expect(requests, hasLength(2));
      expect(requests[1].body, requests[0].body);
      expect(waits, [const Duration(seconds: 3)]);
      expect(outcome.absence, ProcessAbsence.transport);
      expect(outcome.response, isNull);
    });

    test('does not retry other 503 responses', () async {
      var requests = 0;
      final reported = <http.Response>[];

      final outcome = await processInProgressConversationOutcome(
        sendRequest: (_) async {
          requests++;
          return http.Response('server unavailable', 503);
        },
        waitBeforeRetry: (_) async => fail('unexpected retry'),
        reportUnexpectedResponse: reported.add,
      );

      expect(requests, 1);
      expect(reported, hasLength(1));
      expect(outcome.absence, ProcessAbsence.transport);
    });
  });
}
