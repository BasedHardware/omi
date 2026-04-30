import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:nooto_v2/home/cards/today_card.dart';
import 'package:nooto_v2/home/companion_card.dart';
import 'package:nooto_v2/home/home_nav.dart';

Widget _harness(TodayCard card, {void Function(int)? onSwitch}) {
  return MaterialApp(
    home: Provider<HomeNav>.value(
      value: HomeNav(switchToTab: onSwitch ?? (_) {}),
      child: Scaffold(
        body: SingleChildScrollView(
          child: Builder(builder: (ctx) => card.render(ctx)),
        ),
      ),
    ),
  );
}

void main() {
  testWidgets('renders Day-1 explainer when empty', (tester) async {
    final card = TodayCard(descriptions: const [], generatedAt: DateTime.now());

    await tester.pumpWidget(_harness(card));
    await tester.pumpAndSettle();

    expect(find.text('Today'), findsOneWidget);
    expect(
      find.textContaining("Once you start a recording"),
      findsOneWidget,
    );
    expect(find.text('See all'), findsOneWidget);
  });

  testWidgets('renders one bullet per description, max 3', (tester) async {
    final card = TodayCard(
      descriptions: const ['first thing', 'second thing', 'third thing'],
      generatedAt: DateTime.now(),
    );

    await tester.pumpWidget(_harness(card));
    await tester.pumpAndSettle();

    expect(find.text('Today'), findsOneWidget);
    expect(find.text('first thing'), findsOneWidget);
    expect(find.text('second thing'), findsOneWidget);
    expect(find.text('third thing'), findsOneWidget);
    expect(find.textContaining("Once you start a recording"), findsNothing);
  });

  testWidgets('See all tap switches to Plan tab when items exist',
      (tester) async {
    int? switchedTo;
    final card = TodayCard(
      descriptions: const ['email john'],
      generatedAt: DateTime.now(),
    );

    await tester.pumpWidget(_harness(
      card,
      onSwitch: (idx) => switchedTo = idx,
    ));
    await tester.pumpAndSettle();

    await tester.tap(find.text('See all'));
    await tester.pumpAndSettle();

    expect(switchedTo, HomeNav.planTabIndex);
  });

  testWidgets('See all is non-tappable in empty state', (tester) async {
    var tapCount = 0;
    final card = TodayCard(descriptions: const [], generatedAt: DateTime.now());

    await tester.pumpWidget(_harness(
      card,
      onSwitch: (_) => tapCount++,
    ));
    await tester.pumpAndSettle();

    // InkWell wrapper is omitted in empty mode, so the row is not interactive.
    expect(find.byType(InkWell), findsNothing);
    expect(tapCount, 0);
  });

  test('toJson/fromJson roundtrip preserves descriptions', () {
    final original = TodayCard(
      descriptions: const ['a', 'b'],
      generatedAt: DateTime.parse('2026-04-30T12:00:00Z'),
    );
    final round = TodayCard.fromJson(original.toJson());

    expect(round.descriptions, ['a', 'b']);
    expect(round.generatedAt, original.generatedAt);
    expect(round.kind, CardKind.actionItem);
    expect(round.id, 'today:summary');
  });
}
