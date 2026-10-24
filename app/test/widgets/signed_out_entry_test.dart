import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/app_globals.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/mobile/mobile_app.dart';
import 'package:omi/pages/home/page.dart';
import 'package:omi/pages/onboarding/auth.dart';
import 'package:omi/pages/onboarding/widgets/onboarding_hero_film.dart';
import 'package:omi/pages/onboarding/wrapper.dart';
import 'package:omi/providers/auth_provider.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/auth_service.dart';

class _SignedOutAuthenticationProvider extends AuthenticationProvider {
  _SignedOutAuthenticationProvider() : super(initializeListeners: false);

  @override
  bool get requiresReauthentication => false;

  @override
  bool isSignedIn() => false;
}

/// No Firebase user: the signed-out state, without a Firebase app in the test.
class _NoUserGateway implements AuthTokenGateway {
  @override
  AuthUserSnapshot? get currentUser => null;
  @override
  Future<RefreshedAuthToken?> forceRefresh() async => null;
  @override
  Future<void> signOut() async {}
}

void main() {
  setUpAll(() => AuthService.installLocalHarnessTokenGateway(_NoUserGateway()));

  testWidgets('signed out opens on sign-in with the launch film behind it, no Get started page', (tester) async {
    final authProvider = _SignedOutAuthenticationProvider();
    addTearDown(authProvider.dispose);

    await tester.pumpWidget(ChangeNotifierProvider<AuthenticationProvider>.value(
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
    ));
    await tester.pump();

    expect(find.byType(OnboardingWrapper), findsOneWidget);
    expect(find.byType(AuthComponent), findsOneWidget);
    expect(find.byType(OnboardingHeroFilm), findsOneWidget);
    expect(find.byType(HomePageWrapper), findsNothing);

    await tester.pumpAndSettle();
  });
}
