import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/onboarding/found_omi/found_omi_widget.dart';

void main() {
  Future<void> pumpFoundOmi(WidgetTester tester, {VoidCallback? goNext}) async {
    await tester.pumpWidget(
      MaterialApp(
        localizationsDelegates: const [
          AppLocalizations.delegate,
          GlobalMaterialLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
        ],
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(body: FoundOmiWidget(goNext: goNext ?? () {})),
      ),
    );
    await tester.pump();
  }

  // Regression: the source list used to be a wrapping pile of
  // content-sized chips (uneven last row). It's now a 4×3 grid of
  // equal capsules, including Other, with nothing to scroll.
  testWidgets('found-omi sources render as an even 4-by-3 capsule grid', (tester) async {
    await pumpFoundOmi(tester);

    expect(find.byType(ListView), findsNothing);
    expect(find.byType(Wrap), findsNothing);
    expect(find.text('TikTok'), findsOneWidget);
    expect(find.text('Google'), findsOneWidget);
    expect(find.text('Google Search'), findsNothing);
    expect(find.text('Other'), findsOneWidget);

    // First row is four equal-height capsules across.
    final firstRowTops = [
      tester.getRect(find.text('TikTok')).top,
      tester.getRect(find.text('YouTube')).top,
      tester.getRect(find.text('Instagram')).top,
      tester.getRect(find.text('X (Twitter)')).top,
    ];
    for (final top in firstRowTops.skip(1)) {
      expect(top, closeTo(firstRowTops.first, 1));
    }

    // Third row sits below the first, and Other is the last cell.
    expect(tester.getRect(find.text('Other')).top, greaterThan(firstRowTops.first + 20));
    expect(tester.getRect(find.text('Google')).top, closeTo(tester.getRect(find.text('Other')).top, 1));
  });

  testWidgets('Continue is disabled until a source is picked, then enabled', (tester) async {
    await pumpFoundOmi(tester);

    ElevatedButton continueButton() => tester.widget<ElevatedButton>(find.widgetWithText(ElevatedButton, 'Continue'));

    expect(continueButton().onPressed, isNull);

    await tester.tap(find.text('TikTok'));
    await tester.pump();

    expect(continueButton().onPressed, isNotNull);
  });

  // The "Other" chip expands in place into a text field instead of a second
  // box appearing elsewhere on the page.
  testWidgets('tapping Other expands it into an inline text field', (tester) async {
    await pumpFoundOmi(tester);

    expect(find.byType(TextField), findsNothing);

    await tester.tap(find.text('Other'));
    await tester.pumpAndSettle(const Duration(milliseconds: 300));

    expect(find.byType(TextField), findsOneWidget);
    ElevatedButton continueButton() => tester.widget<ElevatedButton>(find.widgetWithText(ElevatedButton, 'Continue'));
    expect(continueButton().onPressed, isNull);

    await tester.enterText(find.byType(TextField), 'A friend told me');
    await tester.pump();

    expect(continueButton().onPressed, isNotNull);

    // Closing it collapses back to the plain chip and clears the text.
    await tester.tap(find.byIcon(Icons.close));
    await tester.pumpAndSettle(const Duration(milliseconds: 300));

    expect(find.byType(TextField), findsNothing);
    expect(find.text('Other'), findsOneWidget);
    expect(continueButton().onPressed, isNull);
  });
}
