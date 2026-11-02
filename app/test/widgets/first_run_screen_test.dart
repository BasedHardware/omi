import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/app_globals.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/mobile/mobile_app.dart';
import 'package:omi/pages/home/page.dart';
import 'package:omi/pages/onboarding/wrapper.dart';
import 'package:omi/providers/auth_provider.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/auth_service.dart';

/// The fresh-install state the Android emulator acceptance smoke launches
/// into: signed out, no onboarding state, offline.
class _SignedOutAuthenticationProvider extends AuthenticationProvider {
  _SignedOutAuthenticationProvider() : super(initializeListeners: false);

  @override
  bool get requiresReauthentication => false;

  @override
  bool isSignedIn() => false;
}

/// No current user on the auth-service singleton the wrapper consults.
final class _SignedOutTokenGateway implements AuthTokenGateway {
  @override
  AuthUserSnapshot? get currentUser => null;

  @override
  Future<RefreshedAuthToken?> forceRefresh() async => null;

  @override
  Future<void> signOut() async {}
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
    'a fresh signed-out install opens on the sign-in screen (the first-run screen the Android acceptance smoke requires)',
    (tester) async {
      SharedPreferences.setMockInitialValues({});
      await SharedPreferencesUtil.init();
      AuthService.installLocalHarnessTokenGateway(_SignedOutTokenGateway());
      final authProvider = _SignedOutAuthenticationProvider();
      addTearDown(authProvider.dispose);

      await tester.pumpWidget(_app(authProvider));
      await tester.pump();

      expect(find.byType(OnboardingWrapper), findsOneWidget);
      expect(find.byType(HomePageWrapper), findsNothing);
      expect(find.text('Speak. Transcribe. Summarize.'), findsOneWidget);

      await tester.pumpAndSettle();
    },
  );
}
