import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/widgets/transcript.dart';

import 'support/hermetic_boot.dart';
import 'support/journey_evidence.dart';

/// Client half of the persistence contract. The fixture serves already matched
/// conversations; real backend teaching/matching is exercised separately by
/// test_taught_speaker_persistence.py. This does not simulate acoustic accuracy.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('persisted person id renders after reload, including an offline-synced conversation', (tester) async {
    final evidence = JourneyEvidence.begin(journeyId: 'j6_persisted_speaker_name', lane: journeyLane);
    final person = Person(
      id: 'synthetic-person-1',
      name: 'Synthetic Alex',
      createdAt: DateTime.utc(2026, 9, 19),
      updatedAt: DateTime.utc(2026, 9, 19),
    );
    final savedPrefs = {
      'cachedPeople': [jsonEncode(person.toJson())]
    };
    final server = await JourneyHermeticBoot.start(extraPrefs: savedPrefs);
    addTearDown(JourneyHermeticBoot.stop);

    for (final id in ['later-conversation', 'offline-synced-conversation']) {
      server.conversations.add(ServerConversation(
        id: id,
        createdAt: DateTime.utc(2026, 9, 19),
        structured: Structured('Synthetic conversation', 'Synthetic speech', category: 'other'),
        transcriptSegments: [
          TranscriptSegment(
            id: 'segment-$id',
            text: 'Synthetic speech about a trip.',
            speaker: 'SPEAKER_07',
            isUser: false,
            translations: [],
            personId: person.id,
            start: 0,
            end: 10,
          )
        ],
      ).toJson());
    }

    // Reinitialize preferences and providers without carrying a live speaker map.
    await JourneyHermeticBoot.resetAppState(extraPrefs: savedPrefs);
    final provider = ConversationProvider(isSignedIn: () => true);
    addTearDown(provider.dispose);
    await provider.forceRefreshConversations();
    expect(provider.conversations, hasLength(2));
    for (final conversation in provider.conversations) {
      await JourneyHermeticBoot.pumpPage(
        tester,
        page:
            Scaffold(body: TranscriptWidget(key: ValueKey(conversation.id), segments: conversation.transcriptSegments)),
      );
      await tester.pumpAndSettle();
      final named = find.text(person.name).evaluate().isNotEmpty;
      evidence.record(conversation.id,
          ok: named, invariant: 'persisted person_id resolves through reloaded people to the displayed name');
      expect(find.text(person.name), findsOneWidget);
    }

    // Account teardown clears the cached name; the widget must not invent an
    // identity from a reused diarization number or retain the previous label.
    await JourneyHermeticBoot.resetAppState(uid: 'synthetic-account-b');
    await JourneyHermeticBoot.pumpPage(
      tester,
      page: Scaffold(
          body: TranscriptWidget(
              key: const ValueKey('account-b'), segments: provider.conversations.first.transcriptSegments)),
    );
    await tester.pumpAndSettle();
    final cleared = find.text(person.name).evaluate().isEmpty;
    evidence.record('account-cache-cleared',
        ok: cleared, invariant: 'another account does not display the previous account person name');
    expect(find.text(person.name), findsNothing);
    await evidence.write();
  });
}
