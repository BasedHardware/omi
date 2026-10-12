import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/onboarding/name/name_widget.dart';
import 'package:omi/pages/onboarding/widgets/onboarding_card.dart';

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  Future<void> pump(WidgetTester tester, double bottomInset, Widget step) {
    return tester.pumpWidget(
      MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Builder(
          builder: (context) => MediaQuery(
            data: MediaQuery.of(context).copyWith(
              padding: EdgeInsets.only(bottom: bottomInset),
              viewPadding: EdgeInsets.only(bottom: bottomInset),
            ),
            child: Scaffold(body: KeyedSubtree(key: ValueKey(bottomInset), child: step)),
          ),
        ),
      ),
    );
  }

  // The onboarding cards once added MediaQuery.padding.bottom to their own padding and then wrapped
  // their content in a SafeArea that added it again, leaving 2 x 34pt + 8pt of dead space under the
  // button on an iPhone.
  const homeIndicatorInset = 34.0;

  testWidgets('an onboarding card reserves the bottom system inset once, not twice', (tester) async {
    Future<double> cardHeight(double inset) async {
      await pump(
        tester,
        inset,
        const OnboardingStep(card: OnboardingCard(content: [Text('step')], footer: [SizedBox(height: 48)])),
      );
      // The bottom card is the Container that wraps the SafeArea.
      final card = find.ancestor(of: find.byType(SafeArea), matching: find.byType(Container)).first;
      return tester.getSize(card).height;
    }

    final flat = await cardHeight(0);
    final inset = await cardHeight(homeIndicatorInset);
    expect(inset - flat, moreOrLessEquals(homeIndicatorInset, epsilon: 0.5));
  });

  testWidgets('a plain step lifts its button by the bottom inset once, not twice', (tester) async {
    Future<double> buttonBottom(double inset) async {
      await pump(tester, inset, NameWidget(goNext: () {}));
      return tester.getRect(find.byKey(const Key('onboarding_name_continue'))).bottom;
    }

    final flat = await buttonBottom(0);
    final inset = await buttonBottom(homeIndicatorInset);
    expect(flat - inset, moreOrLessEquals(homeIndicatorInset, epsilon: 0.5));
  });
}
