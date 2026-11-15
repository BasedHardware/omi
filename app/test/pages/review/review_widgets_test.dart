import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/open_loops.dart';
import 'package:omi/backend/schema/review.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/review/review_item_sheet.dart';
import 'package:omi/pages/review/widgets/review_entry_card.dart';
import 'package:omi/pages/review/widgets/review_question_card.dart';
import 'package:omi/providers/review_provider.dart';
import 'package:omi/ui/ui.dart';

const _task = ReviewItem(
  itemId: 'task:c1',
  kind: ReviewItemKind.task,
  task: TaskItem(candidateId: 'c1', description: 'Send the signed SOW'),
);

const _speaker = ReviewItem(
  itemId: 'speaker:p1',
  kind: ReviewItemKind.speaker,
  quote: 'See you Friday.',
  speaker: SpeakerItem(
    promptId: 'p1',
    conversationId: 'c9',
    conversationTitle: 'Sync',
    start: 0,
    end: 5,
    candidates: [PersonRef(personId: 'bela', name: 'Béla')],
  ),
);

const _samePerson = ReviewItem(
  itemId: 'same_person:ab',
  kind: ReviewItemKind.samePerson,
  samePerson: SamePersonItem(
    left: EntitySummary(entityId: 'person:a', type: EntityType.person, name: 'Sam'),
    right: EntitySummary(entityId: 'person:b', type: EntityType.person, name: 'Samuel'),
    reason: 'Same voice',
  ),
);

const _proposal = ReviewItem(
  itemId: 'agent_proposal:p',
  kind: ReviewItemKind.agentProposal,
  agentProposal: AgentProposalItem(
    editKind: 'merge_people',
    targetLabel: 'Bela K',
    otherLabel: 'Béla',
    reason: 'Same company and the same phone number.',
  ),
);

const _memoryProposal = ReviewItem(
  itemId: 'agent_proposal:m',
  kind: ReviewItemKind.agentProposal,
  agentProposal: AgentProposalItem(
    editKind: 'memory',
    targetLabel: 'Lives in Hanoi',
    before: 'Lives in Hanoi',
    after: 'Lives in Ho Chi Minh City',
    reason: 'Moved in September.',
  ),
);

Future<ReviewProvider> _provider(List<ReviewItem> items, List<(String, Map<String, dynamic>)> sent) async {
  final provider = ReviewProvider(
    isEligible: () => true,
    reportChannel: (_, {appBuild}) async => const ApiSuccess<void>(null),
    loadItems: () async => ApiSuccess(ReviewItemsResponse(items: items, remainingToday: items.length)),
    loadOpenLoopCards: () async => const ApiSuccess(OpenLoopCardsResponse(cards: [])),
    sendAnswer: (item, answer) async {
      sent.add((item.itemId, answer.toJson(item.kind)));
      return const ApiSuccess(0);
    },
  );
  await provider.load();
  return provider;
}

Widget _host(ReviewProvider provider, Widget child) => ChangeNotifierProvider<ReviewProvider>.value(
      value: provider,
      child: MaterialApp(
        theme: buildOmiTheme(),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(body: ListView(children: [child])),
      ),
    );

void main() {
  testWidgets('a quick answer on the card sends it and the card leaves the queue', (tester) async {
    final sent = <(String, Map<String, dynamic>)>[];
    final provider = await _provider([_speaker], sent);
    await tester.pumpWidget(_host(provider, const ReviewQuestionCard(item: _speaker)));
    expect(find.text('Who said this?'), findsOneWidget);
    expect(find.text('“See you Friday.”'), findsOneWidget);

    await tester.tap(find.text('Béla'));
    await tester.pumpAndSettle();
    expect(sent.single.$1, 'speaker:p1');
    expect((sent.single.$2['speaker'] as Map)['person_id'], 'bela');
    expect(provider.items, isEmpty);
  });

  testWidgets('a Dream suggestion card asks the question and applies on Apply', (tester) async {
    final sent = <(String, Map<String, dynamic>)>[];
    final provider = await _provider([_proposal], sent);
    await tester.pumpWidget(_host(provider, const ReviewQuestionCard(item: _proposal)));
    expect(find.text('Is “Bela K” the same person as “Béla”?'), findsOneWidget);
    expect(find.text('Dismiss'), findsOneWidget);

    await tester.tap(find.text('Apply'));
    await tester.pumpAndSettle();
    expect(sent.single.$1, 'agent_proposal:p');
    expect(sent.single.$2['agent_proposal'], {'decision': 'accept'});
    expect(provider.items, isEmpty);
  });

  for (final item in [_speaker, _samePerson, _proposal]) {
    testWidgets('a 409 uses neutral copy for ${item.kind.name}', (tester) async {
      final provider = ReviewProvider(
        isEligible: () => true,
        reportChannel: (_, {appBuild}) async => const ApiSuccess<void>(null),
        loadItems: () async => ApiSuccess(ReviewItemsResponse(items: [item], remainingToday: 3)),
        loadOpenLoopCards: () async => const ApiSuccess(OpenLoopCardsResponse(cards: [])),
        sendAnswer: (_, __) async => const ApiFailure(ApiProblem(ApiProblemKind.rejected, statusCode: 409)),
      );
      await provider.load();
      await tester.pumpWidget(_host(provider, ReviewQuestionCard(item: item)));
      final label = switch (item.kind) {
        ReviewItemKind.speaker => 'Béla',
        ReviewItemKind.samePerson => 'Yes',
        _ => 'Apply',
      };
      await tester.tap(find.text(label));
      await tester.pumpAndSettle();
      expect(find.text('This question is out of date, so nothing changed.'), findsOneWidget);
      expect(provider.lastAnswerConflict, isTrue);
      expect(provider.items, isEmpty);
      expect(provider.remainingToday, 3);
    });
  }

  testWidgets('the suggestion sheet shows the current and suggested values and the reason', (tester) async {
    final sent = <(String, Map<String, dynamic>)>[];
    final provider = await _provider([_memoryProposal], sent);
    var closed = false;
    await tester.pumpWidget(_host(provider, ReviewItemDetail(item: _memoryProposal, onDone: () => closed = true)));
    expect(find.text('CURRENT'), findsOneWidget);
    expect(find.text('Lives in Hanoi'), findsOneWidget);
    expect(find.text('SUGGESTED'), findsOneWidget);
    expect(find.text('Lives in Ho Chi Minh City'), findsOneWidget);
    expect(find.text('Moved in September.'), findsOneWidget);

    await tester.tap(find.text('Dismiss'));
    await tester.pumpAndSettle();
    expect(closed, isTrue);
    expect(sent.single.$2['agent_proposal'], {'decision': 'dismiss'});
  });

  testWidgets('task sheet shows dismiss reasons only after Dismiss', (tester) async {
    final sent = <(String, Map<String, dynamic>)>[];
    final provider = await _provider([_task], sent);
    var closed = false;
    await tester.pumpWidget(_host(provider, ReviewItemDetail(item: _task, onDone: () => closed = true)));
    expect(find.text('Not Mine'), findsNothing);

    await tester.tap(find.byKey(const Key('review_task_dismiss')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Not Mine'));
    await tester.pumpAndSettle();
    expect(closed, isTrue);
    expect((sent.single.$2['task'] as Map)['dismiss_reason'], 'not_mine');
  });

  testWidgets('the Home entry draws nothing while Review is off, and hides when caught up', (tester) async {
    final off = ReviewProvider(
        isEligible: () => true,
        reportChannel: (_, {appBuild}) async => const ApiSuccess<void>(null),
        loadItems: () async => const ApiFailure(ApiProblem(ApiProblemKind.notFound)),
        loadOpenLoopCards: () async => const ApiSuccess(OpenLoopCardsResponse(cards: [])));
    await off.load();
    await tester.pumpWidget(_host(off, const ReviewEntryCard()));
    expect(find.byKey(const Key('review_entry_card')), findsNothing);

    final empty = await _provider(const [], []);
    await tester.pumpWidget(_host(empty, const ReviewEntryCard()));
    // Caught up: nothing on Home; Recent Changes lives in Activity behind the bell.
    expect(find.byKey(const Key('review_entry_card')), findsNothing);
    expect(find.text('Recent Changes'), findsNothing);

    final some = await _provider([_task], []);
    await tester.pumpWidget(_host(some, const ReviewEntryCard()));
    expect(find.byKey(const Key('review_entry_card')), findsOneWidget);
  });

  testWidgets('on launch, before Review availability is known, Home draws nothing', (tester) async {
    final pending = Completer<ApiResult<ReviewItemsResponse>>();
    final launching = ReviewProvider(
        isEligible: () => true,
        reportChannel: (_, {appBuild}) async => const ApiSuccess<void>(null),
        loadItems: () => pending.future,
        loadOpenLoopCards: () async => const ApiSuccess(OpenLoopCardsResponse(cards: [])));
    expect(launching.availability, ReviewAvailability.unknown);
    await tester.pumpWidget(_host(launching, const ReviewEntryCard()));
    await tester.pump();
    expect(find.byKey(const Key('review_entry_card')), findsNothing);
  });
}
