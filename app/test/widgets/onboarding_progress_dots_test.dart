import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/onboarding/wrapper.dart';

void main() {
  testWidgets('progress dots count only real steps and speak "Step N of M"', (tester) async {
    final handle = tester.ensureSemantics();
    await tester.pumpWidget(const MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: Scaffold(body: OnboardingProgressDots(current: 1, total: 6)),
    ));

    expect(find.bySemanticsLabel('Step 2 of 6'), findsOneWidget);
    // One dot per step: no placeholder pages inflate the count.
    expect(
      find.descendant(of: find.byType(OnboardingProgressDots), matching: find.byType(AnimatedContainer)),
      findsNWidgets(6),
    );
    handle.dispose();
  });

  test('the progress steps are the six real first-run steps', () {
    expect(OnboardingProgressStepsForTest.steps, hasLength(6));
  });
}
