import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/onboarding/complete_screen.dart';
import 'package:omi/widgets/omi_device_glow.dart';
import 'package:omi/widgets/onboarding_page_transition.dart';

void main() {
  testWidgets('completion page is just the title, device graphic, and a button without an arrow', (tester) async {
    var completed = false;

    await tester.pumpWidget(
      MaterialApp(
        localizationsDelegates: const [
          AppLocalizations.delegate,
          GlobalMaterialLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
        ],
        supportedLocales: AppLocalizations.supportedLocales,
        home: OnboardingCompleteScreen(onComplete: () => completed = true),
      ),
    );
    await tester.pump();

    expect(find.text('You are all set'), findsOneWidget);
    expect(find.byType(OmiDeviceGlow), findsOneWidget);
    expect(find.text('Start using Omi'), findsOneWidget);
    expect(find.byIcon(Icons.arrow_forward_rounded), findsNothing);
    expect(find.byIcon(Icons.arrow_forward), findsNothing);
    expect(find.textContaining('Just use Omi'), findsNothing);
    expect(find.textContaining('USE OMI'), findsNothing);
    expect(find.textContaining('2 days'), findsNothing);

    await tester.tap(find.widgetWithText(ElevatedButton, 'Start using Omi'));
    await tester.pump();
    expect(completed, isFalse);
    expect(tester.widget<ElevatedButton>(find.byType(ElevatedButton)).onPressed, isNull);

    await tester.pumpAndSettle();
    expect(completed, isTrue);
  });
}
