import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:nooto_v2/home/cards/today_card.dart';
import 'package:nooto_v2/home/companion_card.dart';
import 'package:nooto_v2/home/home_nav.dart';
import 'package:nooto_v2/l10n/gen/app_localizations.dart';

Widget _harness(TodayCard card, {void Function(int)? onSwitch}) {
  return MaterialApp(
    locale: const Locale('en'),
    localizationsDelegates: AppLocalizations.localizationsDelegates,
    supportedLocales: AppLocalizations.supportedLocales,
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

TodayItem _item(String description, {DateTime? createdAt, DateTime? dueAt}) =>
    TodayItem(description: description, createdAt: createdAt, dueAt: dueAt);

void main() {
  testWidgets('renders Day-1 explainer when empty', (tester) async {
    final card = TodayCard(items: const [], generatedAt: DateTime.now());

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
      items: [_item('first thing'), _item('second thing'), _item('third thing')],
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

  testWidgets('subtitle shows "of N" when total exceeds visible',
      (tester) async {
    final card = TodayCard(
      items: [_item('a'), _item('b'), _item('c')],
      totalIncomplete: 12,
      generatedAt: DateTime.parse('2026-04-30T10:00:00Z'),
    );

    await tester.pumpWidget(_harness(card));
    await tester.pumpAndSettle();

    expect(find.textContaining('3 of 12'), findsOneWidget);
  });

  testWidgets('subtitle shows plain "N items" when totals match',
      (tester) async {
    final card = TodayCard(
      items: [_item('a'), _item('b')],
      totalIncomplete: 2,
      generatedAt: DateTime.parse('2026-04-30T10:00:00Z'),
    );

    await tester.pumpWidget(_harness(card));
    await tester.pumpAndSettle();

    expect(find.textContaining('2 items'), findsOneWidget);
  });

  testWidgets('renders relative-age trailing tag for items with createdAt',
      (tester) async {
    final card = TodayCard(
      items: [
        _item('older', createdAt: DateTime.now().subtract(const Duration(days: 5))),
      ],
      generatedAt: DateTime.now(),
    );

    await tester.pumpWidget(_harness(card));
    await tester.pumpAndSettle();

    expect(find.text('5d'), findsOneWidget);
  });

  testWidgets('due date overrides createdAt for trailing tag',
      (tester) async {
    final card = TodayCard(
      items: [
        _item(
          'pay invoice',
          createdAt: DateTime.now().subtract(const Duration(days: 5)),
          dueAt: DateTime.now().add(const Duration(hours: 6, minutes: 30)),
        ),
      ],
      generatedAt: DateTime.now(),
    );

    await tester.pumpWidget(_harness(card));
    await tester.pumpAndSettle();

    // Allow 5h or 6h depending on how many ms elapsed during pump.
    expect(
      find.byWidgetPredicate((w) =>
          w is Text && (w.data == 'due 6h' || w.data == 'due 5h')),
      findsOneWidget,
    );
    expect(find.text('5d'), findsNothing);
  });

  testWidgets('past-due renders "overdue"', (tester) async {
    final card = TodayCard(
      items: [
        _item('late thing', dueAt: DateTime.now().subtract(const Duration(hours: 2))),
      ],
      generatedAt: DateTime.now(),
    );

    await tester.pumpWidget(_harness(card));
    await tester.pumpAndSettle();

    expect(find.text('overdue'), findsOneWidget);
  });

  testWidgets('See all tap switches to Plan tab when items exist',
      (tester) async {
    int? switchedTo;
    final card = TodayCard(
      items: [_item('email john')],
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
    final card = TodayCard(items: const [], generatedAt: DateTime.now());

    await tester.pumpWidget(_harness(
      card,
      onSwitch: (_) => tapCount++,
    ));
    await tester.pumpAndSettle();

    expect(find.byType(InkWell), findsNothing);
    expect(tapCount, 0);
  });

  group('JSON roundtrip', () {
    test('preserves items + totalIncomplete', () {
      final original = TodayCard(
        items: [
          TodayItem(
            description: 'a',
            createdAt: DateTime.parse('2026-04-25T10:00:00Z'),
          ),
          TodayItem(
            description: 'b',
            dueAt: DateTime.parse('2026-05-01T10:00:00Z'),
          ),
        ],
        totalIncomplete: 12,
        generatedAt: DateTime.parse('2026-04-30T12:00:00Z'),
      );
      final round = TodayCard.fromJson(original.toJson());

      expect(round.items.length, 2);
      expect(round.items[0].description, 'a');
      expect(round.items[0].createdAt, DateTime.parse('2026-04-25T10:00:00Z'));
      expect(round.items[1].dueAt, DateTime.parse('2026-05-01T10:00:00Z'));
      expect(round.totalIncomplete, 12);
      expect(round.generatedAt, original.generatedAt);
      expect(round.kind, CardKind.actionItem);
      expect(round.id, 'today:summary');
    });

    test('migrates legacy descriptions field', () {
      final legacyJson = {
        'kind': 'actionItem',
        'descriptions': ['legacy a', 'legacy b'],
        'generatedAt': '2026-04-30T12:00:00Z',
      };

      final card = TodayCard.fromJson(legacyJson);

      expect(card.items.length, 2);
      expect(card.items[0].description, 'legacy a');
      expect(card.items[0].createdAt, isNull);
      expect(card.totalIncomplete, isNull);
    });
  });
}
