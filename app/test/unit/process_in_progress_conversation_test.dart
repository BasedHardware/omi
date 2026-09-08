import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/http/api/conversations.dart';

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
}
