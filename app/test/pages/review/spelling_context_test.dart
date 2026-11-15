import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/open_loops.dart';
import 'package:omi/backend/schema/review.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/review/review_item_sheet.dart';
import 'package:omi/pages/review/widgets/review_parts.dart';
import 'package:omi/pages/review/widgets/review_question_card.dart';
import 'package:omi/providers/review_provider.dart';
import 'package:omi/ui/ui.dart';

import '../../../integration_test/support/dream_review_context_fixture.dart';

Future<ReviewProvider> _provider() async {
  final provider = ReviewProvider(
    isEligible: () => true,
    reportChannel: (_, {appBuild}) async => const ApiSuccess<void>(null),
    loadItems: () async => ApiSuccess(ReviewItemsResponse(items: [dreamSpellingQuestion], remainingToday: 3)),
    loadOpenLoopCards: () async => const ApiSuccess(OpenLoopCardsResponse(cards: [])),
  );
  await provider.load();
  return provider;
}

Widget _host(ReviewProvider provider, Widget child, {Locale locale = const Locale('en'), double scale = 1}) =>
    ChangeNotifierProvider<ReviewProvider>.value(
      value: provider,
      child: MaterialApp(
        locale: locale,
        theme: buildOmiTheme(),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        builder: (context, child) => MediaQuery(
          data: MediaQuery.of(context).copyWith(textScaler: TextScaler.linear(scale)),
          child: child!,
        ),
        home: Scaffold(body: ListView(children: [child])),
      ),
    );

void main() {
  testWidgets('card includes a one-line speech snippet and opens the context sheet', (tester) async {
    final provider = await _provider();
    addTearDown(provider.dispose);
    await tester.pumpWidget(_host(provider, ReviewQuestionCard(item: dreamSpellingQuestion)));
    expect(find.text('“UL”'), findsOneWidget);
    final snippet = tester.widget<Text>(find.byKey(const Key('review_spelling_snippet')));
    expect(snippet.data, contains('send the UL to the design group'));
    expect(snippet.maxLines, 1);
    await tester.tap(find.byKey(const ValueKey('review_card_open_spelling:synthetic-link')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('review_spelling_context')), findsOneWidget);
    expect(find.textContaining('Launch planning'), findsOneWidget);
    expect(find.text('Where should we send the link?'), findsOneWidget);
    expect(find.text('I will share it after lunch.'), findsOneWidget);
    expect(find.text('You'), findsOneWidget);
    expect(find.text('Alex'), findsNWidgets(2));
    final text = tester.widget<Text>(find.byKey(const Key('review_spelling_highlight')));
    final spans = (text.textSpan! as TextSpan).children!.cast<TextSpan>();
    expect(spans.map((s) => s.text).join(), dreamSpellingQuestion.spelling!.context!.main.text);
    expect(spans[1].text, 'UL');
    expect(spans[1].style!.backgroundColor, isNotNull);
    expect(tester.getTopLeft(find.byKey(const Key('review_spelling_context'))).dy,
        lessThan(tester.getTopLeft(find.widgetWithText(ReviewAnswerPill, 'URL').last).dy));
    expect(tester.takeException(), isNull);
  });

  for (final scale in [1.0, 2.0]) {
    testWidgets('context fits a narrow screen at text scale $scale', (tester) async {
      tester.view.physicalSize = const Size(320, 900);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final provider = await _provider();
      addTearDown(provider.dispose);
      await tester.pumpWidget(_host(provider, ReviewItemDetail(item: dreamSpellingQuestion), scale: scale));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('review_spelling_highlight')), findsOneWidget);
      expect(tester.takeException(), isNull);
    });
  }

  testWidgets('owner labels and context heading follow the app locale', (tester) async {
    final provider = await _provider();
    addTearDown(provider.dispose);
    await tester.pumpWidget(_host(provider, ReviewItemDetail(item: dreamSpellingQuestion), locale: const Locale('fr')));
    await tester.pumpAndSettle();
    final l10n = await AppLocalizations.delegate.load(const Locale('fr'));
    expect(find.text(l10n.you), findsOneWidget);
    expect(find.text(l10n.reviewSpellingContext), findsOneWidget);
    expect(find.text('You'), findsNothing);
  });

  testWidgets('a missing quote match displays cited speech without a highlight', (tester) async {
    final provider = await _provider();
    addTearDown(provider.dispose);
    final context = SpellingContext(
      conversationTitle: 'Launch planning',
      mainIndex: 0,
      segments: dreamSpellingQuestion.spelling!.context!.segments,
    );
    await tester.pumpWidget(_host(provider, ReviewSpellingContext(context: context)));
    expect(find.text('Where should we send the link?'), findsOneWidget);
    expect(find.byKey(const Key('review_spelling_highlight')), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('old spelling items retain quote and choices without context', (tester) async {
    final provider = await _provider();
    addTearDown(provider.dispose);
    const old = ReviewItem(
      itemId: 'spelling:old',
      kind: ReviewItemKind.spelling,
      quote: 'UL',
      spelling: SpellingItem(termId: 'old', options: ['UL', 'URL']),
    );
    await tester.pumpWidget(_host(provider, const ReviewItemDetail(item: old)));
    expect(find.text('“UL”'), findsOneWidget);
    expect(find.text('URL'), findsOneWidget);
    expect(find.byKey(const Key('review_spelling_context')), findsNothing);
  });

  test('optional malformed display metadata cannot hide an answerable spelling item', () {
    final spelling = SpellingItem.fromJson({
      'term_id': 'toy',
      'options': ['UL', 'URL'],
      'context': {'segments': [], 'main_index': 4},
    });
    expect(spelling, isNotNull);
    expect(spelling!.context, isNull);
  });
}
