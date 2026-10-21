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

  Future<double> cardHeight(WidgetTester tester, double bottomInset) async {
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
    // The bottom card is the Container that wraps the SafeArea.
    final card = find.ancestor(of: find.byType(SafeArea), matching: find.byType(Container)).first;
    return tester.getSize(card).height;
  }

  testWidgets('an onboarding card reserves the bottom system inset once, not twice', (tester) async {
    // The onboarding cards added MediaQuery.padding.bottom to their own padding
    // and then wrapped their content in a SafeArea that added it again, leaving
    // 2 x 34pt + 8pt = 76pt of dead space under the button on an iPhone.
    const homeIndicatorInset = 34.0;

    final flat = await cardHeight(tester, 0);
    final inset = await cardHeight(tester, homeIndicatorInset);

    expect(inset - flat, moreOrLessEquals(homeIndicatorInset, epsilon: 0.5));
  });
}
