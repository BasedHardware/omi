import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/services.dart';
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:sign_in_with_apple/sign_in_with_apple.dart';

import 'package:omi/app_globals.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/mobile/mobile_app.dart';
import 'package:omi/providers/auth_provider.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/auth_service.dart';

import '../helpers/sfpro_font_fixtures.dart';
import '../support/crashlytics_recorder.dart';

/// Signed out, and Sign in with Apple fails the way it does without a working Apple Account
/// (AuthorizationError 1000).
class _AppleFails extends AuthenticationProvider {
  _AppleFails() : super(initializeListeners: false);

  int googleTaps = 0;

  @override
  bool get requiresReauthentication => false;

  @override
  bool isSignedIn() => false;

  /// A store build: Apple and Google, not the local-dev button.
  @override
  bool get isLocalDevProfile => false;

  @override
  Future<UserCredential?> requestAppleCredential() async =>
      throw const SignInWithAppleAuthorizationException(code: AuthorizationErrorCode.unknown, message: 'error 1000');

  @override
  Future<void> onGoogleSignIn(Function() onSignIn) async => googleTaps++;
}

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

/// The Apple failure toast tells the reader to continue with Google, so it must not sit on the
/// sign-in buttons (docs/ux-contract.md §6), at the default and the largest standard iOS text size.
/// (At accessibility sizes the button labels themselves overflow, a separate defect.)
void main() {
  setUpAll(() async {
    await installCrashlyticsRecorder();
    // iOS draws this screen in SF Pro: Manrope is not bundled, so it falls back to the system font.
    for (final family in ['Manrope', 'CupertinoSystemText', 'CupertinoSystemDisplay']) {
      final loader = FontLoader(family);
      for (final weight in ['REGULAR', 'MEDIUM', 'BOLD']) {
        loader.addFont(sfProFont('SFPRODISPLAY$weight.OTF'));
      }
      await loader.load();
    }
  });

  for (final textScale in const [1.0, 1.35]) {
    testWidgets('Sign in with Google stays tappable under the Apple failure toast (text x$textScale)', (tester) async {
      // iPhone 17 Pro: 402 x 874 points, home indicator inset.
      tester.view.devicePixelRatio = 3;
      tester.view.physicalSize = const Size(1206, 2622);
      tester.view.padding = const FakeViewPadding(top: 186, bottom: 102);
      tester.view.viewPadding = const FakeViewPadding(top: 186, bottom: 102);
      tester.platformDispatcher.textScaleFactorTestValue = textScale;
      addTearDown(tester.view.reset);
      addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
      SharedPreferences.setMockInitialValues({});
      await SharedPreferencesUtil.init();
      AuthService.installLocalHarnessTokenGateway(_SignedOutTokenGateway());
      final provider = _AppleFails();
      addTearDown(provider.dispose);

      await tester.pumpWidget(_app(provider));
      await tester.pumpAndSettle();
      final google = find.widgetWithText(ElevatedButton, 'Sign in with Google');
      await tester.ensureVisible(google);
      await tester.pumpAndSettle();

      await provider.onAppleSignIn(() {});
      await tester.pumpAndSettle();

      final message = find.text("Sign in with Apple didn't work. Try again or continue with Google.");
      expect(message, findsOneWidget);
      final toast = find.descendant(of: find.byType(SnackBar), matching: find.byType(Material)).first;
      expect(tester.getRect(toast).overlaps(tester.getRect(google)), isFalse);
      expect(tester.getRect(toast).top, greaterThanOrEqualTo(0), reason: 'the whole toast stays on screen');

      await tester.tap(google);
      expect(provider.googleTaps, 1);

      await tester.pump(const Duration(seconds: 9));
      await tester.pumpAndSettle();
    }, variant: TargetPlatformVariant.only(TargetPlatform.iOS));
  }
}
