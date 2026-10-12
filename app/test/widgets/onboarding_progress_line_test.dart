import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/onboarding/widgets/onboarding_step_layout.dart';
import 'package:omi/pages/onboarding/wrapper.dart';

void main() {
  testWidgets('progress line fills by real steps and speaks "Step N of M"', (tester) async {
    final handle = tester.ensureSemantics();
    await tester.pumpWidget(
      const MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(body: OnboardingProgressLine(current: 1, total: 6)),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.bySemanticsLabel('Step 2 of 6'), findsOneWidget);
    // The fill covers the steps reached so far: 2 of 6.
    final fill = tester.widget<FractionallySizedBox>(
      find.descendant(of: find.byType(OnboardingProgressLine), matching: find.byType(FractionallySizedBox)),
    );
    expect(fill.widthFactor, closeTo(2 / 6, 1e-9));
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
                progress: progress == null ? null : OnboardingProgressLine(current: progress, total: 6),
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
    expect(withDots, greaterThanOrEqualTo(tester.getBottomLeft(find.byType(OnboardingProgressLine)).dy));
    expect(withDots, greaterThanOrEqualTo(tester.getBottomLeft(find.byKey(const Key('onboarding_back'))).dy));
    expect(await top(onBack: () {}), 47 + kOnboardingChromeHeight, reason: 'the back button alone also reserves');
  });
}
