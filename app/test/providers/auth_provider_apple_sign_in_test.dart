import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sign_in_with_apple/sign_in_with_apple.dart';

import 'package:omi/app_globals.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/providers/auth_provider.dart';

import '../support/crashlytics_recorder.dart';

/// Sign in with Apple as the reader sees it: a cancel says nothing, a real failure (AuthorizationError
/// 1000, a Firebase rejection) points them to Google and is reported, and the web flow's empty result
/// keeps its own message.
class _AppleOutcome extends AuthenticationProvider {
  _AppleOutcome(this.outcome) : super(initializeListeners: false);

  final Future<UserCredential?> Function() outcome;

  @override
  Future<UserCredential?> requestAppleCredential() => outcome();
}

Widget _app() => MaterialApp(
      navigatorKey: globalNavigatorKey,
      localizationsDelegates: const [
        AppLocalizations.delegate,
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      supportedLocales: AppLocalizations.supportedLocales,
      home: const Scaffold(body: SizedBox()),
    );

const _useGoogle = "Sign in with Apple didn't work. Try again or continue with Google.";

void main() {
  late CrashlyticsRecorder crashlytics;
  setUpAll(() async => crashlytics = await installCrashlyticsRecorder());
  setUp(() => crashlytics.reset());

  Future<void> signIn(WidgetTester tester, Future<UserCredential?> Function() outcome) async {
    await tester.pumpWidget(_app());
    final provider = _AppleOutcome(outcome);
    addTearDown(provider.dispose);
    var signedIn = false;
    await provider.onAppleSignIn(() => signedIn = true);
    await tester.pumpAndSettle();
    expect(signedIn, isFalse);
    expect(provider.loading, isFalse, reason: 'the buttons come back after every outcome');
  }

  Future<void> letToastClose(WidgetTester tester) async {
    await tester.pump(const Duration(seconds: 9));
    await tester.pumpAndSettle();
  }

  testWidgets('a cancel shows nothing and reports nothing', (tester) async {
    await signIn(
      tester,
      () async => throw const SignInWithAppleAuthorizationException(code: AuthorizationErrorCode.canceled, message: ''),
    );
    expect(find.byType(SnackBar), findsNothing);
    expect(crashlytics.recordErrors, isEmpty);
  });

  testWidgets('Apple error 1000 points to Google and is reported', (tester) async {
    await signIn(
      tester,
      () async => throw const SignInWithAppleAuthorizationException(
          code: AuthorizationErrorCode.unknown, message: 'error 1000'),
    );
    expect(find.text(_useGoogle), findsOneWidget);
    expect(crashlytics.recordErrors, hasLength(1));
    await letToastClose(tester);
  });

  testWidgets('a Firebase rejection of the Apple token points to Google and is reported', (tester) async {
    await signIn(tester, () async => throw FirebaseAuthException(code: 'invalid-credential'));
    expect(find.text(_useGoogle), findsOneWidget);
    expect(crashlytics.recordErrors, hasLength(1));
    await letToastClose(tester);
  });

  testWidgets('the web flow returning nothing keeps its own message', (tester) async {
    await signIn(tester, () async => null);
    expect(find.text('Failed to sign in with Apple, please try again.'), findsOneWidget);
    await letToastClose(tester);
  });
}
