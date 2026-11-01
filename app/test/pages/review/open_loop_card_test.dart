import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/open_loops.dart';
import 'package:omi/backend/schema/review.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/review/widgets/open_loop_card.dart';
import 'package:omi/providers/review_provider.dart';
import 'package:omi/ui/ui.dart';

const _card = OpenLoopCard(
  cardId: 'ol-1',
  date: '2026-10-26',
  question: 'Did Maya send the vendor write-up?',
  contextLine: "From Monday's Pricing sync, due Tuesday",
);

ReviewProvider _provider(
  List<OpenLoopCard> cards, {
  required Future<ApiResult<OpenLoopAnswerResult>> Function(OpenLoopCard, OpenLoopAction) send,
}) {
  return ReviewProvider(
    isEligible: () => true,
    reportChannel: (_, {appBuild}) async => const ApiSuccess<void>(null),
    loadItems: () async => const ApiSuccess(ReviewItemsResponse(items: [], remainingToday: 0)),
    loadOpenLoopCards: () async => ApiSuccess(OpenLoopCardsResponse(cards: cards)),
    sendOpenLoopAnswer: send,
  );
}

Future<void> _loaded(ReviewProvider provider) => provider.load();

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
  testWidgets('shows the card verbatim with exactly the three answers', (tester) async {
    final provider = _provider([_card], send: (card, action) async {
      fail('no answer expected');
    });
    await _loaded(provider);
    await tester.pumpWidget(_host(provider, const OpenLoopQuestionCard(card: _card)));

    expect(find.text('Did Maya send the vendor write-up?'), findsOneWidget);
    expect(find.text("From Monday's Pricing sync, due Tuesday"), findsOneWidget);
    expect(find.text('Done'), findsOneWidget);
    expect(find.text('Remind me later'), findsOneWidget);
    expect(find.text('Drop it'), findsOneWidget);
  });

  testWidgets('a long question and context wrap instead of truncating', (tester) async {
    const longCard = OpenLoopCard(
      cardId: 'ol-long',
      date: '2026-10-26',
      question: 'Did you send Tyler the bullets for the Stably write-up before the partner review?',
      contextLine: "From Friday's Stably partner sync, was due Monday, no follow-up since Friday",
    );
    final provider = _provider([longCard], send: (card, action) async {
      fail('no answer expected');
    });
    await _loaded(provider);
    await tester.pumpWidget(
      Center(
        child: SizedBox(
          width: 320,
          child: _host(provider, const OpenLoopQuestionCard(card: longCard)),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text(longCard.question), findsOneWidget, reason: 'the question is never ellipsized away');
    expect(find.text(longCard.contextLine), findsOneWidget, reason: 'the context line is never ellipsized away');
    expect(tester.takeException(), isNull, reason: 'wrapping must not overflow');
    expect(find.text('Done'), findsOneWidget);
  });

  testWidgets('Remind me later sends remind and removes the card', (tester) async {
    final sent = <OpenLoopAction>[];
    final provider = _provider([_card], send: (card, action) async {
      sent.add(action);
      return ApiSuccess(OpenLoopAnswerResult(cardId: card.cardId, state: 'remind'));
    });
    await _loaded(provider);
    await tester.pumpWidget(_host(provider, const OpenLoopQuestionCard(card: _card)));

    await tester.tap(find.text('Remind me later'));
    await tester.pumpAndSettle();

    expect(sent, [OpenLoopAction.remind]);
    expect(provider.openLoopCards, isEmpty);
  });

  testWidgets('a failed answer puts the card back and says so', (tester) async {
    final provider = _provider([_card], send: (card, action) async {
      return const ApiFailure(ApiProblem(ApiProblemKind.server));
    });
    await _loaded(provider);
    await tester.pumpWidget(_host(provider, const OpenLoopQuestionCard(card: _card)));

    await tester.tap(find.text('Done'));
    await tester.pumpAndSettle();

    expect(provider.openLoopCards.map((c) => c.cardId), ['ol-1'], reason: 'rollback');
    expect(find.text('Couldn’t save your answer. Try again.'), findsOneWidget);
  });

  testWidgets('a 409 keeps the card gone and reports the conflict for that request', (tester) async {
    const a = OpenLoopCard(cardId: 'ol-1', date: '2026-10-26', question: 'Did Maya send it?');
    const b = OpenLoopCard(cardId: 'ol-2', date: '2026-10-26', question: 'Did you file the bug?');
    var conflict = true;
    final provider = _provider([a, b],
        send: (card, action) async => conflict
            ? const ApiFailure(ApiProblem(ApiProblemKind.rejected, statusCode: 409))
            : const ApiFailure(ApiProblem(ApiProblemKind.server)));
    await _loaded(provider);
    await tester.pumpWidget(
      _host(
        provider,
        const Column(children: [OpenLoopQuestionCard(card: a), OpenLoopQuestionCard(card: b)]),
      ),
    );

    await tester.tap(find.text('Drop it').first);
    await tester.pumpAndSettle();

    expect(provider.openLoopCards.map((c) => c.cardId), ['ol-2'], reason: 'answered on another device; stays gone');
    expect(find.text('This question is out of date, so nothing changed.'), findsOneWidget);

    // The next failing answer is its own request: the plain failure message.
    conflict = false;
    await tester.tap(find.text('Done').last);
    await tester.pumpAndSettle();
    expect(find.text("Couldn’t save your answer. Try again."), findsOneWidget);
    expect(find.text('This question is out of date, so nothing changed.'), findsNothing);
  });
}
