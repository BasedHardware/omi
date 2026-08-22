import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/app_globals.dart';
import 'package:omi/env/env.dart';
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
  // The onboarding auth page reads Env.useOidc (auth.dart, ADR-0038) while building, so Env must be
  // initialized or the widget tree throws LateInitializationError. Default to the firebase backend
  // (useOidc == false) — this test asserts the expired-session UI, not the auth-backend branch.
  setUpAll(() => Env.init(_FakeEnv()));

  testWidgets(
    'expired session replaces the home shell with reauthentication UI and a clear message',
    (tester) async {
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
    },
  );
}

class _FakeEnv implements EnvFields {
  @override
  String? get apiBaseUrl => 'https://api.omi.me/';

  @override
  String? get openAIAPIKey => null;

  @override
  String? get posthogApiKey => null;

  @override
  String? get googleMapsApiKey => null;

  @override
  String? get intercomAppId => null;

  @override
  String? get intercomIOSApiKey => null;

  @override
  String? get intercomAndroidApiKey => null;

  @override
  String? get googleClientId => null;

  @override
  String? get googleClientSecret => null;

  @override
  bool? get useWebAuth => false;

  @override
  bool? get useAuthCustomToken => false;

  @override
  String? get authBackend => 'firebase';

  @override
  String? get oidcIssuer => null;

  @override
  String? get oidcClientId => null;

  @override
  String? get oidcRedirectScheme => null;

  @override
  String? get notificationsBackend => 'fcm';
}
