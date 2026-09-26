import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/onboarding/name/name_widget.dart';

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  /// Distance from the bottom of the screen to the bottom of the step's Continue button.
  Future<double> buttonLift(WidgetTester tester, double bottomInset) async {
    await tester.pumpWidget(
      MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Builder(
          builder: (context) => MediaQuery(
            data: MediaQuery.of(context).copyWith(
              padding: EdgeInsets.only(bottom: bottomInset),
              viewPadding: EdgeInsets.only(bottom: bottomInset),
            ),
            child: Scaffold(body: NameWidget(key: ValueKey(bottomInset), goNext: () {})),
          ),
        ),
      ),
    );
    final screen = tester.getRect(find.byType(Scaffold));
    final button = tester.getRect(find.byKey(const Key('onboarding_name_continue')));
    return screen.bottom - button.bottom;
  }

  testWidgets('an onboarding step reserves the bottom system inset once, not twice', (tester) async {
    // The onboarding cards once added MediaQuery.padding.bottom to their own padding and then
    // wrapped their content in a SafeArea that added it again, leaving 2 x 34pt + 8pt of dead space
    // under the button on an iPhone. The button must rise by exactly the inset.
    const homeIndicatorInset = 34.0;

    final flat = await buttonLift(tester, 0);
    final inset = await buttonLift(tester, homeIndicatorInset);

    expect(inset - flat, moreOrLessEquals(homeIndicatorInset, epsilon: 0.5));
  });
}
