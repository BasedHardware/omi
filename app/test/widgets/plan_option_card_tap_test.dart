import 'package:flutter/material.dart';
import 'package:flutter/semantics.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/pages/settings/widgets/plans/plan_cards.dart';

void main() {
  testWidgets('tapping plan details selects the tier, not only the heading', (tester) async {
    var taps = 0;
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Center(
            child: SizedBox(
              width: 360,
              child: PlanOptionCard(
                isSelected: false,
                title: 'Unlimited',
                subtitle: null,
                price: '\$29.99/mo',
                featureSummary: 'Unlimited transcription',
                features: const ['1000 chat questions per month'],
                onTap: () => taps++,
              ),
            ),
          ),
        ),
      ),
    );

    await tester.tap(find.text('Unlimited'));
    expect(taps, 1);

    await tester.tap(find.text('1000 chat questions per month'));
    expect(taps, 2, reason: 'the feature rows are part of the visible plan card');

    final card = tester.getRect(find.byType(PlanOptionCard));
    await tester.tapAt(card.bottomCenter - const Offset(0, 4));
    expect(taps, 3, reason: 'empty space inside the card must also select the plan');
  });

  testWidgets('only the header is the screen-reader button, so plan details stay readable', (tester) async {
    final semantics = tester.ensureSemantics();
    var taps = 0;
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: PlanOptionCard(
            isSelected: true,
            title: 'Unlimited',
            subtitle: null,
            price: '\$29.99/mo',
            features: const ['1000 chat questions per month'],
            onTap: () => taps++,
          ),
        ),
      ),
    );

    expect(
      tester.getSemantics(find.text('Unlimited')),
      containsSemantics(isButton: true, isSelected: true, isInMutuallyExclusiveGroup: true, hasTapAction: true),
    );
    expect(
      tester.getSemantics(find.text('1000 chat questions per month')),
      isNot(containsSemantics(isButton: true)),
      reason: 'feature rows must not merge into the button label',
    );

    final header = tester.getSemantics(find.text('Unlimited'));
    header.owner!.performAction(header.id, SemanticsAction.tap);
    expect(taps, 1, reason: 'the screen-reader tap still selects the plan');
    semantics.dispose();
  });
}
