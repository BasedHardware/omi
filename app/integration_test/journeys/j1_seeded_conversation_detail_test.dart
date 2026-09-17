import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/services/dev_controls/journey_faults.dart';
import 'package:omi/services/dev_controls/semantic_controls.dart';

import 'support/hermetic_boot.dart';
import 'support/journey_evidence.dart';

/// Journey 1 — seeded conversation detail (SCA-488 / C2).
///
/// Preconditions are an executable seed contract: a fixture conversation
/// with an exact synthetic identity is served by the loopback fixture
/// backend; the journey signs in the fixture principal via the hermetic
/// boot's seeded preferences.
///
/// Positive: fetch conversations through the REAL provider HTTP path
/// (ConversationProvider), assert the exact synthetic record identity came
/// back from the server (not a local echo), then open the REAL
/// [ConversationDetailPage] for the fetched record and assert the seeded
/// title renders on screen.
///
/// Negative: a wrong-owner bearer must be rejected before any seeded record
/// is served — the provider must not surface the record (ownership
/// invariant).
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  const seededId = 'seeded-conv-j1-0001';
  const seededTitle = 'Journey one seeded conversation';

  ServerConversation seedConversation() {
    return ServerConversation(
      id: seededId,
      createdAt: DateTime.utc(2026, 9, 16, 9, 0, 0),
      structured: Structured(
        seededTitle,
        'Deterministic overview for the seeded conversation-detail journey.',
        emoji: '🧠',
        category: 'other',
      ),
    );
  }

  testWidgets('positive: seeded record fetched through the real provider path and rendered in detail', (tester) async {
    final evidence = JourneyEvidence.begin(journeyId: 'j1_seeded_conversation_detail', lane: journeyLane);
    final server = await JourneyHermeticBoot.start();
    addTearDown(JourneyHermeticBoot.stop);
    server.conversations.add(seedConversation().toJson());
    evidence.stateBefore = SemanticControls.instance.state().toJson();

    final conversationProvider = ConversationProvider(isSignedIn: () => true);
    await conversationProvider.forceRefreshConversations();
    final fetched = conversationProvider.conversations;
    evidence.record('server-returned-seeded-record',
        ok: fetched.any((c) => c.id == seededId),
        invariant: 'the seeded conversation is served through the real API path',
        detail: fetched.map((c) => c.id).toList());
    expect(fetched.any((c) => c.id == seededId), isTrue,
        reason: 'fixture must serve the seeded record via GET /v1/conversations');

    final seeded = fetched.firstWhere((c) => c.id == seededId);
    final identityExact = seeded.structured.title == seededTitle &&
        seeded.createdAt.isAtSameMomentAs(DateTime.utc(2026, 9, 16, 9, 0, 0)) &&
        seeded.id == seededId;
    evidence.record('exact-synthetic-identity',
        ok: identityExact, invariant: 'the fetched record carries the exact synthetic identity (id, title, timestamp)');
    expect(identityExact, isTrue, reason: 'record identity must be the seeded identity, not a local echo');

    await JourneyHermeticBoot.pumpPage(
      tester,
      page: ConversationDetailPage(conversation: seeded),
      providers: [
        // The detail provider resolves through groupedConversations[selectedDate]
        // and validates the same local day key, with selectedDate defaulting to
        // DateTime.now() — pin it to the seed's local day so the journey is
        // independent of the calendar day and timezone it runs in.
        ChangeNotifierProvider<ConversationDetailProvider>.value(
          value: ConversationDetailProvider()..selectedDate = conversationLocalDayKey(seeded.createdAt),
        ),
        ChangeNotifierProvider<ConversationProvider>.value(value: conversationProvider),
      ],
    );
    await tester.pumpAndSettle(const Duration(seconds: 3));

    final titleRendered = find.textContaining(seededTitle).evaluate().isNotEmpty;
    evidence.record('detail-renders-seeded-title',
        ok: titleRendered, invariant: 'the conversation detail screen renders the seeded record');
    expect(titleRendered, isTrue, reason: 'detail page must render the seeded conversation title');

    evidence.stateAfter = SemanticControls.instance.state().toJson();
    expect(evidence.failed, 0);
    await evidence.write();
  });

  testWidgets('negative: wrong-owner session cannot read the seeded record', (tester) async {
    final evidence =
        JourneyEvidence.begin(journeyId: 'j1_seeded_conversation_detail.wrong-owner-session', lane: journeyLane);
    final server = await JourneyHermeticBoot.start();
    addTearDown(JourneyHermeticBoot.stop);
    server.conversations.add(seedConversation().toJson());
    // Client-side egress fault: every authenticated request carries the wrong
    // synthetic principal; the fixture backend must refuse it.
    JourneyFaultGate.instance.arm(JourneyFault.wrongOwnerSession);
    evidence.stateBefore = SemanticControls.instance.state().toJson();

    final conversationProvider = ConversationProvider(isSignedIn: () => true);
    await conversationProvider.forceRefreshConversations();
    final fetched = conversationProvider.conversations;
    final leaked = fetched.any((c) => c.id == seededId);
    evidence.record('ownership-rejected',
        ok: !leaked,
        invariant: JourneyFault.wrongOwnerSession.invariant,
        detail: 'fetched ${fetched.length} records under wrong owner');
    if (leaked) {
      await evidence.write();
      fail('seeded record readable under wrong-owner session');
    }
    evidence.failed++;
    evidence.assertions.add({
      'name': 'journey-under-fault',
      'ok': false,
      'invariant': JourneyFault.wrongOwnerSession.invariant,
      'detail': 'server refused wrong-owner bearer — expected failure',
    });
    evidence.stateAfter = SemanticControls.instance.state().toJson();
    await evidence.write();
  });
}
