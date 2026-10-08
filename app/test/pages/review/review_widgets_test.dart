import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/review.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/review/review_item_sheet.dart';
import 'package:omi/pages/review/widgets/review_entry_card.dart';
import 'package:omi/pages/review/widgets/review_question_card.dart';
import 'package:omi/providers/review_provider.dart';
import 'package:omi/ui/ui.dart';

final _task = ReviewItem(
  itemId: 'task:c1',
  kind: ReviewItemKind.task,
  task: const TaskItem(candidateId: 'c1', description: 'Send the signed SOW'),
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

Future<ReviewProvider> _provider(List<ReviewItem> items, List<(String, Map<String, dynamic>)> sent) async {
  final provider = ReviewProvider(
    isEligible: () => true,
    loadItems: () async => ApiSuccess(ReviewItemsResponse(items: items, remainingToday: items.length)),
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

  testWidgets('the Home entry shows the fallback while Review is off, and hides when caught up', (tester) async {
    final off = ReviewProvider(
        isEligible: () => true, loadItems: () async => const ApiFailure(ApiProblem(ApiProblemKind.notFound)));
    await off.load();
    await tester.pumpWidget(_host(off, const ReviewEntryCard(fallback: Text('old card'))));
    expect(find.text('old card'), findsOneWidget);

    final empty = await _provider(const [], []);
    await tester.pumpWidget(_host(empty, const ReviewEntryCard(fallback: Text('old card'))));
    expect(find.text('old card'), findsNothing);
    expect(find.byKey(const Key('review_entry_card')), findsNothing);

    final some = await _provider([_task], []);
    await tester.pumpWidget(_host(some, const ReviewEntryCard(fallback: Text('old card'))));
    expect(find.byKey(const Key('review_entry_card')), findsOneWidget);
  });
}
