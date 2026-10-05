import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/http/api/speaker_labels.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';

class _FailingRefreshProvider extends ConversationDetailProvider {
  _FailingRefreshProvider({required this.sentinel, super.assignSpeaker, super.rejectSpeaker});

  final Object sentinel;

  @override
  Future<void> refreshConversation({bool trackLoad = false}) async => throw sentinel;
}

Future<void> _flushEventQueue() async {
  await Future<void>.delayed(Duration.zero);
  await Future<void>.delayed(Duration.zero);
}

Future<({List<Object> unhandled, Object? harnessError})> _runInGuardedZone(Future<void> Function() body) async {
  final unhandled = <Object>[];
  final done = Completer<void>();
  Object? harnessError;
  runZonedGuarded(() async {
    try {
      await body();
    } catch (e) {
      harnessError = e;
    } finally {
      await _flushEventQueue();
      done.complete();
    }
  }, (error, stackTrace) => unhandled.add(error));
  await done.future;
  return (unhandled: unhandled, harnessError: harnessError);
}

ServerConversation _conversation() => ServerConversation(
      id: 'conversation',
      createdAt: DateTime(2026),
      structured: Structured('Title', 'Overview'),
      transcriptSegments: [
        TranscriptSegment(
          id: 'segment',
          text: 'Hello',
          speaker: 'SPEAKER_00',
          isUser: false,
          personId: null,
          translations: [],
          start: 0,
          end: 1,
        ),
      ],
    );

ServerConversation _syncConversation() => ServerConversation(
      id: 'abcdefab-1234-5678-90ab-cdefabcdefab',
      createdAt: DateTime(2026),
      structured: Structured('Title', 'Overview'),
      status: ConversationStatus.completed,
      transcriptSegments: [
        TranscriptSegment(
          id: 'segment',
          text: 'Hello',
          speaker: 'SPEAKER_00',
          isUser: false,
          personId: null,
          translations: [],
          start: 0,
          end: 1,
        ),
      ],
    );

void _select(ConversationDetailProvider provider, ServerConversation value) {
  provider.selectedDate = value.createdAt;
  provider.setCachedConversation(value);
}

void main() {
  test('applies immediately and rolls back after a failed save', () async {
    final response = Completer<bool>();
    final provider = ConversationDetailProvider(
      assignSpeaker: (_, __, {isUser, personId, speakerId}) => response.future,
    );
    _select(provider, _conversation());
    var failures = 0;
    final pending = provider.startSpeakerAssignment(['segment'], 'alice', onFailed: () => failures++)!;
    expect(provider.conversation.transcriptSegments.single.personId, 'alice');
    response.complete(false);
    expect(await pending, isFalse);
    expect(provider.conversation.transcriptSegments.single.personId, isNull);
    expect(failures, 1);
    provider.dispose();
  });

  test('older failure cannot undo a newer edit or a reloaded conversation', () async {
    final old = Completer<bool>();
    final newer = Completer<bool>();
    final provider = ConversationDetailProvider(
      assignSpeaker: (_, __, {isUser, personId, speakerId}) => personId == 'alice' ? old.future : newer.future,
    );
    _select(provider, _conversation());
    final first = provider.startSpeakerAssignment(['segment'], 'alice')!;
    final second = provider.startSpeakerAssignment(['segment'], 'bob')!;
    old.complete(false);
    expect(await first, isFalse);
    expect(provider.conversation.transcriptSegments.single.personId, 'bob');
    newer.complete(true);
    expect(await second, isTrue);

    final stale = Completer<bool>();
    final reloadProvider = ConversationDetailProvider(
      assignSpeaker: (_, __, {isUser, personId, speakerId}) => stale.future,
    );
    _select(reloadProvider, _conversation());
    final pending = reloadProvider.startSpeakerAssignment(['segment'], 'alice')!;
    final reloaded = _conversation();
    reloaded.transcriptSegments.single.personId = 'server-person';
    reloadProvider.setCachedConversation(reloaded);
    stale.complete(false);
    expect(await pending, isFalse);
    expect(reloadProvider.conversation.transcriptSegments.single.personId, 'server-person');
    provider.dispose();
    reloadProvider.dispose();
  });

  test('new person shows a temporary name then reconciles before assignment', () async {
    final created = Completer<String?>();
    final saved = Completer<bool>();
    String? wirePerson;
    final provider = ConversationDetailProvider(
      assignSpeaker: (_, __, {isUser, personId, speakerId}) {
        wirePerson = personId;
        return saved.future;
      },
    );
    _select(provider, _conversation());
    String? reconciled;
    final pending = provider.startSpeakerAssignment(
      ['segment'],
      'optimistic-person:1',
      createPerson: () => created.future,
      onReconciled: (id) => reconciled = id,
    )!;
    expect(provider.conversation.transcriptSegments.single.personId, 'optimistic-person:1');
    created.complete('real-person');
    await Future<void>.delayed(Duration.zero);
    expect(reconciled, 'real-person');
    expect(provider.conversation.transcriptSegments.single.personId, 'real-person');
    expect(wirePerson, 'real-person');
    saved.complete(true);
    expect(await pending, isTrue);
    provider.dispose();
  });

  test('a throwing reconciliation callback reaches the caller without an unhandled zone error', () async {
    final sentinel = StateError('reconciled-boom');
    Object? callerError;
    late ConversationDetailProvider provider;

    final outcome = await _runInGuardedZone(() async {
      provider = ConversationDetailProvider(assignSpeaker: (_, __, {isUser, personId, speakerId}) async => true);
      _select(provider, _conversation());
      final pending = provider.startSpeakerAssignment(
        ['segment'],
        'optimistic-person:1',
        createPerson: () async => 'real-person',
        onReconciled: (_) => throw sentinel,
      )!;
      try {
        await pending;
      } catch (e) {
        callerError = e;
      }
      provider.dispose();
    });

    expect(outcome.harnessError, isNull);
    expect(callerError, same(sentinel));
    expect(outcome.unhandled, isEmpty);
  });

  test('a failing finalization after a queued rejection reaches the caller without an unhandled zone error', () async {
    final sentinel = StateError('refresh-boom');
    final assignGate = Completer<bool>();
    bool? assignmentResult;
    Object? callerError;
    late _FailingRefreshProvider provider;

    final outcome = await _runInGuardedZone(() async {
      final conversation = _syncConversation();
      provider = _FailingRefreshProvider(
        sentinel: sentinel,
        assignSpeaker: (_, __, {isUser, personId, speakerId}) => assignGate.future,
        rejectSpeaker: (_, __, ___, {personId, segmentIds}) async => ApiSuccess(conversation),
      );
      _select(provider, conversation);
      final segment = conversation.transcriptSegments.single;
      final assignment = provider.startSpeakerAssignment(['segment'], 'alice')!;
      await Future<void>.delayed(Duration.zero);
      final rejection = provider.rejectSpeakerLabel(segment, SpeakerRejection.notPerson);
      assignGate.complete(true);
      assignmentResult = await assignment;
      try {
        await rejection;
      } catch (e) {
        callerError = e;
      }
      provider.dispose();
    });

    expect(outcome.harnessError, isNull);
    expect(assignmentResult, isTrue);
    expect(callerError, same(sentinel));
    expect(outcome.unhandled, isEmpty);
  });
}
