import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';

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
}
