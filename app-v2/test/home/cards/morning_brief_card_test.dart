import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:nooto_v2/home/cards/morning_brief_card.dart';
import 'package:nooto_v2/home/companion_card.dart';

Widget _harness(MorningBriefCard card) {
  return MaterialApp(
    home: Scaffold(
      body: Builder(builder: (ctx) => card.render(ctx)),
    ),
  );
}

void main() {
  testWidgets('renders greeting and body', (tester) async {
    final card = MorningBriefCard(
      dateKey: '2026-04-30',
      greeting: 'Good morning, Matheus.',
      body: 'Yesterday you said you would email John. Today: three meetings.',
      generatedAt: DateTime.now(),
    );

    await tester.pumpWidget(_harness(card));
    await tester.pumpAndSettle();

    expect(find.text('Good morning, Matheus.'), findsOneWidget);
    expect(
      find.textContaining('Yesterday you said you would email John'),
      findsOneWidget,
    );
  });

  testWidgets('omits greeting line when empty string', (tester) async {
    final card = MorningBriefCard(
      dateKey: '2026-04-30',
      greeting: '',
      body: 'just the body',
      generatedAt: DateTime.now(),
    );

    await tester.pumpWidget(_harness(card));
    await tester.pumpAndSettle();

    expect(find.text('just the body'), findsOneWidget);
  });

  test('toJson/fromJson roundtrip preserves fields', () {
    final original = MorningBriefCard(
      dateKey: '2026-04-30',
      greeting: 'Hi.',
      body: 'short brief',
      generatedAt: DateTime.parse('2026-04-30T10:00:00Z'),
    );

    final round = MorningBriefCard.fromJson(original.toJson());

    expect(round.dateKey, '2026-04-30');
    expect(round.greeting, 'Hi.');
    expect(round.body, 'short brief');
    expect(round.kind, CardKind.brief);
    expect(round.id, 'brief:2026-04-30');
  });
}
