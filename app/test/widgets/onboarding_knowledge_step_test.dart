// The first-run "Here is what I know about you" step (v2 Knows): a sample map with the reader at
// the centre, four topics and Continue in the standard place — at every phone size and text size.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/onboarding/knowledge_graph_step.dart';
import 'package:omi/pages/onboarding/widgets/knowledge_preview.dart';
import 'package:omi/ui/omi_theme.dart';

void main() {
  final en = lookupAppLocalizations(const Locale('en'));

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  testWidgets('the reader at the centre, four topics, and Continue', (tester) async {
    SharedPreferencesUtil().givenName = 'Ashwin';
    var continued = 0;
    for (final width in [320.0, 390.0, 440.0]) {
      for (final scale in [1.0, 1.3]) {
        tester.view.physicalSize = Size(width, 800);
        tester.view.devicePixelRatio = 1;
        tester.platformDispatcher.textScaleFactorTestValue = scale;
        await tester.pumpWidget(MaterialApp(
          theme: buildOmiTheme(),
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: const [Locale('en')],
          home: Scaffold(body: OnboardingKnowledgeGraphStep(onContinue: () => continued++)),
        ));
        await tester.pumpAndSettle();
        expect(tester.takeException(), isNull, reason: 'width $width, text x$scale');
        expect(find.byType(OnboardingKnowledgePreview), findsOneWidget);
        expect(find.text('Ashwin'), findsOneWidget);
        for (final topic in [en.categoryProductivity, en.people, en.categoryHealth, en.goals]) {
          expect(find.text(topic), findsOneWidget);
        }
      }
    }
    addTearDown(tester.view.reset);
    addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
    await tester.tap(find.byKey(const Key('onboarding_knowledge_graph_continue')));
    expect(continued, 1);
  });
}
