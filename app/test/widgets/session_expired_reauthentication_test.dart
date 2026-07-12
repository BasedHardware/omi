import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/app_globals.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/mobile/mobile_app.dart';
import 'package:omi/pages/home/page.dart';
import 'package:omi/pages/onboarding/wrapper.dart';
import 'package:omi/providers/auth_provider.dart';

class _ExpiredAuthenticationProvider extends AuthenticationProvider {
  _ExpiredAuthenticationProvider() : super(initializeListeners: false);

  @override
  bool get requiresReauthentication => true;

  @override
  int get sessionExpirationGeneration => 1;

  @override
  bool isSignedIn() => false;
}

void main() {
  testWidgets('expired session replaces the home shell with reauthentication UI and a clear message', (tester) async {
    final authProvider = _ExpiredAuthenticationProvider();
    addTearDown(authProvider.dispose);

    await tester.pumpWidget(
      ChangeNotifierProvider<AuthenticationProvider>.value(
        value: authProvider,
        child: MaterialApp(
          navigatorKey: globalNavigatorKey,
          localizationsDelegates: const [
            AppLocalizations.delegate,
            GlobalMaterialLocalizations.delegate,
            GlobalWidgetsLocalizations.delegate,
            GlobalCupertinoLocalizations.delegate,
          ],
          supportedLocales: AppLocalizations.supportedLocales,
          home: const MobileApp(),
        ),
      ),
    );
    await tester.pump();

    expect(find.byType(OnboardingWrapper), findsOneWidget);
    expect(find.byType(HomePageWrapper), findsNothing);
    expect(find.text('Session expired — sign in again.'), findsOneWidget);

    await tester.pumpAndSettle();
  });
}
