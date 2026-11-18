import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/pages/conversation_detail/widgets.dart' show summaryRetrySlotApplies;
import 'package:omi/providers/transcription_pending_conversations.dart';

import '../helpers/summary_fixtures.dart';
import '../helpers/transcription_hold_wire.dart';

void main() {
  setUpAll(initHeldWireEnv);
  setUp(TranscriptionPendingConversations.reset);
  tearDown(TranscriptionPendingConversations.reset);

  group('held recording wire copies decode as the app expects', () {
    // If the server changes any of these copies, this group fails instead of the app silently
    // offering a summary retry that can only be answered 409 again.
    test('(a) the Home/list row is a failed Home step titled with the server stand-in', () {
      final row = heldListRow();
      expect(row.homeStep, 'failed');
      expect(row.status, ConversationStatus.completed);
      expect(row.summaryRetryable, isFalse);
      expect(row.transcriptSegments, isEmpty);
      expect(row.structured.title, TranscriptionPendingConversations.serverHoldTitle);
      expect(TranscriptionPendingConversations.replacesTitle(row), isFalse, reason: 'not marked yet');
      TranscriptionPendingConversations.mark(row.id);
      expect(TranscriptionPendingConversations.replacesTitle(row), isTrue);
      TranscriptionPendingConversations.observe(row);
      expect(TranscriptionPendingConversations.contains(row.id), isTrue, reason: 'the row proves nothing settled');
    });

    test('(b) the detail copy has no Home step, so only the not-transcribed answer opens the slot', () {
      final detail = heldDetail();
      expect(detail.homeStep, isNull);
      expect(detail.status, ConversationStatus.completed);
      expect(detail.summaryRetryable, isFalse);
      expect(detail.transcriptSegments, isEmpty);
      expect(summaryRetrySlotApplies(detail), isFalse);
      TranscriptionPendingConversations.mark(detail.id);
      expect(summaryRetrySlotApplies(detail), isTrue);
      TranscriptionPendingConversations.observe(detail);
      expect(TranscriptionPendingConversations.contains(detail.id), isTrue);
    });

    test('(c) a 200 inside the window maps to the waiting result with its copy', () {
      final result = reprocessResultFromResponse(heldJsonResponse(200, heldRetryWaitingJson()));
      expect(result, isA<ReprocessTranscriptionPending>());
      expect(result.conversation!.homeStep, 'transcribing');
      expect(result.conversation!.status, ConversationStatus.processing);
    });

    test('(d) the 409 body maps to the waiting result with no copy', () {
      final result = reprocessResultFromResponse(heldJsonResponse(409, heldReprocess409Body));
      expect(result, isA<ReprocessTranscriptionPending>());
      expect(result.conversation, isNull);
    });
  });

  group('reProcessConversationServer records the answer', () {
    Future<ReprocessResult> call(int status, Object body) => reProcessConversationServer(
          heldConversationId,
          send: (_) async => heldJsonResponse(status, body),
        );

    test('a 409 transcription_pending marks the conversation', () async {
      final result = await call(409, heldReprocess409Body);
      expect(result, isA<ReprocessTranscriptionPending>());
      expect(TranscriptionPendingConversations.contains(heldConversationId), isTrue);
    });

    test('a 200 with a summarized copy unmarks it', () async {
      TranscriptionPendingConversations.mark(heldConversationId);
      final summarized = summaryConversation(id: heldConversationId, overview: 'Picked Friday.').toJson();
      final result = await call(200, summarized);
      expect(result, isA<ReprocessSuccess>());
      expect(TranscriptionPendingConversations.contains(heldConversationId), isFalse);
    });

    test('a 200 still transcribing returns the waiting copy and keeps no marker', () async {
      TranscriptionPendingConversations.mark(heldConversationId);
      final result = await call(200, heldRetryWaitingJson());
      expect(result, isA<ReprocessTranscriptionPending>());
      expect(result.conversation!.homeStep, 'transcribing');
      expect(TranscriptionPendingConversations.contains(heldConversationId), isFalse);
    });

    test('no response is a failure and leaves the marker as it was', () async {
      TranscriptionPendingConversations.mark(heldConversationId);
      final result = await reProcessConversationServer(heldConversationId, send: (_) async => null);
      expect(result, isA<ReprocessFailed>());
      expect(TranscriptionPendingConversations.contains(heldConversationId), isTrue);
    });
  });
}
