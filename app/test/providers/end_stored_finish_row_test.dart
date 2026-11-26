// Reliability experiment `end_open_conversation`: an End the server stored before its conversation
// existed ("End stored, result to come") names no conversation, so Home's Processing row had nothing
// to hand over to and stayed for 20 minutes. The conversation that End closes carries the End's
// instant (`v3_manual_cut_at`); the row is handed to it, and is removed after two minutes if none comes.
import 'package:fake_async/fake_async.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/providers/conversations_v3_provider.dart';
import 'package:omi/services/capture/optimistic_processing.dart';

final firstEnd = DateTime.utc(2026, 11, 26, 0, 36, 27, 759);
final secondEnd = DateTime.utc(2026, 11, 26, 0, 36, 48, 954);

/// A conversation as the list read serves it. [closedBy] is the End that closed it, as the server
/// stores it (microseconds, UTC).
ServerConversation ended(String id, {DateTime? closedBy, String status = 'completed', String tile = 'done'}) =>
    ServerConversation.fromJson({
      'id': id,
      'created_at': '2026-11-26T00:36:35.817739Z',
      'started_at': '2026-11-26T00:36:35.817739Z',
      'finished_at': '2026-11-26T00:36:48.156999Z',
      'source': 'omi',
      'status': status,
      'kind': 'conversation',
      'tile_state': tile,
      'manual_end': true,
      'v3_recording_ids': ['upload-recording'],
      if (closedBy != null) 'v3_manual_cut_at': '${closedBy.toIso8601String().replaceFirst('Z', '')}000Z',
      'structured': {'title': 'Russian Microphone Test', 'overview': 'A synthetic summary', 'emoji': '🎙️'},
    });

ConversationsV3Provider provider() => ConversationsV3Provider(uid: () => 'owner', cached: 'owner:1');

/// The finish as the phone-file route starts it: no conversation named, and the recording it knows is
/// the listening session's own empty one, which no conversation lists.
ServerConversation startStoredEnd(ConversationsV3Provider v3, DateTime endedAt) {
  final row = OptimisticProcessingPlaceholder.conversation(targetConversationId: 'listening-recording');
  v3.startManualFinish(row, 'listening-recording', captureId: 'capture-1');
  expect(v3.settleManualFinish(row, null, alreadyClosed: true, endStoredAt: endedAt), isTrue);
  return row;
}

void main() {
  test('the list row carries the End that closed it', () {
    expect(ended('c', closedBy: secondEnd).v3?.manualCutAt, secondEnd);
    expect(ended('c').v3?.manualCutAt, isNull);
    final cached = ServerConversation.fromJson(ended('c', closedBy: secondEnd).toJson());
    expect(cached.v3?.manualCutAt, secondEnd, reason: 'the cached row keeps it');
  });

  test('the Processing row is handed to the conversation that carries the same End time', () {
    final v3 = provider();
    addTearDown(v3.dispose);
    final row = startStoredEnd(v3, secondEnd);

    // The conversation the previous End closed is already on Home; it is not this End's result.
    final earlier = ended('earlier', closedBy: firstEnd);
    expect(v3.finishHasSuccessor([earlier]), isFalse);
    expect(v3.finishTerminalMatch([earlier]), isNull);
    // Nor is a conversation that ended by silence.
    expect(v3.finishHasSuccessor([ended('silent')]), isFalse);
    expect(v3.finishRow, same(row));

    // Its own conversation, still open or being cut, does not take the row yet.
    expect(v3.finishHasSuccessor([ended('mine', closedBy: secondEnd, status: 'in_progress', tile: 'live')]), isFalse);

    final mine = ended('mine', closedBy: secondEnd);
    expect(v3.finishHasSuccessor([earlier, mine]), isTrue);
    expect(v3.finishTerminalMatch([earlier, mine])?.id, 'mine');
    expect(v3.acknowledgeManualFinish(row), isTrue);
    expect(v3.finishRow, isNull);
  });

  test('with no conversation for the stored End, the row goes after two minutes and Home reads once', () {
    fakeAsync((async) {
      final v3 = provider();
      final row = startStoredEnd(v3, secondEnd);

      async.elapse(OptimisticProcessingPlaceholder.timeout - const Duration(seconds: 1));
      expect(v3.finishRow, same(row));
      expect(v3.suppressListeningAfterFinish('capture-1'), isTrue);

      async.elapse(const Duration(seconds: 2));
      expect(v3.finishRow, isNull);
      expect(v3.suppressListeningAfterFinish('capture-1'), isFalse);
      expect(v3.takeHomeReconcile(), isTrue);
      // Nothing is left for the 20-minute deadline to act on.
      async.elapse(const Duration(minutes: 20));
      expect(v3.takeHomeReconcile(), isFalse);
      // A conversation that arrives later is an ordinary Home row, not this finish's successor.
      expect(v3.finishHasSuccessor([ended('mine', closedBy: secondEnd)]), isFalse);
      v3.dispose();
    });
  });

  test('a finish accepted without a stored End time keeps its row past two minutes, as before', () {
    fakeAsync((async) {
      final v3 = provider();
      final row = OptimisticProcessingPlaceholder.conversation(targetConversationId: 'rec-1');
      v3.startManualFinish(row, null);
      expect(v3.settleManualFinish(row, null, alreadyClosed: true), isTrue);

      async.elapse(const Duration(minutes: 5));
      expect(v3.finishRow, same(row));
      // It still matches only by its recording, never by an End time.
      expect(v3.finishHasSuccessor([ended('other', closedBy: secondEnd)]), isFalse);
      v3.acknowledgeManualFinish(row);
      v3.dispose();
    });
  });
}
