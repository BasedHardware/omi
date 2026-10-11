import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/onboarding/widgets/onboarding_step_layout.dart';
import 'package:omi/pages/onboarding/wrapper.dart';

void main() {
  testWidgets('progress dots count only real steps and speak "Step N of M"', (tester) async {
    final handle = tester.ensureSemantics();
    await tester.pumpWidget(
      const MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(body: OnboardingProgressDots(current: 1, total: 6)),
      ),
    );

    expect(find.bySemanticsLabel('Step 2 of 6'), findsOneWidget);
    // One dot per step: no placeholder pages inflate the count.
    expect(
      find.descendant(of: find.byType(OnboardingProgressDots), matching: find.byType(AnimatedContainer)),
      findsNWidgets(6),
    );
    handle.dispose();
  });

  test('the progress steps are the five real first-run steps while Knowledge Graph is hidden', () {
    expect(OnboardingProgressStepsForTest.knowledgeGraphStepEnabled, isFalse);
    expect(OnboardingProgressStepsForTest.steps, hasLength(5));
    expect(OnboardingProgressStepsForTest.steps, isNot(contains(OnboardingProgressStepsForTest.knowledgeGraphPage)));
  });

  testWidgets('floating navigation reserves its row, so a step SafeArea starts below the dots and back button', (
    tester,
  ) async {
    Future<double> top({int? progress, VoidCallback? onBack}) async {
      await tester.pumpWidget(
        MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: MediaQuery(
            data: const MediaQueryData(size: Size(390, 844), padding: EdgeInsets.only(top: 47)),
            child: Scaffold(
              body: OnboardingStepLayout(
                reserveHeader: false,
                progress: progress == null ? null : OnboardingProgressDots(current: progress, total: 6),
                onBack: onBack,
                child: const SafeArea(child: Text('step title', key: Key('title'))),
              ),
            ),
          ),
        ),
      );
      return tester.getTopLeft(find.byKey(const Key('title'))).dy;
    }

    expect(await top(), 47, reason: 'no chrome, nothing reserved');
    final withDots = await top(progress: 4, onBack: () {});
    expect(withDots, 47 + kOnboardingChromeHeight);
    expect(withDots, greaterThanOrEqualTo(tester.getBottomLeft(find.byType(OnboardingProgressDots)).dy));
    expect(withDots, greaterThanOrEqualTo(tester.getBottomLeft(find.byKey(const Key('onboarding_back'))).dy));
    expect(await top(onBack: () {}), 47 + kOnboardingChromeHeight, reason: 'the back button alone also reserves');
  });
}
