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
import 'package:omi/services/auth/auth_token_result.dart';

class _ExpiredAuthenticationProvider extends AuthenticationProvider {
  _ExpiredAuthenticationProvider() : super(initializeListeners: false);

  @override
  bool get requiresReauthentication => true;

  @override
  int get sessionExpirationGeneration => 1;

  @override
  bool isSignedIn() => false;
}

class _DeletedAccountAuthenticationProvider extends _ExpiredAuthenticationProvider {
  @override
  AuthSessionExpirationReason? get sessionExpirationReason => AuthSessionExpirationReason.accountDeleted;
}

Widget _app(AuthenticationProvider authProvider) => ChangeNotifierProvider<AuthenticationProvider>.value(
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
    );

void main() {
  testWidgets(
    'expired session replaces the home shell with reauthentication UI and a clear message',
    (tester) async {
      final authProvider = _ExpiredAuthenticationProvider();
      addTearDown(authProvider.dispose);

      await tester.pumpWidget(_app(authProvider));
      await tester.pump();

      expect(find.byType(OnboardingWrapper), findsOneWidget);
      expect(find.byType(HomePageWrapper), findsNothing);
      expect(find.text('Session expired — sign in again.'), findsOneWidget);

      await tester.pumpAndSettle();
    },
  );

  testWidgets(
    'a session ended by the deleted-account fence says so instead of "session expired"',
    (tester) async {
      final authProvider = _DeletedAccountAuthenticationProvider();
      addTearDown(authProvider.dispose);

      await tester.pumpWidget(_app(authProvider));
      await tester.pump();

      expect(find.byType(OnboardingWrapper), findsOneWidget);
      expect(find.byType(HomePageWrapper), findsNothing);
      expect(
        find.text('This account is being deleted. Sign in with another account, or wait a few minutes and try again.'),
        findsOneWidget,
      );
      expect(find.text('Session expired — sign in again.'), findsNothing);

      await tester.pumpAndSettle();
    },
  );
}
