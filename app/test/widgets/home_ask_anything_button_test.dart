import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/widgets/home_bottom_bar.dart';

// Regression test for #19854: Mobile: clean up the Home bottom bar with an Ask Anything button
// - Center the localized Ask Anything label, with no chat icon or microphone inside the button.
// - Tapping the button triggers the chat callback.
// - Verify layout, text style, and absence of microphone icon in light and dark themes.

Widget _buildHarness({required Widget child, Brightness brightness = Brightness.light}) {
  return MaterialApp(
    theme: ThemeData(brightness: brightness),
    localizationsDelegates: const [
      AppLocalizations.delegate,
      GlobalMaterialLocalizations.delegate,
      GlobalWidgetsLocalizations.delegate,
      GlobalCupertinoLocalizations.delegate,
    ],
    supportedLocales: AppLocalizations.supportedLocales,
    home: Scaffold(
      body: Center(
        child: SizedBox(
          width: 300,
          child: child,
        ),
      ),
    ),
  );
}

void main() {
  testWidgets('HomeAskAnythingButton displays centered localized label and invokes callback on tap', (tester) async {
    var tapped = false;
    await tester.pumpWidget(
      _buildHarness(
        child: HomeAskAnythingButton(
          onTap: () {
            tapped = true;
          },
        ),
      ),
    );
    await tester.pumpAndSettle();

    // Verify localized label "Ask anything" is present
    final textFinder = find.text('Ask anything');
    expect(textFinder, findsOneWidget);

    // Verify text is centered
    final textWidget = tester.widget<Text>(textFinder);
    expect(textWidget.textAlign, TextAlign.center);

    // Verify no microphone or chat icon is rendered inside the button
    expect(find.byType(FaIcon), findsNothing);
    expect(find.byIcon(Icons.mic), findsNothing);

    // Tap button and verify callback
    await tester.tap(textFinder);
    expect(tapped, isTrue);
  });

  testWidgets('HomeAskAnythingButton renders properly in Dark theme without icons', (tester) async {
    await tester.pumpWidget(
      _buildHarness(
        brightness: Brightness.dark,
        child: const HomeAskAnythingButton(),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Ask anything'), findsOneWidget);
    expect(find.byType(FaIcon), findsNothing);
    expect(tester.takeException(), isNull);
  });
}
