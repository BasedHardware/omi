import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/mobile/mobile_app.dart';
import 'package:omi/pages/onboarding/wrapper.dart';
import 'package:omi/providers/auth_provider.dart';

class _SignedOutAuthenticationProvider extends AuthenticationProvider {
  _SignedOutAuthenticationProvider() : super(initializeListeners: false);

  @override
  bool isSignedIn() => false;
}

void main() {
  // Regression: MobileApp used to show DeviceSelectionPage as the first
  // screen for a signed-out user, which duplicated the onboarding splash
  // (both offered a "Get Started" button back to back). The splash is now
  // OnboardingWrapper's own first page, so there's only ever one.
  testWidgets('signed-out users land on the splash page of the onboarding wrapper', (tester) async {
    final authProvider = _SignedOutAuthenticationProvider();
    addTearDown(authProvider.dispose);

    await tester.pumpWidget(
      ChangeNotifierProvider<AuthenticationProvider>.value(
        value: authProvider,
        child: const MaterialApp(
          localizationsDelegates: [
            AppLocalizations.delegate,
            GlobalMaterialLocalizations.delegate,
            GlobalWidgetsLocalizations.delegate,
            GlobalCupertinoLocalizations.delegate,
          ],
          supportedLocales: AppLocalizations.supportedLocales,
          home: MobileApp(),
        ),
      ),
    );
    await tester.pump();

    expect(find.byType(OnboardingWrapper), findsOneWidget);
    expect(find.text('Omi'), findsOneWidget);
    expect(find.text('your second brain.'), findsOneWidget);
    // Not yet advanced past the splash into sign-in.
    expect(find.text('Speak. Transcribe. Summarize.'), findsNothing);
  });
}
